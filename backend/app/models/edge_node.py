"""Edge nodes that belong to an account, independent of any printer."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class EdgeNode(Base):
    """One installed Edge: a kit, a Linux service, a container or an add-on.

    A node is registered once and may later carry readers and printer
    connections. It is not a printer and owns no printer data by itself.
    """

    __tablename__ = "edge_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Hardware profile of a kit; empty for software installations.
    kit_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # What the node calls itself. Informational: never proof of ownership.
    node_instance_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EdgeNodeCredential(Base):
    """The node's own secret, kept as a SHA-256 digest.

    The node generates the secret and stores it before pairing; the server
    never has it in the clear after the request that activates it.
    """

    __tablename__ = "edge_node_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("edge_nodes.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    credential_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EdgeNodePairing(Base):
    """A short-lived one-time code that lets one node join one account.

    Once used, the row remembers which secret used it, so the same node can
    repeat a request whose answer was lost without the code working for
    anybody else.
    """

    __tablename__ = "edge_node_pairings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Set from the start when an existing node is being linked again, and at
    # activation for a new one.
    node_id: Mapped[int | None] = mapped_column(
        ForeignKey("edge_nodes.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    kit_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proof_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
