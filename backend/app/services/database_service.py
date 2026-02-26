"""Service for database management operations."""

import asyncio
import logging
import math
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

# Path to migrations directory
ALEMBIC_CONFIG_PATH = Path(__file__).parent.parent.parent / "alembic.ini"
ALEMBIC_VERSIONS_PATH = Path(__file__).parent.parent.parent / "alembic" / "versions"


def get_alembic_config() -> Config:
    """Get Alembic configuration."""
    config = Config(str(ALEMBIC_CONFIG_PATH))
    # Escape % for Alembic (it interprets % as interpolation)
    database_url_escaped = settings.DATABASE_URL.replace('%', '%%')
    config.set_main_option("sqlalchemy.url", database_url_escaped)
    return config


async def _ensure_migration_history_table(db: AsyncSession) -> None:
    """Create migration history table if it doesn't exist."""
    try:
        # Check if table exists before creating
        result = await db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'alembic_migration_history'
            )
        """))
        exists = result.scalar()
        
        if not exists:
            logger.info("Creating alembic_migration_history table...")
            await db.execute(text("""
                CREATE TABLE alembic_migration_history (
                    revision VARCHAR(50) PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL DEFAULT now(),
                    applied_by VARCHAR(255),
                    downgraded_at TIMESTAMP,
                    downgraded_by VARCHAR(255)
                )
            """))
            logger.info("alembic_migration_history table created")
        else:
            logger.debug("alembic_migration_history table already exists")
    except Exception as e:
        logger.error(f"Failed to create migration history table: {e}", exc_info=True)
        await db.rollback()
        raise  # Re-raise so the caller knows about the error


async def _record_migration_application(db: AsyncSession, revision: str, applied_by: str | None = None) -> None:
    """Record migration application in history."""
    await _ensure_migration_history_table(db)
    try:
        await db.execute(text("""
            INSERT INTO alembic_migration_history (revision, applied_at, applied_by, downgraded_at, downgraded_by)
            VALUES (:revision, now(), :applied_by, NULL, NULL)
            ON CONFLICT (revision) 
            DO UPDATE SET 
                applied_at = now(),
                applied_by = :applied_by,
                downgraded_at = NULL,
                downgraded_by = NULL
        """), {"revision": revision, "applied_by": applied_by})
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to record migration application {revision}: {e}")
        await db.rollback()


async def _record_migration_downgrade(db: AsyncSession, revision: str, downgraded_by: str | None = None) -> None:
    """Record migration downgrade in history."""
    await _ensure_migration_history_table(db)
    try:
        await db.execute(text("""
            UPDATE alembic_migration_history
            SET downgraded_at = now(), downgraded_by = :downgraded_by
            WHERE revision = :revision
        """), {"revision": revision, "downgraded_by": downgraded_by})
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to record migration downgrade {revision}: {e}")
        await db.rollback()


async def get_migration_history(db: AsyncSession) -> dict:
    """Get migration history."""
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    
    config = get_alembic_config()
    script = ScriptDirectory.from_config(config)
    
    # Get current revision from DB
    current_revision = None
    try:
        # Use direct query without transaction for reading
        # Explicitly specify autocommit for reading
        result = await db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        if row:
            current_revision = str(row[0])  # Explicitly convert to string
            logger.info(f"Current revision from DB: {current_revision}")
        else:
            logger.info("alembic_version table is empty (no migrations applied yet)")
    except Exception as e:
        # alembic_version table may not exist if migrations haven't been applied yet
        logger.warning(f"Failed to get current revision: {e}", exc_info=True)
        current_revision = None
    
    # Get migration application history
    migration_history_map = {}
    try:
        # Create migration history table if it doesn't exist
        await _ensure_migration_history_table(db)
        # Commit table creation separately so it's available for queries
        await db.commit()
        
        result = await db.execute(text("""
            SELECT revision, applied_at, applied_by, downgraded_at, downgraded_by
            FROM alembic_migration_history
            WHERE downgraded_at IS NULL
        """))
        for row in result.fetchall():
            # Convert datetime to ISO string for Pydantic
            applied_at = row[1]
            if applied_at and isinstance(applied_at, datetime):
                applied_at = applied_at.isoformat()
            migration_history_map[row[0]] = {
                "applied_at": applied_at,
                "applied_by": row[2],
            }
    except Exception as e:
        logger.warning(f"Failed to get migration history: {e}")
    
    # Get all migrations
    migrations = []
    heads = [rev.revision for rev in script.get_revisions("heads")]
    
    # First build a map of all migrations for quick access
    all_revisions_map = {}
    for rev in script.walk_revisions():
        all_revisions_map[rev.revision] = rev
        # Get application date from history, if available
        history = migration_history_map.get(rev.revision, {})
        # down_revision can be a tuple (merge migration) - convert to string
        down_rev = rev.down_revision
        if isinstance(down_rev, tuple):
            down_rev = ",".join(down_rev)
        
        migration = {
            "revision": rev.revision,
            "down_revision": down_rev,
            "branch_labels": ",".join(rev.branch_labels) if rev.branch_labels else None,
            "is_head": rev.revision in heads,
            "is_applied": False,  # Will be updated below
            "applied_at": history.get("applied_at"),  # Date from migration history
            "description": rev.doc if rev.doc else None,
        }
        migrations.append(migration)
    
    # Check which migration is applied
    # Alembic stores only the current revision, so we need to check the chain
    applied_revisions = set()
    if current_revision:
        # Find all applied migrations (from current to initial)
        # Use recursive approach to handle all branches
        visited = set()
        
        def add_migration_chain(revision_id: str | None):
            """Recursively add migration and all its predecessors."""
            if revision_id is None or revision_id in visited:
                return
            
            visited.add(revision_id)
            
            # Get revision from map or via script
            rev = all_revisions_map.get(revision_id)
            if not rev:
                try:
                    rev = script.get_revision(revision_id)
                except Exception:
                    logger.warning(f"Failed to find revision {revision_id}")
                    applied_revisions.add(revision_id)
                    return
            
            if rev:
                applied_revisions.add(rev.revision)
                logger.debug(f"Added applied migration: {rev.revision}")
                
                # Process down_revision
                if rev.down_revision:
                    if isinstance(rev.down_revision, tuple):
                        # Multiple down_revision (merge) - process all branches
                        logger.debug(f"Merge detected in {rev.revision}, branches: {rev.down_revision}")
                        for down_rev in rev.down_revision:
                            if down_rev:
                                add_migration_chain(down_rev)
                    else:
                        # Single branch
                        add_migration_chain(rev.down_revision)
        
        # Start from current revision
        logger.info(f"Building applied migration chain starting from {current_revision}")
        add_migration_chain(current_revision)
        logger.info(f"Found applied migrations: {len(applied_revisions)}")
        logger.debug(f"Applied revisions: {sorted(applied_revisions)}")
    
    # Update application status
    for migration in migrations:
        migration["is_applied"] = migration["revision"] in applied_revisions
    
    return {
        "current_revision": current_revision,
        "heads": heads,
        "migrations": migrations,
    }


async def validate_migration_integrity(db: AsyncSession) -> tuple[bool, list[str]]:
    """
    Validate database integrity after applying migrations.

    Checks that all tables from migrations actually exist in the database.

    Returns:
        (is_valid, list_of_missing_tables)
    """
    from alembic.script import ScriptDirectory

    config = get_alembic_config()
    script = ScriptDirectory.from_config(config)

    # Get table list from SQLAlchemy models
    from app.db.base import Base
    # Import ALL models to register them in metadata
    from app.models import (  # noqa: F401
        Brand,
        BrandRequest,
        Filament,
        FilamentReview,
        MaterialMapping,
        Preset,
        PresetPrinter,
        Printer,
        PrinterRequest,
        User,
        UserSavedPreset,
    )
    # Additional models (may be absent in older versions)
    try:
        from app.models.feedback import Feedback  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.notification import Notification  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.wiki_article import WikiArticle  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.wiki_category import WikiCategory  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.wiki_feedback import WikiArticleFeedback  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.bad_word import BadWord  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.printer_profile import PrinterProfile  # noqa: F401
    except ImportError:
        pass
    try:
        from app.models.print_profile import PrintProfile  # noqa: F401
    except ImportError:
        pass
    
    # Get all tables from metadata
    expected_tables = set(Base.metadata.tables.keys())
    # Add alembic_version which is not in models
    expected_tables.add('alembic_version')
    
    # Get actual tables from DB
    try:
        result = await db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """))
        existing_tables = {row[0] for row in result.fetchall()}
        
        # Find missing tables
        missing_tables = expected_tables - existing_tables

        return len(missing_tables) == 0, list(missing_tables)
    except Exception as e:
        logger.error(f"Database integrity check error: {e}", exc_info=True)
        return False, [f"Validation error: {str(e)}"]


async def recreate_missing_tables(db: AsyncSession) -> tuple[bool, str, list[str]]:
    """
    Restore all missing tables by applying Alembic migrations.

    First tries to apply all unapplied migrations up to head.
    If that doesn't help, uses SQLAlchemy metadata as a fallback.
    
    Returns:
        (success, message, created_tables)
    """
    try:
        # Step 1: Check which tables are missing
        is_valid, missing_tables = await validate_migration_integrity(db)
        
        if is_valid:
            return True, "All tables already exist. Nothing to restore.", []
        
        if not missing_tables:
            return True, "All tables already exist. Nothing to restore.", []
        
        # Step 2: Try to apply migrations up to head
        # This is the proper way to create tables
        logger.info(f"Missing tables detected: {missing_tables}. Applying migrations up to head...")
        
        try:
            config = get_alembic_config()
            
            def run_upgrade():
                # Apply all migrations up to head
                command.upgrade(config, "head")
            
            await asyncio.to_thread(run_upgrade)
            
            # Check the result
            is_valid_after, still_missing = await validate_migration_integrity(db)
            
            if is_valid_after:
                return True, f"Successfully restored via migrations. All tables created.", list(missing_tables)
            
            if still_missing:
                logger.warning(f"Tables still missing after applying migrations: {still_missing}")
                # Continue to fallback method
                missing_tables = still_missing
        
        except Exception as migration_error:
            logger.warning(f"Failed to apply migrations: {migration_error}. Using fallback method.")
            # Continue to fallback method
        
        # Step 3: Fallback - create via SQLAlchemy metadata
        # This is only used if migrations didn't help
        logger.info(f"Using fallback method to create tables: {missing_tables}")

        from app.db.base import Base
        # Import ALL models to register them in metadata
        from app.models import (  # noqa: F401
            Brand,
            BrandRequest,
            Filament,
            FilamentReview,
            MaterialMapping,
            Preset,
            PresetPrinter,
            Printer,
            PrinterRequest,
            User,
            UserSavedPreset,
        )
        # Additional models
        try:
            from app.models.feedback import Feedback  # noqa: F401
            from app.models.notification import Notification  # noqa: F401
            from app.models.wiki_article import WikiArticle  # noqa: F401
            from app.models.wiki_category import WikiCategory  # noqa: F401
            from app.models.wiki_feedback import WikiArticleFeedback  # noqa: F401
            from app.models.bad_word import BadWord  # noqa: F401
            from app.models.printer_profile import PrinterProfile  # noqa: F401
            from app.models.print_profile import PrintProfile  # noqa: F401
        except ImportError:
            pass
        
        # Get list of existing tables
        result = await db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """))
        existing_tables = {row[0] for row in result.fetchall()}
        
        # Get all tables from metadata
        all_tables = set(Base.metadata.tables.keys())

        # Find missing tables (excluding alembic_version)
        tables_to_create = all_tables - existing_tables - {'alembic_version'}
        
        if not tables_to_create:
            return True, "All tables already exist after applying migrations.", []
        
        # Create missing tables via SQLAlchemy metadata
        from app.db.session import engine
        
        async def create_tables_async():
            async with engine.begin() as conn:
                # Use run_sync to execute synchronous create_all
                await conn.run_sync(Base.metadata.create_all, checkfirst=True)
        
        await create_tables_async()
        
        # Verify that tables were actually created
        result = await db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """))
        new_existing_tables = {row[0] for row in result.fetchall()}
        actually_created = tables_to_create & new_existing_tables
        
        if actually_created:
            warning = " (WARNING: fallback method via metadata was used. Check ENUM types and indexes!)"
            return True, f"Tables created via fallback method: {len(actually_created)}{warning}", list(actually_created)
        else:
            return False, "Failed to create tables. Check logs for details.", []
    
    except Exception as e:
        logger.error(f"Table restoration error: {e}", exc_info=True)
        return False, f"Table restoration error: {str(e)}", []


async def apply_migration(revision: str = "head", applied_by: str | None = None) -> tuple[bool, str, Optional[str], Optional[list[str]]]:
    """
    Apply migration via Alembic with validation and history recording.

    Args:
        revision: Revision to apply ('head', '+1', '-1', or a specific revision)
        applied_by: Username of the person who applied the migration (optional)
    
    Returns:
        (success, message, current_revision, validation_errors)
    """
    try:
        config = get_alembic_config()
        
        # Determine which migrations will be applied
        # Need to get current revision and compute the target
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as pre_db:
            result = await pre_db.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            old_revision = row[0] if row else None
        
        # Run Alembic command synchronously (Alembic doesn't support async directly)
        # Use asyncio.to_thread for non-blocking execution
        def run_upgrade():
            command.upgrade(config, revision)
        
        await asyncio.to_thread(run_upgrade)
        
        # Get current revision after application
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            current_revision = row[0] if row else None
            
            # Record all applied migrations in history
            if current_revision and current_revision != old_revision:
                from alembic.script import ScriptDirectory
                script = ScriptDirectory.from_config(config)
                applied_revisions = []
                
                # Find all migrations between old_revision and current_revision
                if old_revision:
                    # Build path from old to new revision via down_revision chain
                    # Start from current_revision and go back to old_revision
                    path = []
                    current = current_revision
                    visited = set()
                    
                    while current and current not in visited:
                        visited.add(current)
                        path.append(current)
                        
                        if current == old_revision:
                            # Found the start of path, reverse the list
                            applied_revisions = list(reversed(path))
                            break
                        
                        try:
                            rev = script.get_revision(current)
                            if rev and rev.down_revision:
                                if isinstance(rev.down_revision, tuple):
                                    # Merge - take the first branch
                                    current = rev.down_revision[0] if rev.down_revision[0] else None
                                else:
                                    current = rev.down_revision
                            else:
                                break
                        except Exception:
                            break
                    
                    # If path not found, just record the current one
                    if not applied_revisions:
                        applied_revisions = [current_revision]
                else:
                    # If there was no old revision, record the current one
                    applied_revisions = [current_revision]
                
                # Record all applied migrations
                for rev in applied_revisions:
                    await _record_migration_application(db, rev, applied_by)
        
        # Validation after migration application
        async with AsyncSessionLocal() as validation_db:
            is_valid, missing_tables = await validate_migration_integrity(validation_db)
            
            if not is_valid:
                warning_msg = f"Migration {revision} applied, but issues detected: missing tables {', '.join(missing_tables)}"
                logger.warning(warning_msg)
                return True, f"Migration {revision} applied. WARNING: {warning_msg}", current_revision, missing_tables
        
        return True, f"Migration {revision} applied and verified successfully", current_revision, None
    
    except Exception as e:
        logger.error(f"Migration application error {revision}: {e}", exc_info=True)
        return False, f"Migration application error: {str(e)}", None, None


async def downgrade_migration(revision: str = "-1", downgraded_by: str | None = None) -> tuple[bool, str, Optional[str]]:
    """
    Downgrade migration via Alembic with history recording.

    Args:
        revision: Revision to downgrade to ('-1', 'base', or a specific revision)
        downgraded_by: Username of the person who downgraded the migration (optional)

    Returns:
        (success, message, current_revision)
    """
    try:
        config = get_alembic_config()

        # Get current revision before downgrade
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as pre_db:
            result = await pre_db.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            old_revision = row[0] if row else None

        def run_downgrade():
            command.downgrade(config, revision)

        await asyncio.to_thread(run_downgrade)

        # Get current revision after downgrade
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            current_revision = row[0] if row else None

            # Record downgrade in history
            if old_revision and old_revision != current_revision:
                await _record_migration_downgrade(db, old_revision, downgraded_by)

        return True, f"Migration successfully downgraded to {revision}", current_revision

    except Exception as e:
        logger.error(f"Migration downgrade error to {revision}: {e}", exc_info=True)
        return False, f"Migration downgrade error: {str(e)}", None


async def stamp_migration(revision: str = "head", stamped_by: str | None = None) -> tuple[bool, str, Optional[str]]:
    """
    Stamp migration as applied WITHOUT executing SQL.

    Useful when:
    - Migration was partially applied (enum created, but table wasn't)
    - Need to synchronize alembic_version state with actual DB
    - Database was created manually and migrations need to be marked as applied

    Args:
        revision: Revision to stamp ('head' or a specific revision)
        stamped_by: Username (optional)

    Returns:
        (success, message, current_revision)
    """
    try:
        config = get_alembic_config()

        def run_stamp():
            command.stamp(config, revision)

        await asyncio.to_thread(run_stamp)

        # Get current revision after stamp
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            current_revision = row[0] if row else None

            # Record in history
            if current_revision:
                await _record_migration_application(db, current_revision, stamped_by)

        return True, f"Migration {revision} stamped as applied (without executing SQL)", current_revision

    except Exception as e:
        logger.error(f"Migration stamp error {revision}: {e}", exc_info=True)
        return False, f"Migration stamp error: {str(e)}", None


async def list_database_dumps() -> list[dict]:
    """
    Get list of all database dumps.

    Returns:
        List of dicts with dump info: filename, size, created_at, format
    """
    try:
        dumps_dir = Path(settings.UPLOAD_DIR) / "database_dumps"
        if not dumps_dir.exists():
            return []
        
        dumps = []
        for file_path in dumps_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                filename = file_path.name
                
                # Determine format by extension
                if filename.endswith('.dump'):
                    format_type = 'custom'
                elif filename.endswith('.sql'):
                    format_type = 'plain'
                elif filename.endswith('.tar'):
                    format_type = 'tar'
                else:
                    format_type = 'unknown'
                
                dumps.append({
                    "filename": filename,
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "format": format_type,
                })
        
        # Sort by creation date (newest first)
        dumps.sort(key=lambda x: x["created_at"], reverse=True)
        return dumps
    
    except Exception as e:
        logger.error(f"Error getting dump list: {e}", exc_info=True)
        return []


async def delete_database_dump(filename: str) -> tuple[bool, str]:
    """
    Delete a database dump file.

    Args:
        filename: Dump file name
    
    Returns:
        (success, message)
    """
    try:
        dumps_dir = Path(settings.UPLOAD_DIR) / "database_dumps"
        dump_file = dumps_dir / filename
        
        # Check that file exists and is in the correct directory
        if not dump_file.exists():
            return False, f"Dump file not found: {filename}"

        # Check that the file is actually in the dumps directory (security)
        if not str(dump_file).startswith(str(dumps_dir.resolve())):
            return False, "Invalid file path"

        # Delete the file
        dump_file.unlink()
        
        return True, f"Dump file {filename} deleted successfully"
    
    except Exception as e:
        logger.error(f"Error deleting dump {filename}: {e}", exc_info=True)
        return False, f"Deletion error: {str(e)}"


async def get_database_stats(db: AsyncSession) -> dict:
    """Get database statistics."""
    # Get database name
    db_name_result = await db.execute(text("SELECT current_database()"))
    db_name = db_name_result.scalar()
    
    # Get database size
    size_result = await db.execute(
        text("SELECT pg_size_pretty(pg_database_size(current_database())) as size, "
             "pg_database_size(current_database()) as size_bytes")
    )
    size_row = size_result.fetchone()
    db_size = size_row[0] if size_row else "0 bytes"
    db_size_bytes = size_row[1] if size_row else 0
    
    # Get table statistics
    tables_result = await db.execute(
        text("""
            SELECT 
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
                pg_total_relation_size(schemaname||'.'||tablename) AS size_bytes,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_schema = schemaname AND table_name = tablename
                ) AS column_count
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
        """)
    )
    
    table_stats = []
    for row in tables_result.fetchall():
        # Get row count for table
        # Safe use of table names (they come from pg_tables, so they're safe)
        schema_name = row[0].replace('"', '""')
        table_name = row[1].replace('"', '""')
        count_result = await db.execute(
            text(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"')
        )
        row_count = count_result.scalar() or 0
        
        table_stats.append({
            "schema": row[0],
            "table": row[1],
            "size": row[2],
            "size_bytes": row[3],
            "column_count": row[4],
            "row_count": row_count,
        })
    
    return {
        "database_name": db_name,
        "database_size": db_size,
        "database_size_bytes": db_size_bytes,
        "table_stats": table_stats,
    }


async def export_database(
    format: str = "custom",
    include_data: bool = True,
    tables: Optional[list[str]] = None,
) -> tuple[bool, str, Optional[str], Optional[int]]:
    """
    Export database via pg_dump.

    Args:
        format: Export format ('custom', 'plain', 'tar')
        include_data: Include data (True) or schema only (False)
        tables: List of tables to export (None = all tables)
    
    Returns:
        (success, message, filename, size)
    """
    try:
        # Parse DATABASE_URL to get connection parameters
        from urllib.parse import urlparse
        parsed = urlparse(settings.DATABASE_URL.replace("+asyncpg", ""))
        
        db_name = parsed.path.lstrip("/")
        db_user = parsed.username
        db_password = parsed.password
        db_host = parsed.hostname or "localhost"
        db_port = parsed.port or 5432
        
        # Create dumps directory if it doesn't exist
        dumps_dir = Path(settings.UPLOAD_DIR) / "database_dumps"
        dumps_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if format == "custom":
            ext = ".dump"
        elif format == "plain":
            ext = ".sql"
        elif format == "tar":
            ext = ".tar"
        else:
            ext = ".dump"
        
        filename = f"filamenthub_backup_{timestamp}{ext}"
        filepath = dumps_dir / filename
        
        # Build pg_dump command
        cmd = [
            "pg_dump",
            "-h", db_host,
            "-p", str(db_port),
            "-U", db_user,
            "-d", db_name,
            "-F", format[0],  # 'c' for custom, 'p' for plain, 't' for tar
        ]
        
        if not include_data:
            cmd.append("--schema-only")
        
        if tables:
            for table in tables:
                cmd.extend(["-t", table])
        
        # Set environment variable for password
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password
        
        # Execute export
        def run_export():
            with open(filepath, "wb") as f:
                process = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    env=env,
                    check=True,
                )
                return process.returncode == 0
        
        success = await asyncio.to_thread(run_export)
        
        if success:
            size = filepath.stat().st_size
            return True, f"Database exported successfully", filename, size
        else:
            return False, "Database export error", None, None
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Database export error: {e.stderr.decode()}", exc_info=True)
        return False, f"Export error: {e.stderr.decode()}", None, None
    except Exception as e:
        logger.error(f"Database export error: {e}", exc_info=True)
        return False, f"Export error: {str(e)}", None, None


async def import_database(
    filepath: str,
    format: str = "custom",
    clean: bool = False,
    create: bool = False,
) -> tuple[bool, str]:
    """
    Import database via pg_restore or psql.

    Args:
        filepath: Path to the dump file
        format: Import format ('custom', 'plain', 'tar')
        clean: Clean database before import
        create: Create database if it doesn't exist
    
    Returns:
        (success, message)
    """
    try:
        # Parse DATABASE_URL
        from urllib.parse import urlparse
        parsed = urlparse(settings.DATABASE_URL.replace("+asyncpg", ""))
        
        db_name = parsed.path.lstrip("/")
        db_user = parsed.username
        db_password = parsed.password
        db_host = parsed.hostname or "localhost"
        db_port = parsed.port or 5432
        
        # Check file existence
        dump_file = Path(settings.UPLOAD_DIR) / "database_dumps" / filepath
        if not dump_file.exists():
            return False, f"Dump file not found: {filepath}"
        
        # Build command depending on format
        if format == "plain":
            # For plain format, use psql
            cmd = [
                "psql",
                "-h", db_host,
                "-p", str(db_port),
                "-U", db_user,
                "-d", db_name,
                "-f", str(dump_file),
            ]
        else:
            # For custom and tar formats, use pg_restore
            cmd = [
                "pg_restore",
                "-h", db_host,
                "-p", str(db_port),
                "-U", db_user,
                "-d", db_name,
            ]
            
            if clean:
                cmd.append("--clean")
            
            if create:
                cmd.append("--create")
            
            cmd.append(str(dump_file))
        
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password
        
        def run_import():
            try:
                process = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    check=True,
                    timeout=300,  # 5 minute timeout for large dumps
                )
                return True, process.stdout.decode() if process.stdout else "Database imported successfully"
            except subprocess.TimeoutExpired:
                return False, "Import timeout: operation took too long (>5 minutes)"
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode() if e.stderr else str(e)
                logger.error(f"Import error: {error_msg}")
                return False, f"Import error: {error_msg[:500]}"  # Limit message length
            except Exception as e:
                logger.error(f"Unexpected import error: {e}", exc_info=True)
                return False, f"Import error: {str(e)}"
        
        success, result_message = await asyncio.to_thread(run_import)
        
        if success:
            return True, result_message if isinstance(result_message, str) else "Database imported successfully"
        else:
            return False, result_message if isinstance(result_message, str) else "Database import error"
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Database import error: {e.stderr.decode()}", exc_info=True)
        return False, f"Import error: {e.stderr.decode()}"
    except Exception as e:
        logger.error(f"Database import error: {e}", exc_info=True)
        return False, f"Import error: {str(e)}"


async def get_table_structure(db: AsyncSession, table_name: str, schema_name: str = "public") -> dict:
    """Get table structure (columns, indexes, constraints)."""

    # Get column information
    columns_result = await db.execute(
        text("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = :schema_name AND table_name = :table_name
            ORDER BY ordinal_position
        """),
        {"schema_name": schema_name, "table_name": table_name}
    )
    
    columns = []
    for row in columns_result.fetchall():
        columns.append({
            "column_name": row[0],
            "data_type": row[1],
            "is_nullable": row[2] == "YES",
            "column_default": row[3],
            "character_maximum_length": row[4],
        })
    
    # Get index information
    indexes_result = await db.execute(
        text("""
            SELECT 
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = :schema_name AND tablename = :table_name
        """),
        {"schema_name": schema_name, "table_name": table_name}
    )
    
    indexes = []
    for row in indexes_result.fetchall():
        indexes.append({
            "name": row[0],
            "definition": row[1],
        })
    
    # Получаем информацию об ограничениях
    constraints_result = await db.execute(
        text("""
            SELECT 
                constraint_name,
                constraint_type
            FROM information_schema.table_constraints
            WHERE table_schema = :schema_name AND table_name = :table_name
        """),
        {"schema_name": schema_name, "table_name": table_name}
    )
    
    constraints = []
    for row in constraints_result.fetchall():
        constraints.append({
            "name": row[0],
            "type": row[1],
        })
    
    return {
        "table_name": table_name,
        "schema_name": schema_name,
        "columns": columns,
        "indexes": indexes,
        "constraints": constraints,
    }


async def get_table_data(
    db: AsyncSession,
    table_name: str,
    schema_name: str = "public",
    page: int = 1,
    size: int = 50,
    order_by: Optional[str] = None,
    order_desc: bool = False,
    search: Optional[str] = None,
) -> dict:
    """Получить данные из таблицы с пагинацией."""
    
    # Безопасное имя таблицы (защита от SQL injection)
    safe_table_name = table_name.replace('"', '""')
    safe_schema_name = schema_name.replace('"', '""')
    qualified_table = f'"{safe_schema_name}"."{safe_table_name}"'
    
    # Получаем список колонок
    columns_result = await db.execute(
        text(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema_name AND table_name = :table_name
            ORDER BY ordinal_position
        """),
        {"schema_name": schema_name, "table_name": table_name}
    )
    columns = [row[0] for row in columns_result.fetchall()]
    
    if not columns:
        raise ValueError(f"Table {schema_name}.{table_name} not found or has no columns")
    
    # Строим WHERE для поиска
    where_clause = ""
    search_params = {}
    if search:
        # Поиск по всем текстовым колонкам
        search_conditions = []
        for col in columns:
            search_conditions.append(f'CAST("{col}" AS TEXT) ILIKE :search')
        where_clause = "WHERE " + " OR ".join(search_conditions)
        search_params["search"] = f"%{search}%"
    
    # Строим ORDER BY
    order_clause = ""
    if order_by and order_by in columns:
        safe_order_by = order_by.replace('"', '""')
        order_clause = f'ORDER BY "{safe_order_by}" {"DESC" if order_desc else "ASC"}'
    
    # Подсчет общего количества строк
    count_query = text(f'SELECT COUNT(*) FROM {qualified_table} {where_clause}')
    count_result = await db.execute(count_query, search_params)
    total = count_result.scalar() or 0
    
    # Получение данных с пагинацией
    offset = (page - 1) * size
    data_query = text(f'SELECT * FROM {qualified_table} {where_clause} {order_clause} LIMIT :limit OFFSET :offset')
    data_params = {**search_params, "limit": size, "offset": offset}
    data_result = await db.execute(data_query, data_params)
    
    # Преобразуем строки в словари
    rows = []
    for row in data_result.fetchall():
        row_dict = {}
        for i, col in enumerate(columns):
            value = row[i]
            # Преобразуем специальные типы в строки для JSON
            if isinstance(value, datetime):
                value = value.isoformat()
            elif hasattr(value, '__dict__'):
                value = str(value)
            row_dict[col] = value
        rows.append(row_dict)
    
    pages = math.ceil(total / size) if total > 0 else 0
    
    return {
        "table_name": table_name,
        "schema_name": schema_name,
        "columns": columns,
        "rows": rows,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }

