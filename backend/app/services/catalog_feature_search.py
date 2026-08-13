"""Resolve translated catalog feature labels to their stored canonical codes."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.services.catalog_color_groups import (
    FilamentColorGroup,
    resolve_color_group_aliases,
)


@dataclass(frozen=True)
class CatalogFeatureCodes:
    effects: tuple[str, ...] = ()
    additives: tuple[str, ...] = ()
    claims: tuple[str, ...] = ()
    color_groups: tuple[FilamentColorGroup, ...] = ()
    color_types: tuple[str, ...] = ()
    transparent: bool = False


_SEPARATORS = re.compile(r"[\W_]+", re.UNICODE)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    return _SEPARATORS.sub(" ", normalized).strip()


# These are search aliases, not display translations. They mirror the labels a
# person already sees in the three supported interfaces and keep a few common
# spelling variants so a visible label does not become an implementation code.
_FEATURE_LABELS: dict[str, dict[str, tuple[str, ...]]] = {
    "effects": {
        "wood": ("wood texture", "древесная текстура", "木纹"),
        "carbon": ("carbon texture", "карбоновая текстура", "碳纤纹理"),
        "glass": ("glass fibres", "glass fibers", "стеклянные волокна", "玻璃纤维"),
        "metallic": ("metallic", "металлик", "金属质感"),
        "luminescent": ("glow", "свечение", "夜光"),
        "glitter": ("glitter", "блестки", "闪粉"),
        "fibers": ("fibrous texture", "волокнистая текстура", "纤维纹理"),
        "stone": ("stone texture", "каменная текстура", "石纹"),
        "carbonaceous": ("carbon particles", "углеродные частицы", "碳颗粒"),
        "microspheres": ("microspheres", "микросферы", "微球"),
        "particles": ("fine particles", "мелкодисперсные частицы", "细颗粒"),
    },
    "additives": {
        "carbon_fiber": (
            "carbon fibre",
            "carbon fiber",
            "углеродное волокно",
            "углеволокно",
            "碳纤维",
        ),
        "glass_fiber": ("glass fibre", "glass fiber", "стекловолокно", "玻璃纤维"),
        "aramid_fiber": ("aramid fibre", "aramid fiber", "арамидное волокно", "芳纶纤维"),
        "basalt_fiber": ("basalt fibre", "basalt fiber", "базальтовое волокно", "玄武岩纤维"),
        "natural_fiber": ("natural fibre", "natural fiber", "натуральное волокно", "天然纤维"),
        "wood": ("wood flour", "древесная мука", "木粉"),
        "bamboo": ("bamboo fibre", "bamboo fiber", "бамбуковое волокно", "竹纤维"),
        "cork": ("cork", "пробка", "软木"),
        "metal_powder": ("metal powder", "металлический порошок", "金属粉末"),
        "mineral": ("mineral filler", "минеральный наполнитель", "矿物填料"),
        "ceramic": ("ceramic filler", "керамический наполнитель", "陶瓷填料"),
        "glass_beads": ("glass beads", "стеклянные микросферы", "玻璃微珠"),
        "carbon_nanotubes": ("carbon nanotubes", "углеродные нанотрубки", "碳纳米管"),
        "carbon_black": ("carbon black", "технический углерод", "炭黑"),
        "graphene": ("graphene", "графен", "石墨烯"),
        "hollow_spheres": ("hollow microspheres", "полые микросферы", "空心微球"),
        "ptfe": ("ptfe", "птфэ", "聚四氟乙烯"),
    },
    "claims": {
        "esd": ("esd safe", "esd безопасный", "防静电"),
        "electrically_conductive": ("electrically conductive", "электропроводящий", "导电"),
        "emi_shielding": ("emi shielding", "экранирование emi", "emi 屏蔽"),
        "flame_retardant": ("flame retardant", "огнестойкий", "阻燃"),
        "uv_resistant": ("uv resistant", "уф стойкий", "抗紫外线"),
        "wear_resistant": ("wear resistant", "износостойкий", "耐磨"),
        "low_friction": ("low friction", "низкое трение", "低摩擦"),
        "lightweight": ("lightweight", "облегченный", "轻量化"),
        "foaming": ("foaming", "вспениваемый", "可发泡"),
        "antimicrobial": ("antimicrobial", "антимикробный", "抗菌"),
        "food_contact": ("food contact", "для контакта с пищей", "食品接触"),
        "heat_resistant": ("heat resistant", "термостойкий", "耐热"),
        "chemical_resistant": ("chemical resistant", "химически стойкий", "耐化学品"),
        "magnetically_detectable": (
            "magnetically detectable",
            "магнитно обнаруживаемый",
            "可磁性检测",
        ),
    },
}

_NORMALIZED_LABELS = {
    kind: {code: tuple(_normalize(label) for label in labels) for code, labels in codes.items()}
    for kind, codes in _FEATURE_LABELS.items()
}

_TRANSPARENCY_LABELS = tuple(
    _normalize(label)
    for label in ("transparent", "translucent", "прозрачный", "полупрозрачный", "透明", "半透明")
)
_COLOR_TYPE_LABELS: dict[str, tuple[str, ...]] = {
    "two": ("two color", "two colour", "двухцветный", "双色"),
    "three": ("three color", "three colour", "трехцветный", "трёхцветный", "三色"),
    "gradient": ("gradient", "градиент", "渐变"),
    "transition": ("transition color", "transition colour", "переходный цвет", "过渡色"),
}
_MULTICOLOR_LABELS = tuple(
    _normalize(label)
    for label in (
        "multicolor",
        "multicolour",
        "multi color",
        "multi colour",
        "многоцветный",
        "多色",
    )
)
_NORMALIZED_COLOR_TYPE_LABELS = {
    color_type: tuple(_normalize(label) for label in labels)
    for color_type, labels in _COLOR_TYPE_LABELS.items()
}


def resolve_catalog_feature_codes(search: str) -> CatalogFeatureCodes:
    """Return every canonical feature whose visible label matches the query."""
    needle = _normalize(search)
    if not needle:
        return CatalogFeatureCodes()

    matched: dict[str, list[str]] = {"effects": [], "additives": [], "claims": []}
    for kind, codes in _NORMALIZED_LABELS.items():
        for code, labels in codes.items():
            if any(label in needle or (len(needle) >= 3 and needle in label) for label in labels):
                matched[kind].append(code)

    color_types = [
        color_type
        for color_type, labels in _NORMALIZED_COLOR_TYPE_LABELS.items()
        if any(label in needle or (len(needle) >= 3 and needle in label) for label in labels)
    ]
    if any(
        label in needle or (len(needle) >= 3 and needle in label) for label in _MULTICOLOR_LABELS
    ):
        color_types = ["two", "three", "gradient", "transition"]

    return CatalogFeatureCodes(
        effects=tuple(matched["effects"]),
        additives=tuple(matched["additives"]),
        claims=tuple(matched["claims"]),
        color_groups=resolve_color_group_aliases(search),
        color_types=tuple(color_types),
        transparent=any(
            label in needle or (len(needle) >= 3 and needle in label)
            for label in _TRANSPARENCY_LABELS
        ),
    )
