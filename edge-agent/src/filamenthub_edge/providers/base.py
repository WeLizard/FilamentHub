"""Provider contract used by every Edge packaging surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderSnapshot:
    printer: dict[str, Any]
    slots: list[dict[str, Any]]
    slot_topology_complete: bool
    capabilities: list[str]


class EdgeProvider(Protocol):
    def observe(self) -> ProviderSnapshot: ...

    def capabilities(self) -> list[str]: ...
