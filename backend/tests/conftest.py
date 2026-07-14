"""Pytest configuration and fixtures."""

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Ensure tests are self-contained and do not require local .env/Redis.
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DEBUG"] = "false"
os.environ["REDIS_URL"] = "memory://"

from app.db.base import Base
from app.db.session import get_db
from app.main import app

# Use in-memory SQLite for tests - faster and isolated
# Each test gets a fresh database
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a test database session.
    
    Uses in-memory SQLite for fast, isolated tests.
    Each test gets a fresh database that doesn't affect others.
    """
    # Create async engine with in-memory SQLite
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    # Drop all tables after test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create a test HTTP client.
    
    Overrides the database dependency to use the test session.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # Disable rate limiting in tests to keep flows deterministic.
    app.state.limiter.enabled = False

    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clean up
    app.state.limiter.enabled = True
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def auth_user(db_session: AsyncSession) -> "User":
    """Create a regular authenticated user for protected-endpoint tests."""
    from app.models.user import User

    user = User(
        email="auth_user@example.com",
        username="authuser",
        password_hash="$2b$12$test",
        active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def auth_client(client: AsyncClient, auth_user: "User") -> AsyncClient:
    """HTTP client pre-authenticated as a regular user (Bearer token)."""
    from app.core.security import create_access_token

    token = create_access_token({"sub": auth_user.email})
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest_asyncio.fixture(scope="function")
async def admin_user(db_session: AsyncSession) -> "User":
    """Create an admin user for admin-only / privileged endpoint tests."""
    from app.models.user import User, UserRole

    user = User(
        email="admin_user@example.com",
        username="adminuser",
        password_hash="$2b$12$test",
        active=True,
        role=UserRole.ADMIN,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def admin_client(client: AsyncClient, admin_user: "User") -> AsyncClient:
    """HTTP client pre-authenticated as an admin (Bearer token)."""
    from app.core.security import create_access_token

    token = create_access_token({"sub": admin_user.email})
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def test_client() -> TestClient:
    """
    Create a synchronous test client (for simple tests).
    
    Note: For async tests, use the 'client' fixture instead.
    """
    return TestClient(app)
