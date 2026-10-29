"""Codes of a filament's visual effects, finish, colour type, additives and claims.

Every input path (web form, catalog intake, Orca plugin, API) passes these
values through the schema normalisers, which map a known spelling in any
supported language, or an abbreviation, to its code: "стекловолокно",
"glass fibre" and "GF" are one additive. An unknown value keeps its normalised
spelling; the endpoints decide who may store custom codes.

Spellings are matched per kind, so "glass" is the glass-fibre look among
effects and nothing among additives. A word whose meaning depends on context
("carbon" may be carbon fibre or carbon black, "colour change" may be angle,
UV or heat) is deliberately absent. Catalog search reuses these spellings.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

FeatureKind = Literal["effect", "finish", "color_type", "additive", "claim"]

_LEGACY_PATTERNS = {f"pattern{index}": () for index in range(1, 13)}

EFFECTS: dict[str, tuple[str, ...]] = {
    "none": (),
    "wood": ("wood texture", "древесная текстура", "под дерево", "木纹"),
    "carbon": ("carbon texture", "карбоновая текстура", "碳纤纹理"),
    "glass": ("glass fibres", "glass fibers", "стеклянные волокна", "玻璃纤维"),
    "metallic": ("metal", "metal look", "metallic look", "металлик", "金属质感", "金属色"),
    "luminescent": (
        "glow",
        "glow in the dark",
        "glowing",
        "luminous",
        "phosphorescent",
        "свечение",
        "светящийся",
        "светится в темноте",
        "светящийся в темноте",
        "люминесцентный",
        "夜光",
    ),
    "glitter": (
        "sparkle",
        "sparkling",
        "galaxy",
        "stardust",
        "starlight",
        "twinkling",
        "блестки",
        "с блестками",
        "мерцающий",
        "闪粉",
        "闪光",
        "闪耀",
    ),
    "fibers": ("fibrous texture", "волокнистая текстура", "纤维纹理"),
    "stone": (
        "stone look",
        "stone texture",
        "marble",
        "marble look",
        "rock",
        "granite",
        "каменная текстура",
        "под камень",
        "мрамор",
        "мраморный",
        "гранит",
        "石纹",
        "大理石",
    ),
    "carbonaceous": ("carbon particles", "углеродные частицы", "碳颗粒"),
    "microspheres": ("микросферы", "微球"),
    "particles": ("fine particles", "мелкодисперсные частицы", "细颗粒"),
    "pearlescent": ("pearl", "pearly", "nacreous", "перламутр", "перламутровый", "珠光"),
    "color_shift": (
        "colour shift",
        "chameleon",
        "angle shift",
        "хамелеон",
        "变色龙",
    ),
    "fluorescent": (
        "neon",
        "neon fluorescent",
        "fluo",
        "флуоресцентный",
        "флюоресцентный",
        "неон",
        "неоновый",
        "荧光",
    ),
    "uv_reactive": ("uv reactive", "blacklight", "уф реактивный", "реагирует на уф"),
    "photochromic": (
        "uv colour change",
        "uv color change",
        "uv shift",
        "sun reactive",
        "фотохромный",
        "光变",
        "光致变色",
    ),
    **_LEGACY_PATTERNS,
}

FINISHES: dict[str, tuple[str, ...]] = {
    "matte": ("matt", "mat", "матовый", "мат", "哑光"),
    "glossy": ("gloss", "shiny", "глянцевый", "глянец", "亮光", "光面"),
    "satin": ("semi matte", "semi gloss", "сатин", "сатиновый", "полуматовый", "缎面"),
    "silk": ("silky", "silk shine", "шелк", "шелковый", "丝绸", "丝光"),
}

COLOR_TYPES: dict[str, tuple[str, ...]] = {
    "single": ("solid", "mono", "monochrome", "одноцветный", "单色"),
    "two": (
        "2 color",
        "2 colour",
        "dual",
        "dual color",
        "dual colour",
        "two color",
        "two colour",
        "bicolor",
        "двухцветный",
        "双色",
    ),
    "three": (
        "3 color",
        "3 colour",
        "tri",
        "tri color",
        "tri colour",
        "three color",
        "three colour",
        "tricolor",
        "трехцветный",
        "三色",
    ),
    "four": ("4 color", "4 colour", "quad", "four color", "four colour", "четырехцветный", "四色"),
    "gradient": ("градиент", "градиентный", "渐变"),
    "transition": (
        "rainbow",
        "transition color",
        "transition colour",
        "переходный",
        "переходный цвет",
        "радужный",
        "过渡色",
        "彩虹",
    ),
    "thermochromic": (
        "temperature color changing",
        "temperature colour changing",
        "heat color change",
        "термохромный",
        "温变",
    ),
}

ADDITIVES: dict[str, tuple[str, ...]] = {
    "active_foaming_agent": ("foaming agent", "вспениватель"),
    "antimicrobial_additives": ("antibacterial additive", "антибактериальная добавка"),
    "antioxidants_heat_stabilizers": ("heat stabilizer", "термостабилизатор"),
    "aramid_fiber": (
        "aramid",
        "aramid fibre",
        "kevlar",
        "арамид",
        "арамидное волокно",
        "кевлар",
        "芳纶纤维",
        "芳纶",
    ),
    "bamboo": ("bamboo fibre", "bamboo fiber", "бамбук", "бамбуковое волокно", "竹纤维"),
    "basalt_fiber": ("basalt", "basalt fibre", "базальт", "базальтовое волокно", "玄武岩纤维"),
    "bismuth_fill": ("bismuth", "висмут"),
    "carbon_black": ("технический углерод", "сажа", "炭黑"),
    "carbon_fiber": (
        "cf",
        "carbon fibre",
        "carbon fiber",
        "углеволокно",
        "углеродное волокно",
        "карбоновое волокно",
        "碳纤维",
        "碳纤",
    ),
    "carbon_nanotubes": ("cnt", "углеродные нанотрубки", "碳纳米管"),
    "ceramic": ("ceramic filler", "керамика", "керамический наполнитель", "陶瓷填料", "陶瓷"),
    "chain_extenders": (),
    "compatibilizers": (),
    "cork": ("пробка", "软木"),
    "debinding_metal": ("metal injection", "bound metal", "для спекания"),
    "flame_retardant_additives": ("flame retardant additive", "антипирен"),
    "glass_beads": ("glass microspheres", "стеклянные микросферы", "玻璃微珠"),
    "glass_fiber": (
        "gf",
        "glass fibre",
        "glass fiber",
        "fiberglass",
        "fibreglass",
        "стекловолокно",
        "стеклонаполненный",
        "玻璃纤维",
        "玻纤",
    ),
    "graphene": ("графен", "石墨烯"),
    "hollow_spheres": ("hollow microspheres", "полые микросферы", "空心微球"),
    "impact_modifiers": ("impact modifier", "модификатор ударопрочности"),
    "laser_marking_additives": ("laser marking additive",),
    "metal_powder": (
        "metal",
        "metal fill",
        "metal filled",
        "iron",
        "steel",
        "copper",
        "bronze",
        "brass",
        "aluminium",
        "aluminum",
        "металл",
        "металлический порошок",
        "металлонаполненный",
        "金属粉末",
        "金属粉",
    ),
    "mineral": ("mineral filler", "минеральный наполнитель", "минерал", "矿物填料"),
    "natural_fiber": ("natural fibre", "natural fiber", "натуральное волокно", "天然纤维"),
    "nucleating_agents": ("nucleating agent",),
    "phosphor": ("люминофор", "荧光粉"),
    "ptfe": ("teflon", "птфэ", "тефлон", "聚四氟乙烯"),
    "tungsten_fill": ("tungsten", "вольфрам"),
    "uv_stabilizers_hals": ("uv stabilizer", "hals", "уф стабилизатор"),
    "wood": ("wood fill", "wood flour", "дерево", "древесная мука", "木粉"),
}

PROPERTY_CLAIMS: dict[str, tuple[str, ...]] = {
    "antimicrobial": ("antibacterial", "антимикробный", "антибактериальный", "抗菌"),
    "chemical_resistant": ("химически стойкий", "耐化学品"),
    "electrically_conductive": ("conductive", "электропроводящий", "токопроводящий", "导电"),
    "emi_shielding": ("emi", "экранирование emi", "emi 屏蔽"),
    "esd": ("esd safe", "antistatic", "anti static", "антистатический", "防静电"),
    "flame_retardant": ("fr", "fire retardant", "огнестойкий", "阻燃"),
    "food_contact": ("food safe", "food grade", "для контакта с пищей", "пищевой", "食品接触"),
    "foaming": ("вспениваемый", "可发泡"),
    "heat_resistant": ("high temperature", "high temp", "термостойкий", "耐热", "耐高温"),
    "lightweight": ("light weight", "облегченный", "轻量化"),
    "low_friction": ("низкое трение", "低摩擦"),
    "magnetically_detectable": ("magnetic", "магнитно обнаруживаемый", "магнитный", "可磁性检测"),
    "uv_resistant": ("uv stable", "uv resistance", "уф стойкий", "抗紫外线"),
    "wear_resistant": ("abrasion resistant", "износостойкий", "耐磨"),
}

_SPELLINGS: dict[FeatureKind, dict[str, tuple[str, ...]]] = {
    "effect": EFFECTS,
    "finish": FINISHES,
    "color_type": COLOR_TYPES,
    "additive": ADDITIVES,
    "claim": PROPERTY_CLAIMS,
}

_SEPARATORS = re.compile(r"[\W_]+", re.UNICODE)


def spelling_key(value: str) -> str:
    """Case-, accent-of-ё- and separator-insensitive form of a spelling."""
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    return _SEPARATORS.sub(" ", normalized).strip()


def _build_index(kind: FeatureKind) -> dict[str, str]:
    index: dict[str, str] = {}
    for code, spellings in _SPELLINGS[kind].items():
        for spelling in (code, *spellings):
            key = spelling_key(spelling)
            if index.get(key, code) != code:
                raise ValueError(f"{kind} spelling {spelling!r} is ambiguous")
            index[key] = code
    return index


_INDEX: dict[FeatureKind, dict[str, str]] = {kind: _build_index(kind) for kind in _SPELLINGS}


def known_codes(kind: FeatureKind) -> frozenset[str]:
    return frozenset(_SPELLINGS[kind])


def canonical_code(kind: FeatureKind, value: object) -> object:
    """The code a spelling stands for; other text is kept as a normalised code."""
    if not isinstance(value, str):
        return value
    code = _INDEX[kind].get(spelling_key(value))
    if code is not None:
        return code
    return spelling_key(value).replace(" ", "_")


def spellings(kind: FeatureKind) -> dict[str, tuple[str, ...]]:
    return _SPELLINGS[kind]
