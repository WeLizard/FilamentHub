"""The OrcaSlicer parent a FilamentHub material is exported on.

A managed filament profile carries its own values; the parent only fills what
the profile leaves out and decides which printers OrcaSlicer offers it for.
Every parent is therefore one of OrcaSlicer's universal library presets
(``OrcaFilamentLibrary``), which every installation has and which binds to no
printer. The material decides which one: the closest library preset for its
base polymer and, where the library has one, for its variant (CF, HF, Silk).
"""

import logging
import re

logger = logging.getLogger(__name__)

# Generic filament presets shipped in OrcaSlicer's OrcaFilamentLibrary.
ORCA_LIBRARY_PARENTS = frozenset({
    "Generic ABS @System",
    "Generic ASA @System",
    "Generic BVOH @System",
    "Generic CoPE @System",
    "Generic EVA @System",
    "Generic HIPS @System",
    "Generic PA @System",
    "Generic PA-CF @System",
    "Generic PC @System",
    "Generic PCTG @System",
    "Generic PE @System",
    "Generic PE-CF @System",
    "Generic PETG @System",
    "Generic PETG HF @System",
    "Generic PETG-CF @System",
    "Generic PHA @System",
    "Generic PLA @System",
    "Generic PLA High Speed @System",
    "Generic PLA Matte @System",
    "Generic PLA Silk @System",
    "Generic PLA-CF @System",
    "Generic PP @System",
    "Generic PP-CF @System",
    "Generic PP-GF @System",
    "Generic PPA-CF @System",
    "Generic PPA-GF @System",
    "Generic PVA @System",
    "Generic SBS @System",
    "Generic TPU @System",
})

# A preset without a parent is not neutral in OrcaSlicer: it starts from the
# default filament, which is PLA, and a name containing "@" binds it to the
# printer named after that sign. An unrecognised material therefore gets the
# PLA parent explicitly.
UNKNOWN_MATERIAL_PARENT = "Generic PLA @System"

_CF = re.compile(r"\bCF|CF\b|CARBON")
_GF = re.compile(r"\bGF|GF\b|GLASS")

# Base polymer, most specific first. The first match decides; a later, broader
# rule never sees a material an earlier one recognised (PETG before PE, PPA
# before PA and PP, PC before ABS so that PC/ABS blends follow PC).
_BASE_RULES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), base)
    for pattern, base in (
        (r"\bCO ?PET?\b|\bCPE\b", "COPE"),
        (r"\bPCTG\b", "PCTG"),
        (r"\bPEBA|\bTPU|\bTPEE?\b|\bTPC\b|\bTPI\b|\bFLEX|\bPCL\b", "TPU"),
        (r"\b(?:PEI|PEEK|PEKK|PES|PPSU|PPS|PSU|PI)(?:\b|\d)", "HIGH_TEMP"),
        (r"\bPET", "PETG"),
        (r"\bPC(?:\b|CF|GF)", "PC"),
        (r"\bPPA", "PPA"),
        (r"\b(?:PA(?:\d+|HT)?|NYLON)(?:\b|CF|GF)", "PA"),
        (r"\bPP(?:\b|\+|CF|GF|PLUS)", "PP"),
        (r"\bPE(?:\b|CF|GF)", "PE"),
        (r"\bHIPS\b", "HIPS"),
        (r"\bABS", "ABS"),
        (r"\bASA", "ASA"),
        (r"\bEVA\b", "EVA"),
        (r"\bBVOH\b", "BVOH"),
        (r"\bPV[AB]\b", "PVA"),
        (r"\bPHA\b", "PHA"),
        (r"\bSBS\b", "SBS"),
        (r"PLA|\bSILK\b|\bMATTE\b|\bPOM\b|\bPVDF\b", "PLA"),
    )
)


def _parent_for_base(base: str, material: str) -> str:
    cf = bool(_CF.search(material))
    gf = bool(_GF.search(material))
    if base == "PLA":
        if cf:
            return "Generic PLA-CF @System"
        if re.search(r"\bSILK", material):
            return "Generic PLA Silk @System"
        if re.search(r"\bMATTE", material):
            return "Generic PLA Matte @System"
        if re.search(r"\bHS\b|HIGH ?SPEED", material):
            return "Generic PLA High Speed @System"
        return "Generic PLA @System"
    if base == "PETG":
        if cf:
            return "Generic PETG-CF @System"
        if re.search(r"\bHF\b|HF\b", material):
            return "Generic PETG HF @System"
        return "Generic PETG @System"
    if base == "PA":
        return "Generic PA-CF @System" if cf else "Generic PA @System"
    if base == "PPA":
        if cf:
            return "Generic PPA-CF @System"
        return "Generic PPA-GF @System" if gf else "Generic PA @System"
    if base == "PP":
        if cf:
            return "Generic PP-CF @System"
        return "Generic PP-GF @System" if gf else "Generic PP @System"
    if base == "PE":
        return "Generic PE-CF @System" if cf else "Generic PE @System"
    if base == "HIGH_TEMP":
        return "Generic PC @System"
    if base == "COPE":
        return "Generic CoPE @System"
    return f"Generic {base} @System"


def orca_parent_for_material(material_type: str | None, log_unknown: bool = True) -> str:
    """The OrcaSlicer library preset a filament of this material inherits from."""
    material = re.sub(r"[\s\-_/.,]+", " ", (material_type or "").upper()).strip()
    for pattern, base in _BASE_RULES:
        if pattern.search(material):
            return _parent_for_base(base, material)
    if log_unknown:
        logger.warning(
            "Unknown material type %r, using parent %r", material_type, UNKNOWN_MATERIAL_PARENT
        )
    return UNKNOWN_MATERIAL_PARENT
