"""Small, network-free G-code extrusion tracker used by the adapter hook."""

from __future__ import annotations

import re
from typing import Dict, Optional, Set, Tuple

_PARAM_RE = re.compile(r"(?:^|\s)([A-Z])\s*(-?(?:\d+(?:\.\d*)?|\.\d+))", re.IGNORECASE)
_TOOL_RE = re.compile(r"^\s*T\s*(\d+)(?:\s|$)", re.IGNORECASE)


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
        self.seen_tools: Set[int] = set()
        self.unmapped_tools: Set[int] = set()

    def drain_usage(self) -> Dict[int, float]:
        """Return checkpoint deltas without losing extrusion-mode/tool state."""
        usage = dict(self.used_length_by_slot)
        self.used_length_by_slot = {}
        return usage

    def _slot_for_tool(
        self,
        *,
        active_slot: Optional[int],
        map_tools_to_slots: bool,
        tool_slot_map: Optional[Dict[int, int]],
        available_slots: Set[int],
    ) -> Optional[int]:
        if not map_tools_to_slots:
            return active_slot
        mapped = (
            tool_slot_map.get(self.active_tool)
            if tool_slot_map is not None
            else self.active_tool
        )
        if mapped not in available_slots:
            self.unmapped_tools.add(self.active_tool)
            return None
        self.unmapped_tools.discard(self.active_tool)
        return mapped

    @staticmethod
    def _params(command: str) -> Dict[str, float]:
        line = command.split(";", 1)[0].upper()
        return {name: float(value) for name, value in _PARAM_RE.findall(line)}

    @staticmethod
    def tool_index(command: str, gcode: Optional[str]) -> Optional[int]:
        """Return a standard OctoPrint Tn selection, if this command is one."""
        if (gcode or "").upper() != "T":
            return None
        match = _TOOL_RE.match(command.split(";", 1)[0])
        return int(match.group(1)) if match else None

    def process(
        self,
        *,
        command: str,
        gcode: Optional[str],
        active_slot: Optional[int],
        map_tools_to_slots: bool,
        available_slots: Set[int],
        tool_slot_map: Optional[Dict[int, int]] = None,
    ) -> Tuple[Optional[int], float]:
        operation = (gcode or command.split(None, 1)[0]).upper()
        tool_index = self.tool_index(command, gcode)
        if tool_index is not None:
            self.active_tool = tool_index
            self.seen_tools.add(self.active_tool)
            return (
                self._slot_for_tool(
                    active_slot=active_slot,
                    map_tools_to_slots=map_tools_to_slots,
                    tool_slot_map=tool_slot_map,
                    available_slots=available_slots,
                ),
                0.0,
            )
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
        self.seen_tools.add(self.active_tool)
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
        slot = self._slot_for_tool(
            active_slot=active_slot,
            map_tools_to_slots=map_tools_to_slots,
            tool_slot_map=tool_slot_map,
            available_slots=available_slots,
        )
        if consumed > 0 and slot is not None and slot in available_slots:
            self.used_length_by_slot[slot] = (
                self.used_length_by_slot.get(slot, 0.0) + consumed
            )
            return slot, consumed
        return slot, 0.0
