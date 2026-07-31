"""Small, network-free G-code extrusion tracker used by the adapter hook."""

from __future__ import annotations

import re
from typing import Dict, Optional, Set, Tuple

_PARAM_RE = re.compile(r"(?:^|\s)([A-Z])\s*(-?(?:\d+(?:\.\d*)?|\.\d+))", re.IGNORECASE)


class ExtrusionTracker:
    """Track material pushed through each selected slot without blocking I/O."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.absolute_extrusion = True
        self.active_tool = 0
        self.positions: Dict[int, float] = {}
        self.retraction_debt: Dict[int, float] = {}
        self.used_length_by_slot: Dict[int, float] = {}

    @staticmethod
    def _params(command: str) -> Dict[str, float]:
        line = command.split(";", 1)[0].upper()
        return {name: float(value) for name, value in _PARAM_RE.findall(line)}

    def process(
        self,
        *,
        command: str,
        gcode: Optional[str],
        active_slot: Optional[int],
        map_tools_to_slots: bool,
        available_slots: Set[int],
    ) -> Tuple[Optional[int], float]:
        operation = (gcode or command.split(None, 1)[0]).upper()
        command_operation = command.split(None, 1)[0].upper()
        if command_operation.startswith("T") and command_operation[1:].isdigit():
            self.active_tool = int(command_operation[1:])
            mapped = self.active_tool if map_tools_to_slots else active_slot
            return mapped if mapped in available_slots else active_slot, 0.0
        if operation == "M82":
            self.absolute_extrusion = True
            return active_slot, 0.0
        if operation == "M83":
            self.absolute_extrusion = False
            return active_slot, 0.0
        if operation == "G92":
            params = self._params(command)
            if "E" in params:
                self.positions[self.active_tool] = params["E"]
            return active_slot, 0.0
        if operation not in {"G0", "G00", "G1", "G01", "G2", "G02", "G3", "G03"}:
            return active_slot, 0.0

        params = self._params(command)
        if "E" not in params:
            return active_slot, 0.0
        raw_e = params["E"]
        previous = self.positions.get(self.active_tool, 0.0)
        delta = raw_e if not self.absolute_extrusion else raw_e - previous
        if self.absolute_extrusion:
            self.positions[self.active_tool] = raw_e

        debt = self.retraction_debt.get(self.active_tool, 0.0)
        if delta < 0:
            self.retraction_debt[self.active_tool] = debt + abs(delta)
            return active_slot, 0.0
        if delta <= 0:
            return active_slot, 0.0
        recovered = min(debt, delta)
        consumed = delta - recovered
        self.retraction_debt[self.active_tool] = debt - recovered
        slot = self.active_tool if map_tools_to_slots else active_slot
        if consumed > 0 and slot is not None and slot in available_slots:
            self.used_length_by_slot[slot] = (
                self.used_length_by_slot.get(slot, 0.0) + consumed
            )
            return slot, consumed
        return active_slot, 0.0
