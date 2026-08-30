#!/usr/bin/env python3
"""Create a small, coherent FilamentHub showcase in the local dev database.

Unlike ``seed_dev_volume.py``, this script is intended for product walkthroughs,
Wiki screenshots, and manual UX checks. It creates a stable set of fictional
brands, materials, people, presets, reviews, spools, printers, calculations,
and orders. Re-running it updates the same records instead of adding duplicates.
Rows created by the volume seed are kept in the database but deactivated so
they do not flood the human-facing dev catalogue.

The script never deletes rows and refuses any database that is not both local
and explicitly named as a development database.

Run from the repository root (PowerShell example)::

    $env:POSTGRES_HOST='localhost'
    $env:POSTGRES_PORT='5433'
    $env:POSTGRES_DB='filamenthub_dev'
    $env:POSTGRES_USER='filamenthub'
    $env:POSTGRES_PASSWORD='devpass123'
    python scripts/seed_dev_showcase.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

_repository_backend = Path(__file__).resolve().parent.parent / "backend"
BACKEND_DIR = _repository_backend if _repository_backend.is_dir() else Path.cwd()
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")

LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres-dev"}
SHOWCASE_PASSWORD = "qwerty123"
SHOWCASE_SOURCE = "dev_showcase"


BRAND_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "name": "OlgaCraft",
        "slug": "olgacraft",
        "currency": "RUB",
        "verified": True,
        "logo_bg": "#20143D",
        "description": (
            "Независимая мастерская материалов для прототипов, декора и "
            "функциональных изделий. OlgaCraft публикует проверяемые карточки "
            "материалов и рабочие отправные настройки для 3D-печати."
        ),
        "website": "https://olgacraft.example",
        "social_media_urls": [],
        "shop_links": [],
    },
    {
        "name": "FibraCraft",
        "slug": "fibracraft",
        "currency": "EUR",
        "verified": True,
        "logo_bg": "#172554",
        "description": "Декоративные и армированные материалы для выразительных деталей.",
    },
    {
        "name": "NorthLayer",
        "slug": "northlayer",
        "currency": "EUR",
        "verified": True,
        "logo_bg": "#083344",
        "description": "Практичные материалы для прототипов, мастерской и наружных изделий.",
    },
    {
        "name": "PolyForge",
        "slug": "polyforge",
        "currency": "USD",
        "verified": False,
        "logo_bg": "#292524",
        "description": "Инженерные пластики для функциональных деталей и оснастки.",
    },
    {
        "name": "LumiLayer",
        "slug": "lumilayer",
        "currency": "EUR",
        "verified": False,
        "logo_bg": "#3B0764",
        "description": "Световые, прозрачные и шелковые материалы для творческой печати.",
    },
    {
        "name": "PrismWeave",
        "slug": "prismweave",
        "currency": "EUR",
        "verified": True,
        "logo_bg": "#312E81",
        "description": "Colour-shifting and tactile filaments for expressive objects and studio work.",
    },
    {
        "name": "ForgeNest",
        "slug": "forgenest",
        "currency": "EUR",
        "verified": True,
        "logo_bg": "#3F3F46",
        "description": "Engineering filaments for durable fixtures, housings and workshop parts.",
    },
    {
        "name": "TerraLoop",
        "slug": "terraloop",
        "currency": "EUR",
        "verified": False,
        "logo_bg": "#14532D",
        "description": "Recycled and natural-filled materials with practical, understated colours.",
    },
)


def visual(
    color: str,
    *,
    finish: str = "matte",
    filler: str = "none",
    effects: list[str] | None = None,
    color_type: str = "single",
    colors: list[str] | None = None,
    transparency: bool = False,
) -> dict[str, Any]:
    return {
        "color_type": color_type,
        "colors": colors or [color],
        "finish": finish,
        "filler": filler,
        "effects": effects or ([] if filler == "none" else [filler]),
        "transparency": transparency,
    }


FILAMENT_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "brand": "OlgaCraft", "line": "Everyday PLA", "slug": "pla-ocean-blue",
        "name": "Everyday PLA · Deep Ocean", "material_type": "PLA", "preset_name": "Универсальный",
        "color_name": "Глубокий океан", "color_hex": "#0E5BD8", "ral_code": "5017",
        "density": 1.24, "price_per_kg": 1890.0, "spool_weight": 1000.0,
        "empty_spool_weight_g": 218.0, "nozzle": (200, 220), "bed": (50, 60),
        "visual_settings": visual("#0E5BD8", finish="glossy"),
        "description": "Универсальный насыщенно-синий PLA для прототипов и готовых изделий.",
        "views_count": 438, "scans_count": 67,
    },
    {
        "brand": "OlgaCraft", "line": "Satin PLA", "slug": "pla-satin-red",
        "name": "Satin PLA · Coral", "material_type": "PLA", "preset_name": "Ровный сатин",
        "color_name": "Коралловый сатин", "color_hex": "#E95662", "ral_code": "3016",
        "density": 1.24, "price_per_kg": 1990.0, "spool_weight": 1000.0,
        "empty_spool_weight_g": 221.0, "nozzle": (205, 225), "bed": (50, 60),
        "visual_settings": visual("#E95662", finish="glossy"),
        "description": "Мягкий сатиновый блеск без выраженного металлического эффекта.",
        "views_count": 386, "scans_count": 51,
    },
    {
        "brand": "OlgaCraft", "line": "Timber Blend", "slug": "pla-wood-warm-grey",
        "name": "Timber Blend · Birch", "material_type": "PLA", "preset_name": "Выразительная текстура",
        "color_name": "Светлая берёза", "color_hex": "#C5A77B",
        "density": 1.18, "price_per_kg": 2290.0, "spool_weight": 750.0,
        "empty_spool_weight_g": 186.0, "nozzle": (195, 215), "bed": (45, 60),
        "visual_settings": visual("#C5A77B", filler="wood"),
        "additives": [{"code": "wood", "content_percent": 15.0, "content_basis": "weight"}],
        "description": "PLA с древесным наполнением для декора и интерьерных деталей.",
        "views_count": 512, "scans_count": 84,
    },
    {
        "brand": "OlgaCraft", "line": "Workshop PETG", "slug": "petg-forest",
        "name": "Workshop PETG · Forest", "material_type": "PETG", "preset_name": "Для функциональных деталей",
        "color_name": "Лесной зелёный", "color_hex": "#16845B", "ral_code": "6001",
        "density": 1.27, "price_per_kg": 2190.0, "spool_weight": 1000.0,
        "empty_spool_weight_g": 224.0, "nozzle": (225, 245), "bed": (70, 85),
        "visual_settings": visual("#16845B", finish="glossy"),
        "property_claims": [{"code": "chemical_resistant"}],
        "description": "Повседневный PETG для креплений, корпусов и деталей мастерской.",
        "views_count": 294, "scans_count": 36,
    },
    {
        "brand": "OlgaCraft", "line": "Silk PLA", "slug": "pla-silk-aurora",
        "name": "Silk PLA · Aurora", "material_type": "PLA", "preset_name": "Яркий шёлк",
        "color_name": "Северное сияние", "color_hex": "#8C55D9",
        "density": 1.24, "price_per_kg": 2490.0, "spool_weight": 1000.0,
        "empty_spool_weight_g": 219.0, "nozzle": (205, 225), "bed": (50, 60),
        "visual_settings": visual(
            "#8C55D9", finish="glossy", color_type="gradient",
            colors=["#D84FC7", "#7A5CE0", "#21C6D7"],
        ),
        "description": "Шелковистый трёхцветный переход для ваз, декора и подарков.",
        "views_count": 627, "scans_count": 109,
    },
    {
        "brand": "FibraCraft", "line": "Galaxy PLA", "slug": "fibracraft-galaxy-violet-nebula",
        "name": "Galaxy PLA · Violet Nebula", "material_type": "PLA", "preset_name": "Clean surface",
        "color_name": "Фиолетовая туманность", "color_hex": "#6040A8",
        "density": 1.25, "price_per_kg": 27.9, "spool_weight": 1000.0,
        "empty_spool_weight_g": 206.0, "nozzle": (205, 225), "bed": (50, 65),
        "visual_settings": visual("#6040A8", finish="glossy", filler="glitter", effects=["glitter"]),
        "description": "Тёмно-фиолетовый PLA с мелким равномерным блеском.",
        "views_count": 983, "scans_count": 142,
    },
    {
        "brand": "FibraCraft", "line": "Carbon PETG", "slug": "fibracraft-carbon-petg-graphite",
        "name": "Carbon PETG · Graphite", "material_type": "PETG-CF", "preset_name": "Dimensional parts",
        "color_name": "Графит", "color_hex": "#34383D",
        "density": 1.22, "price_per_kg": 39.9, "spool_weight": 750.0,
        "empty_spool_weight_g": 192.0, "nozzle": (235, 255), "bed": (75, 90),
        "required_nozzle_hrc": 55,
        "visual_settings": visual("#34383D", filler="carbon"),
        "additives": [{"code": "carbon_fiber", "content_percent": 15.0, "content_basis": "weight"}],
        "property_claims": [{"code": "wear_resistant"}],
        "description": "Жёсткий матовый PETG-CF; требуется износостойкое сопло.",
        "views_count": 746, "scans_count": 93,
    },
    {
        "brand": "FibraCraft", "line": "Soft Touch", "slug": "fibracraft-soft-touch-signal-orange",
        "name": "Soft Touch TPU · Signal Orange", "material_type": "TPU", "preset_name": "Flexible details",
        "color_name": "Сигнальный оранжевый", "color_hex": "#F05A28", "ral_code": "2005",
        "density": 1.21, "price_per_kg": 34.5, "spool_weight": 750.0,
        "empty_spool_weight_g": 185.0, "nozzle": (215, 235), "bed": (35, 55),
        "visual_settings": visual("#F05A28"),
        "description": "Эластичный TPU 95A для накладок, ножек и защитных элементов.",
        "views_count": 421, "scans_count": 44,
    },
    {
        "brand": "NorthLayer", "line": "Everyday PETG", "slug": "northlayer-petg-arctic-blue",
        "name": "Everyday PETG · Arctic Blue", "material_type": "PETG", "preset_name": "Strong functional parts",
        "color_name": "Арктический синий", "color_hex": "#43A6C6",
        "density": 1.27, "price_per_kg": 24.9, "spool_weight": 1000.0,
        "empty_spool_weight_g": 214.0, "nozzle": (225, 245), "bed": (70, 85),
        "visual_settings": visual("#43A6C6", finish="glossy"),
        "description": "Спокойный голубой PETG для функциональной печати без закрытой камеры.",
        "views_count": 688, "scans_count": 72,
    },
    {
        "brand": "NorthLayer", "line": "Outdoor ASA", "slug": "northlayer-asa-polar-white",
        "name": "Outdoor ASA · Polar White", "material_type": "ASA", "preset_name": "Outdoor use",
        "color_name": "Полярный белый", "color_hex": "#F1F2EE", "ral_code": "9016",
        "density": 1.07, "price_per_kg": 28.5, "spool_weight": 1000.0,
        "empty_spool_weight_g": 216.0, "nozzle": (245, 265), "bed": (90, 110),
        "visual_settings": visual("#F1F2EE"),
        "property_claims": [{"code": "uv_resistant"}, {"code": "heat_resistant"}],
        "description": "Светлый ASA для уличных корпусов и креплений.",
        "views_count": 532, "scans_count": 61,
    },
    {
        "brand": "NorthLayer", "line": "Draft PLA", "slug": "northlayer-draft-lime",
        "name": "Draft PLA · Workshop Lime", "material_type": "PLA", "preset_name": "Fast drafts",
        "color_name": "Лаймовый", "color_hex": "#A7D129",
        "density": 1.24, "price_per_kg": 20.9, "spool_weight": 1000.0,
        "empty_spool_weight_g": 211.0, "nozzle": (195, 220), "bed": (45, 60),
        "visual_settings": visual("#A7D129"),
        "description": "Контрастный PLA для быстрых макетов и проверок геометрии.",
        "views_count": 312, "scans_count": 28,
    },
    {
        "brand": "PolyForge", "line": "ASA Shield", "slug": "polyforge-asa-shield-graphite",
        "name": "ASA Shield · Graphite", "material_type": "ASA", "preset_name": "Enclosed parts",
        "color_name": "Графитовый серый", "color_hex": "#4A4E52", "ral_code": "7024",
        "density": 1.07, "price_per_kg": 31.0, "spool_weight": 1000.0,
        "empty_spool_weight_g": 230.0, "nozzle": (245, 265), "bed": (95, 110),
        "visual_settings": visual("#4A4E52"),
        "property_claims": [{"code": "uv_resistant"}],
        "description": "Технический ASA для кожухов, кронштейнов и наружных деталей.",
        "views_count": 807, "scans_count": 98,
    },
    {
        "brand": "PolyForge", "line": "Strong PC", "slug": "polyforge-strong-pc-smoke",
        "name": "Strong PC · Smoke", "material_type": "PC", "preset_name": "Heat-resistant parts",
        "color_name": "Дымчатый", "color_hex": "#667078",
        "density": 1.20, "price_per_kg": 42.0, "spool_weight": 750.0,
        "empty_spool_weight_g": 194.0, "nozzle": (265, 285), "bed": (100, 115),
        "visual_settings": visual("#667078", finish="glossy", transparency=True),
        "property_claims": [{"code": "heat_resistant"}],
        "description": "Поликарбонат для прочных деталей с высокой теплостойкостью.",
        "views_count": 611, "scans_count": 39,
    },
    {
        "brand": "PolyForge", "line": "Glass Nylon", "slug": "polyforge-pa-gf-slate",
        "name": "Glass Nylon · Slate", "material_type": "PA-GF", "preset_name": "Loaded parts",
        "color_name": "Сланцевый", "color_hex": "#596168",
        "density": 1.29, "price_per_kg": 54.0, "spool_weight": 750.0,
        "empty_spool_weight_g": 198.0, "nozzle": (265, 290), "bed": (80, 105),
        "required_nozzle_hrc": 55,
        "visual_settings": visual("#596168", filler="glass"),
        "additives": [{"code": "glass_fiber", "content_percent": 20.0, "content_basis": "weight"}],
        "property_claims": [{"code": "wear_resistant"}, {"code": "heat_resistant"}],
        "description": "Стеклонаполненный нейлон для жёстких функциональных деталей.",
        "views_count": 579, "scans_count": 34,
    },
    {
        "brand": "LumiLayer", "line": "Night Glow", "slug": "lumilayer-glow-moonlight",
        "name": "Night Glow PLA · Moonlight", "material_type": "PLA", "preset_name": "Even glow",
        "color_name": "Лунное свечение", "color_hex": "#C9E8B4",
        "density": 1.27, "price_per_kg": 29.0, "spool_weight": 1000.0,
        "empty_spool_weight_g": 207.0, "nozzle": (205, 225), "bed": (50, 60),
        "required_nozzle_hrc": 45,
        "visual_settings": visual("#C9E8B4", filler="luminescent", effects=["luminescent"]),
        "description": "Светонакопительный PLA для указателей и декоративных элементов.",
        "views_count": 1132, "scans_count": 186,
    },
    {
        "brand": "LumiLayer", "line": "Clear PETG", "slug": "lumilayer-clear-petg-ice",
        "name": "Clear PETG · Ice", "material_type": "PETG", "preset_name": "High clarity",
        "color_name": "Ледяной прозрачный", "color_hex": "#D7F3F6",
        "density": 1.27, "price_per_kg": 26.0, "spool_weight": 1000.0,
        "empty_spool_weight_g": 207.0, "nozzle": (230, 250), "bed": (70, 85),
        "visual_settings": visual("#D7F3F6", finish="glossy", transparency=True),
        "description": "Прозрачный PETG для рассеивателей и визуальных прототипов.",
        "views_count": 904, "scans_count": 103,
    },
    {
        "brand": "LumiLayer", "line": "Silk Metal", "slug": "lumilayer-silk-rose-gold",
        "name": "Silk PLA · Rose Gold", "material_type": "PLA", "preset_name": "Decorative shine",
        "color_name": "Розовое золото", "color_hex": "#C98C86",
        "density": 1.24, "price_per_kg": 27.5, "spool_weight": 1000.0,
        "empty_spool_weight_g": 208.0, "nozzle": (205, 225), "bed": (50, 60),
        "visual_settings": visual("#C98C86", finish="glossy", filler="metallic", effects=["metallic"]),
        "description": "Шелковистый PLA с тёплым металлическим отблеском.",
        "views_count": 1021, "scans_count": 119,
    },
    {
        "brand": "PrismWeave", "line": "ChromaShift", "slug": "prismweave-chromashift-aurora-ink",
        "name": "ChromaShift PLA · Aurora Ink", "material_type": "PLA", "preset_name": "Soft colour transitions",
        "color_name": "Aurora Ink", "color_hex": "#7B5AE4",
        "density": 1.24, "price_per_kg": 31.0, "spool_weight": 1000.0,
        "empty_spool_weight_g": 214.0, "nozzle": (205, 225), "bed": (50, 60),
        "visual_settings": visual(
            "#7B5AE4", finish="glossy", color_type="gradient",
            colors=["#D14EB6", "#7B5AE4", "#2AC6C7"],
        ),
        "description": "Three-colour transition PLA for vases, props and decorative surfaces.",
        "views_count": 812, "scans_count": 128,
    },
    {
        "brand": "PrismWeave", "line": "Velvet", "slug": "prismweave-velvet-moss",
        "name": "Velvet PLA · Moss", "material_type": "PLA", "preset_name": "Quiet matte finish",
        "color_name": "Moss", "color_hex": "#52664A", "ral_code": "6003",
        "density": 1.24, "price_per_kg": 27.0, "spool_weight": 1000.0,
        "empty_spool_weight_g": 214.0, "nozzle": (200, 220), "bed": (50, 60),
        "visual_settings": visual("#52664A"),
        "description": "Low-sheen PLA for architectural models and calm interior objects.",
        "views_count": 536, "scans_count": 61,
    },
    {
        "brand": "ForgeNest", "line": "Endurance", "slug": "forgenest-endurance-traffic-grey",
        "name": "Endurance PETG · Traffic Grey", "material_type": "PETG", "preset_name": "Werkstattprofil",
        "color_name": "Traffic Grey", "color_hex": "#7B7D7D", "ral_code": "7042",
        "density": 1.27, "price_per_kg": 28.5, "spool_weight": 1000.0,
        "empty_spool_weight_g": 226.0, "nozzle": (230, 250), "bed": (70, 85),
        "visual_settings": visual("#7B7D7D"),
        "property_claims": [{"code": "chemical_resistant"}],
        "description": "Zäher PETG-Werkstoff für Halterungen, Gehäuse und wiederkehrende Werkstattteile.",
        "views_count": 689, "scans_count": 84,
    },
    {
        "brand": "ForgeNest", "line": "Tech PA12-CF", "slug": "forgenest-pa12-cf-obsidian",
        "name": "Tech PA12-CF · Obsidian", "material_type": "PA12-CF", "preset_name": "Maßhaltige Funktionsteile",
        "color_name": "Obsidian", "color_hex": "#25272A",
        "density": 1.08, "price_per_kg": 69.0, "spool_weight": 750.0,
        "empty_spool_weight_g": 198.0, "nozzle": (265, 290), "bed": (90, 110),
        "required_nozzle_hrc": 55,
        "visual_settings": visual("#25272A", filler="carbon"),
        "additives": [{"code": "carbon_fiber", "content_percent": 15.0, "content_basis": "weight"}],
        "property_claims": [{"code": "wear_resistant"}, {"code": "heat_resistant"}],
        "description": "Carbonfaserverstärktes PA12 für steife, maßhaltige und belastete Bauteile.",
        "views_count": 731, "scans_count": 69,
    },
    {
        "brand": "TerraLoop", "line": "ReForm", "slug": "terraloop-reform-sea-glass",
        "name": "ReForm PLA · Sea Glass", "material_type": "PLA", "preset_name": "Everyday recycled PLA",
        "color_name": "Sea Glass", "color_hex": "#4D8F87",
        "density": 1.24, "price_per_kg": 25.0, "spool_weight": 1000.0,
        "empty_spool_weight_g": 221.0, "nozzle": (200, 220), "bed": (50, 60),
        "visual_settings": visual("#4D8F87"),
        "description": "Recycled PLA with a muted teal colour for prototypes and everyday prints.",
        "views_count": 477, "scans_count": 52,
    },
    {
        "brand": "TerraLoop", "line": "Cork Blend", "slug": "terraloop-cork-blend-natural",
        "name": "Cork Blend · Natural", "material_type": "PLA", "preset_name": "Zichtbare kurktextuur",
        "color_name": "Natural Cork", "color_hex": "#B88755",
        "density": 1.18, "price_per_kg": 32.0, "spool_weight": 750.0,
        "empty_spool_weight_g": 189.0, "nozzle": (195, 215), "bed": (45, 60),
        "visual_settings": visual("#B88755", filler="wood"),
        "additives": [{"code": "cork", "content_percent": 20.0, "content_basis": "weight"}],
        "description": "PLA blend with cork particles and a warm, lightly textured surface.",
        "views_count": 592, "scans_count": 74,
    },
)


COMMUNITY_USERS: tuple[dict[str, str], ...] = (
    {"email": "layerfox@example.com", "username": "LayerFox", "full_name": "Alex Layer", "country": "FI"},
    {"email": "milaprints@example.com", "username": "MilaPrints", "full_name": "Mila Hart", "country": "DE"},
    {"email": "voronnorth@example.com", "username": "VoronNorth", "full_name": "Noah Berg", "country": "SE"},
    {"email": "protoden@example.com", "username": "ProtoDen", "full_name": "Denis Proto", "country": "CZ"},
    {"email": "nikomakes@example.com", "username": "NikoMakes", "full_name": "Niko Marin", "country": "HR"},
    {"email": "printjuno@example.com", "username": "PrintJuno", "full_name": "June Parker", "country": "GB"},
    {"email": "atelier3d@example.com", "username": "Atelier3D", "full_name": "Camille Moreau", "country": "FR"},
    {"email": "makerli@example.com", "username": "MakerLi", "full_name": "Li Wei", "country": "CN"},
)


COMMUNITY_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "key": "layerfox-galaxy-balanced", "user": "LayerFox", "filament": "fibracraft-galaxy-violet-nebula",
        "name": "Smooth outer walls", "temp": 215, "bed": 58,
        "flow": 98.0, "fan": 95, "retraction": 0.8, "speed": 35.0,
        "rating": 4.9, "success_rate": 97.0, "usage_count": 184,
    },
    {
        "key": "milaprints-arctic-strong", "user": "MilaPrints", "filament": "northlayer-petg-arctic-blue",
        "name": "Stabile Funktionsteile", "temp": 238, "bed": 80,
        "flow": 99.0, "fan": 45, "retraction": 0.7, "speed": 32.0,
        "rating": 4.8, "success_rate": 95.0, "usage_count": 126,
    },
    {
        "key": "voronnorth-asa-fast", "user": "VoronNorth", "filament": "polyforge-asa-shield-graphite",
        "name": "Enclosure parts", "temp": 258, "bed": 105,
        "flow": 98.0, "fan": 15, "retraction": 0.6, "speed": 40.0,
        "rating": 4.7, "success_rate": 94.0, "usage_count": 91,
    },
    {
        "key": "protoden-carbon-dimensional", "user": "ProtoDen", "filament": "fibracraft-carbon-petg-graphite",
        "name": "Dimensional accuracy", "temp": 248, "bed": 82,
        "flow": 97.0, "fan": 35, "retraction": 0.7, "speed": 28.0,
        "rating": 4.9, "success_rate": 98.0, "usage_count": 73,
    },
    {
        "key": "nikomakes-wood-detail", "user": "NikoMakes", "filament": "pla-wood-warm-grey",
        "name": "Visible wood texture", "temp": 208, "bed": 55,
        "flow": 101.0, "fan": 100, "retraction": 0.8, "speed": 32.0,
        "rating": 4.6, "success_rate": 92.0, "usage_count": 58,
    },
    {
        "key": "printjuno-chromashift-vase", "user": "PrintJuno", "filament": "prismweave-chromashift-aurora-ink",
        "name": "Vase mode — gentle first layer", "temp": 210, "bed": 55,
        "flow": 99.0, "fan": 100, "retraction": 0.6, "speed": 30.0,
        "rating": 4.8, "success_rate": 96.0, "usage_count": 112,
    },
    {
        "key": "atelier3d-terraloop-matte", "user": "Atelier3D", "filament": "terraloop-reform-sea-glass",
        "name": "Pièces déco mates", "temp": 208, "bed": 55,
        "flow": 100.0, "fan": 95, "retraction": 0.8, "speed": 34.0,
        "rating": 4.7, "success_rate": 95.0, "usage_count": 83,
    },
    {
        "key": "makerli-forgenest-stable", "user": "MakerLi", "filament": "forgenest-endurance-traffic-grey",
        "name": "稳定的功能件", "temp": 240, "bed": 78,
        "flow": 98.0, "fan": 40, "retraction": 0.7, "speed": 32.0,
        "rating": 4.9, "success_rate": 97.0, "usage_count": 137,
    },
)


REVIEW_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "user": "LayerFox", "preset": "layerfox-galaxy-balanced", "rating": 5.0,
        "comment": "Блёстки распределены равномерно. На внешних стенках лучше держать скорость около 80 мм/с.",
        "printer_slug": "bambulab-bambu-lab-p1s",
    },
    {
        "user": "MilaPrints", "preset": "milaprints-arctic-strong", "rating": 4.8,
        "comment": "После сушки нити почти исчезли, цвет совпал с карточкой. Детали получились прочными.",
        "printer_slug": "prusa-prusa-mk4s",
    },
    {
        "user": "VoronNorth", "preset": "voronnorth-asa-fast", "rating": 4.7,
        "comment": "Стабильно печатается в закрытой камере. Для крупных углов добавил широкий brim.",
        "printer_slug": "voron-voron-2-4-350",
    },
    {
        "user": "ProtoDen", "preset": "protoden-carbon-dimensional", "rating": 4.9,
        "comment": "Отличная геометрия креплений. Использовал закалённое сопло 0.4 мм.",
        "printer_slug": "bambulab-bambu-lab-p1s",
    },
    {
        "user": "NikoMakes", "preset": "nikomakes-wood-detail", "rating": 4.6,
        "comment": "Фактура хорошо проявляется после лёгкой шлифовки. Сопло 0.6 мм оказалось спокойнее.",
        "printer_slug": "prusa-prusa-mk4s",
    },
)


OLGA_SPOOLS: tuple[dict[str, Any], ...] = (
    {"key": "olga-coral-a1", "legacy_lot": "OC-SR-2608", "filament": "pla-satin-red", "initial": 1000.0, "used": 460.0, "price": 1990.0, "lot": "OC-CR-2608", "comment": "Текущие небольшие заказы на A1 mini"},
    {"key": "olga-deep-ocean-ams", "legacy_lot": "OC-OB-2608", "filament": "pla-ocean-blue", "initial": 1000.0, "used": 327.6, "price": 1890.0, "lot": "OC-DO-2608", "comment": "Основной синий для корпусов"},
    {"key": "olga-birch-shelf", "legacy_lot": "OC-WD-2607", "filament": "pla-wood-warm-grey", "initial": 750.0, "used": 143.2, "price": 1790.0, "lot": "OC-BR-2607", "comment": "Для декора и интерьерных изделий"},
    {"key": "olga-galaxy-ams", "filament": "fibracraft-galaxy-violet-nebula", "initial": 1000.0, "used": 681.3, "price": 2790.0, "lot": "FC-VN-2606", "comment": "Открытая катушка для подарочной серии"},
    {"key": "olga-arctic-ams", "filament": "northlayer-petg-arctic-blue", "initial": 1000.0, "used": 153.8, "price": 2490.0, "lot": "NL-AB-2607", "comment": "Функциональные детали и крепления"},
    {"key": "olga-aurora-ams", "filament": "pla-silk-aurora", "initial": 1000.0, "used": 74.5, "price": 2490.0, "lot": "OC-AU-2608", "comment": "Свежая катушка для декоративной печати"},
    {"key": "olga-empty-history", "filament": "petg-forest", "initial": 1000.0, "used": 1000.0, "price": 2190.0, "lot": "OC-FR-2604", "comment": "Закончилась на партии креплений", "state": "empty"},
)


OLGA_ORCA_DRAFT = {
    "external_id": "showcase:orca-draft:petg-fast-a1-mini",
    "name": "Быстрый PETG",
    "description": (
        "Локальная настройка из OrcaSlicer. Материал ещё не сопоставлен "
        "с точным товарным вариантом каталога."
    ),
    "extruder_temp": 240.0,
    "bed_temp": 75.0,
    "flow_rate": 0.98,
    "fan_speed": 45,
    "retraction_length": 0.8,
    "retraction_speed": 35.0,
    "orcaslicer_settings": {
        "fhub_draft_id": "showcase_olga_petg_fast_a1_mini",
        "filament_type": ["PETG"],
        "filament_max_volumetric_speed": [18],
        "pressure_advance": 0.032,
        "enrichment": {"material_type": "PETG"},
    },
}


def apply_values(instance: Any, values: dict[str, Any]) -> None:
    for key, value in values.items():
        setattr(instance, key, value)


async def seed_showcase() -> int:
    from sqlalchemy import func, or_, select, update

    from app.core.config import settings
    from app.core.field_encryption import encrypt_field
    from app.core.security import get_password_hash
    from app.db.session import AsyncSessionLocal
    from app.models.brand import Brand
    from app.models.brand_country_cell import BrandCountryCell
    from app.models.calculator_history_entry import CalculatorHistoryEntry
    from app.models.calculator_profile import UserCalculatorProfile
    from app.models.crm import (
        CrmCustomer,
        CrmOrder,
        CrmOrderStatus,
        CrmQuote,
        CrmQuoteEvent,
        CrmQuoteEventType,
        CrmQuoteLine,
        CrmQuoteStatus,
        CrmQuoteVersion,
    )
    from app.models.filament import Filament, FilamentAvailability
    from app.models.filament_analytics_event import FilamentAnalyticsEvent
    from app.models.filament_line import FilamentLine
    from app.models.filament_review import FilamentReview
    from app.models.material_slot_assignment import MaterialSlotAssignment
    from app.models.material_system import MaterialSlot, MaterialSystem
    from app.models.preset import Preset, PresetModerationStatus
    from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
    from app.models.printer import Printer
    from app.models.subscription import Subscription, SubscriptionStatus
    from app.models.user import User, UserRole
    from app.models.user_printer_device import UserPrinterDevice
    from app.models.user_saved_preset import UserSavedPreset
    from app.models.user_spool import UserSpool, UserSpoolState
    from app.schemas.calculator import CalculatorEstimateRequest, CalculatorEstimateResponse
    from app.services.legal_acceptance_service import (
        CURRENT_PERSONAL_DATA_CONSENT_VERSION,
        CURRENT_PRIVACY_POLICY_VERSION,
        CURRENT_TERMS_VERSION,
    )

    db_host = settings.POSTGRES_HOST.casefold()
    db_name = settings.POSTGRES_DB.casefold()
    if db_host not in LOCAL_DB_HOSTS or "dev" not in db_name:
        print(
            "Отказ: showcase можно создавать только в явно локальной dev-базе "
            f"(получено host={settings.POSTGRES_HOST!r}, db={settings.POSTGRES_DB!r}).",
            file=sys.stderr,
        )
        return 2

    now = datetime.now(timezone.utc)
    password_hash = get_password_hash(SHOWCASE_PASSWORD)

    async with AsyncSessionLocal() as db:
        technical_brand_filter = or_(
            Brand.slug.like("seed-brand-%"),
            Brand.slug.like("test%"),
            Brand.slug.like("demo%"),
            Brand.slug.in_(("user-materials", "hexflow", "neonthread", "printnova")),
        )
        volume_brand_ids = select(Brand.id).where(technical_brand_filter)
        volume_filament_ids = select(Filament.id).where(Filament.brand_id.in_(volume_brand_ids))
        hidden_volume_brands = int(await db.scalar(
            select(func.count()).select_from(Brand).where(
                technical_brand_filter,
                Brand.active.is_(True),
            )
        ) or 0)
        hidden_volume_filaments = int(await db.scalar(
            select(func.count()).select_from(Filament).where(
                Filament.brand_id.in_(volume_brand_ids),
                Filament.active.is_(True),
            )
        ) or 0)
        hidden_volume_presets = int(await db.scalar(
            select(func.count()).select_from(Preset).where(
                Preset.filament_id.in_(volume_filament_ids),
                Preset.active.is_(True),
            )
        ) or 0)
        await db.execute(
            update(Preset)
            .where(Preset.filament_id.in_(volume_filament_ids))
            .values(active=False)
        )
        await db.execute(
            update(Filament)
            .where(Filament.brand_id.in_(volume_brand_ids))
            .values(active=False)
        )
        await db.execute(
            update(Brand)
            .where(technical_brand_filter)
            .values(active=False)
        )

        brands: dict[str, Brand] = {}
        for definition in BRAND_DEFINITIONS:
            brand = await db.scalar(select(Brand).where(Brand.slug == definition["slug"]))
            if brand is None:
                brand = Brand(name=definition["name"], slug=definition["slug"])
                db.add(brand)
            apply_values(brand, {key: value for key, value in definition.items() if key != "slug"})
            brand.active = True
            brands[definition["name"]] = brand
        await db.flush()

        olga_market = await db.scalar(
            select(BrandCountryCell).where(
                BrandCountryCell.brand_id == brands["OlgaCraft"].id,
                BrandCountryCell.country == "KZ",
            )
        )
        if olga_market is None:
            olga_market = BrandCountryCell(
                brand_id=brands["OlgaCraft"].id,
                country="KZ",
            )
            db.add(olga_market)
        apply_values(
            olga_market,
            {
                "website": "https://kz.olgacraft.example",
                "description": (
                    "Материалы OlgaCraft для мастерских, студий и небольших "
                    "производств 3D-печати в Казахстане."
                ),
                "social_media_urls": [],
                "shop_links": [],
                "currency": "KZT",
                "published": True,
            },
        )
        await db.flush()

        users: dict[str, User] = {}
        olga = await db.scalar(select(User).where(func.lower(User.username) == "olgacraft"))
        if olga is None:
            olga = await db.scalar(select(User).where(func.lower(User.email) == "olga@example.com"))
        if olga is None:
            olga = User(
                email="olga@example.com",
                username="OlgaCraft",
                password_hash=password_hash,
                created_at=now - timedelta(days=160),
            )
            db.add(olga)
        olga.full_name = "Ольга Крафт"
        olga.password_hash = password_hash
        olga.country = "KZ"
        olga.role = UserRole.BRAND
        olga.brand_id = brands["OlgaCraft"].id
        olga.active = True
        olga.email_verified = True
        olga.can_edit_wiki = True
        olga.badges = ["beta_tester", "verified", "early_adopter"]
        olga.terms_version_accepted = CURRENT_TERMS_VERSION
        olga.personal_data_consent_version = CURRENT_PERSONAL_DATA_CONSENT_VERSION
        olga.privacy_policy_version_presented = CURRENT_PRIVACY_POLICY_VERSION
        olga.legal_accepted_at = olga.legal_accepted_at or now - timedelta(days=150)
        olga.legal_acceptance_language = "ru"
        olga.legal_document_pack = "ru"
        users[olga.username] = olga

        for offset, definition in enumerate(COMMUNITY_USERS, start=1):
            user = await db.scalar(select(User).where(func.lower(User.email) == definition["email"]))
            if user is None:
                user = User(
                    email=definition["email"],
                    username=definition["username"],
                    password_hash=password_hash,
                    role=UserRole.USER,
                    created_at=now - timedelta(days=140 - offset * 13),
                )
                db.add(user)
            user.username = definition["username"]
            user.password_hash = password_hash
            user.full_name = definition["full_name"]
            user.country = definition["country"]
            user.active = True
            user.email_verified = True
            user.badges = ["early_adopter"] if offset % 2 else ["beta_tester"]
            user.terms_version_accepted = CURRENT_TERMS_VERSION
            user.personal_data_consent_version = CURRENT_PERSONAL_DATA_CONSENT_VERSION
            user.privacy_policy_version_presented = CURRENT_PRIVACY_POLICY_VERSION
            user.legal_accepted_at = user.legal_accepted_at or now - timedelta(days=120 - offset * 10)
            user.legal_acceptance_language = "en"
            user.legal_document_pack = "intl"
            users[user.username] = user
        await db.flush()

        subscription = await db.scalar(select(Subscription).where(Subscription.user_id == olga.id))
        if subscription is None:
            subscription = Subscription(user_id=olga.id)
            db.add(subscription)
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.is_comp = True
        subscription.current_period_end = now + timedelta(days=3650)
        subscription.cancel_at_period_end = False

        profile = await db.scalar(
            select(UserCalculatorProfile).where(UserCalculatorProfile.user_id == olga.id)
        )
        if profile is None:
            profile = UserCalculatorProfile(user_id=olga.id)
            db.add(profile)
        apply_values(profile, {
            "currency": "RUB",
            "electricity_cost_per_kwh": 7.2,
            "printer_power_w": 130.0,
            "modeling_rate_per_hour": 900.0,
            "postprocessing_rate_per_hour": 650.0,
            "printing_rate_per_hour": 190.0,
            "amortization_rate_per_hour": 22.0,
            "overhead_percent": 18.0,
            "markup_percent": 35.0,
            "fixed_costs": 120.0,
            "bed_prep_cost_per_print": 35.0,
            "min_order_price": 700.0,
            "seller_name": "Мастерская OlgaCraft",
            "payment_terms": "50% перед запуском, остаток после готовности заказа",
            "quote_market": "RU",
            "validity_days": 14,
            "quote_number_prefix": "OC",
        })

        lines: dict[tuple[str, str], FilamentLine] = {}
        filaments: dict[str, Filament] = {}
        for definition in FILAMENT_DEFINITIONS:
            brand = brands[definition["brand"]]
            line_key = (definition["brand"], definition["line"])
            line = lines.get(line_key)
            if line is None:
                line = await db.scalar(
                    select(FilamentLine).where(
                        FilamentLine.brand_id == brand.id,
                        FilamentLine.name == definition["line"],
                    )
                )
                if line is None:
                    line = FilamentLine(brand_id=brand.id, name=definition["line"])
                    db.add(line)
                    await db.flush()
                lines[line_key] = line

            showcase_qr = f"FH-SHOW-{definition['slug'][:36].upper()}"
            filament = await db.scalar(select(Filament).where(Filament.qr_code == showcase_qr))
            if filament is None:
                filament = await db.scalar(select(Filament).where(Filament.slug == definition["slug"]))
            if filament is None:
                filament = Filament(
                    brand_id=brand.id,
                    slug=definition["slug"],
                    name=definition["name"],
                    material_type=definition["material_type"],
                )
                db.add(filament)
            nozzle_min, nozzle_max = definition["nozzle"]
            bed_min, bed_max = definition["bed"]
            apply_values(filament, {
                "brand_id": brand.id,
                "line_id": line.id,
                "name": definition["name"],
                "material_type": definition["material_type"],
                "color_name": definition["color_name"],
                "color_hex": definition["color_hex"],
                "ral_code": definition.get("ral_code"),
                "diameter": 1.75,
                "density": definition["density"],
                "price_per_kg": definition["price_per_kg"],
                "spool_weight": definition["spool_weight"],
                "empty_spool_weight_g": definition["empty_spool_weight_g"],
                "recommended_nozzle_temp_min": nozzle_min,
                "recommended_nozzle_temp_max": nozzle_max,
                "recommended_bed_temp_min": bed_min,
                "recommended_bed_temp_max": bed_max,
                "required_nozzle_hrc": definition.get("required_nozzle_hrc"),
                "visual_settings": definition["visual_settings"],
                "additives": definition.get("additives", []),
                "property_claims": definition.get("property_claims", []),
                "description": definition["description"],
                "views_count": definition["views_count"],
                "scans_count": definition["scans_count"],
                "qr_code": showcase_qr,
                "availability": FilamentAvailability.available,
                "price_display_unit": "per_spool",
                "active": True,
            })
            filaments[definition["slug"]] = filament
        await db.flush()

        territorial_scan_counts = {
            "pla-ocean-blue": 18,
            "pla-satin-red": 12,
            "pla-wood-warm-grey": 16,
            "petg-forest": 9,
            "pla-silk-aurora": 21,
        }
        for filament_slug, expected_count in territorial_scan_counts.items():
            existing_count = int(
                await db.scalar(
                    select(func.count(FilamentAnalyticsEvent.id)).where(
                        FilamentAnalyticsEvent.filament_id
                        == filaments[filament_slug].id,
                        FilamentAnalyticsEvent.event_type == "qr_scan",
                        FilamentAnalyticsEvent.country == "KZ",
                    )
                )
                or 0
            )
            for event_index in range(existing_count, expected_count):
                db.add(
                    FilamentAnalyticsEvent(
                        filament_id=filaments[filament_slug].id,
                        event_type="qr_scan",
                        country="KZ",
                        created_at=now
                        - timedelta(days=(event_index * 3) % 45, hours=event_index % 17),
                    )
                )
        await db.flush()

        official_presets: dict[str, Preset] = {}
        for slug, filament in filaments.items():
            definition = next(item for item in FILAMENT_DEFINITIONS if item["slug"] == slug)
            owner_id = olga.id if definition["brand"] == "OlgaCraft" else None
            preset = await db.scalar(
                select(Preset).where(
                    Preset.filament_id == filament.id,
                    Preset.is_official.is_(True),
                    Preset.user_id == owner_id if owner_id is not None else Preset.user_id.is_(None),
                ).order_by(Preset.id)
            )
            if preset is None:
                preset = Preset(
                    filament_id=filament.id,
                    user_id=owner_id,
                    name="",
                    extruder_temp=0,
                    bed_temp=0,
                )
                db.add(preset)
            nozzle_min, nozzle_max = definition["nozzle"]
            bed_min, bed_max = definition["bed"]
            apply_values(preset, {
                "name": definition["preset_name"],
                "description": "Проверенная отправная точка производителя для сопла 0.4 мм.",
                "is_official": True,
                "is_weighted": False,
                "extruder_temp": round((nozzle_min + nozzle_max) / 2),
                "bed_temp": round((bed_min + bed_max) / 2),
                "flow_rate": 100.0,
                "fan_speed": 100 if definition["material_type"] == "PLA" else 40,
                "retraction_length": 0.8,
                "retraction_speed": 35.0,
                "rating": 4.8,
                "success_rate": 96.0,
                "usage_count": max(24, definition["views_count"] // 4),
                "moderation_status": PresetModerationStatus.APPROVED,
                "active": True,
                "source": "brand",
                "orcaslicer_settings": {
                    "filament_max_volumetric_speed": 12 if definition["material_type"] == "PLA" else 10,
                    "pressure_advance": 0.025,
                },
            })
            official_presets[slug] = preset
        await db.flush()

        community_presets: dict[str, Preset] = {}
        for definition in COMMUNITY_PRESETS:
            creator = users[definition["user"]]
            filament = filaments[definition["filament"]]
            external_id = f"showcase:{definition['key']}"
            preset = await db.scalar(
                select(Preset).where(Preset.user_id == creator.id, Preset.external_id == external_id)
            )
            if preset is None:
                preset = Preset(
                    user_id=creator.id,
                    filament_id=filament.id,
                    external_id=external_id,
                    name=definition["name"],
                    extruder_temp=definition["temp"],
                    bed_temp=definition["bed"],
                )
                db.add(preset)
            apply_values(preset, {
                "filament_id": filament.id,
                "name": definition["name"],
                "description": "Настроено на реальной печати и опубликовано для сообщества.",
                "is_official": False,
                "is_weighted": False,
                "extruder_temp": definition["temp"],
                "bed_temp": definition["bed"],
                "flow_rate": definition["flow"],
                "fan_speed": definition["fan"],
                "retraction_length": definition["retraction"],
                "retraction_speed": definition["speed"],
                "rating": definition["rating"],
                "success_rate": definition["success_rate"],
                "usage_count": definition["usage_count"],
                "moderation_status": PresetModerationStatus.APPROVED,
                "active": True,
                "source": "user",
                "orcaslicer_settings": {
                    "showcase_key": definition["key"],
                    "filament_max_volumetric_speed": 10.0,
                    "pressure_advance": 0.03,
                },
            })
            community_presets[definition["key"]] = preset
        await db.flush()

        olga_draft = await db.scalar(
            select(Preset).where(
                Preset.user_id == olga.id,
                Preset.external_id == OLGA_ORCA_DRAFT["external_id"],
            )
        )
        if olga_draft is None:
            olga_draft = Preset(
                user_id=olga.id,
                filament_id=None,
                name=OLGA_ORCA_DRAFT["name"],
                extruder_temp=OLGA_ORCA_DRAFT["extruder_temp"],
                bed_temp=OLGA_ORCA_DRAFT["bed_temp"],
            )
            db.add(olga_draft)
            await db.flush()
        apply_values(olga_draft, {
            **OLGA_ORCA_DRAFT,
            "filament_id": None,
            "user_id": olga.id,
            "is_official": False,
            "is_weighted": False,
            "moderation_status": PresetModerationStatus.PENDING,
            "moderation_reason": None,
            "active": False,
            "source": "orcaslicer",
        })
        saved_draft = await db.scalar(
            select(UserSavedPreset).where(
                UserSavedPreset.user_id == olga.id,
                UserSavedPreset.preset_id == olga_draft.id,
            )
        )
        if saved_draft is None:
            saved_draft = UserSavedPreset(
                user_id=olga.id,
                preset_id=olga_draft.id,
                sync=True,
            )
            db.add(saved_draft)
        else:
            saved_draft.sync = True
        await db.flush()

        printers = {
            printer.slug: printer
            for printer in (
                await db.execute(
                    select(Printer).where(
                        Printer.slug.in_({item["printer_slug"] for item in REVIEW_DEFINITIONS})
                    )
                )
            ).scalars()
        }
        for definition in REVIEW_DEFINITIONS:
            creator = users[definition["user"]]
            preset = community_presets[definition["preset"]]
            printer = printers.get(definition["printer_slug"])
            review = await db.scalar(
                select(FilamentReview).where(
                    FilamentReview.user_id == creator.id,
                    FilamentReview.filament_id == preset.filament_id,
                    FilamentReview.preset_id == preset.id,
                )
            )
            if review is None:
                review = FilamentReview(
                    user_id=creator.id,
                    filament_id=preset.filament_id,
                    preset_id=preset.id,
                    success=True,
                    rating=definition["rating"],
                )
                db.add(review)
            apply_values(review, {
                "success": True,
                "rating": definition["rating"],
                "comment": definition["comment"],
                "printer_id": printer.id if printer else None,
                "printer_model": printer.name if printer else None,
                "active": True,
            })

        catalog_printers = {
            printer.slug: printer
            for printer in (
                await db.execute(
                    select(Printer).where(
                        Printer.slug.in_({
                            "bambulab-bambu-lab-a1-mini",
                            "bambulab-bambu-lab-p1s",
                            "prusa-prusa-mk4s",
                            "voron-voron-2-4-350",
                        })
                    )
                )
            ).scalars()
        }

        olga_printer_definitions = (
            ("olga-a1-mini", "Olga's A1 mini", "bambulab-bambu-lab-a1-mini", 28900.0, 145.0),
            ("olga-p1s", "Bambu Lab P1S", "bambulab-bambu-lab-p1s", 77900.0, 170.0),
            ("olga-mk4s", "Prusa MK4S", "prusa-prusa-mk4s", 112000.0, 155.0),
        )
        olga_printers: dict[str, UserPrinterDevice] = {}
        for key, name, printer_slug, purchase_cost, machine_rate in olga_printer_definitions:
            fingerprint = f"showcase:{key}"
            device = await db.scalar(
                select(UserPrinterDevice).where(
                    UserPrinterDevice.user_id == olga.id,
                    UserPrinterDevice.device_fingerprint == fingerprint,
                )
            )
            if device is None:
                device = UserPrinterDevice(user_id=olga.id, name=name)
                db.add(device)
            apply_values(device, {
                "name": name,
                "printer_id": catalog_printers.get(printer_slug).id if catalog_printers.get(printer_slug) else None,
                "device_fingerprint": fingerprint,
                "supports_hh": False,
                "reports_feed": False,
                "purchase_cost": purchase_cost,
                "residual_value": round(purchase_cost * 0.2, 2),
                "useful_life_hours": 6000,
                "average_power_watts": 130.0,
                "maintenance_cost_per_hour": 18.0,
                "machine_hour_rate": machine_rate,
                "economics_currency": "RUB",
            })
            olga_printers[key] = device
        await db.flush()

        for index, definition in enumerate(COMMUNITY_USERS):
            user = users[definition["username"]]
            printer_slug = (
                "voron-voron-2-4-350" if definition["username"] == "VoronNorth"
                else "prusa-prusa-mk4s" if index % 2
                else "bambulab-bambu-lab-p1s"
            )
            name = (
                "Voron 2.4 350 · workshop" if definition["username"] == "VoronNorth"
                else f"{catalog_printers[printer_slug].name} · {definition['username']}"
            )
            device = await db.scalar(
                select(UserPrinterDevice).where(
                    UserPrinterDevice.user_id == user.id,
                    UserPrinterDevice.device_fingerprint == f"showcase:{definition['username'].lower()}",
                )
            )
            if device is None:
                device = UserPrinterDevice(user_id=user.id, name=name)
                db.add(device)
            device.name = name
            device.printer_id = catalog_printers[printer_slug].id
            device.device_fingerprint = f"showcase:{definition['username'].lower()}"
            device.purchase_cost = 65000.0 + index * 7000.0
            device.machine_hour_rate = 150.0 + index * 10.0
            device.economics_currency = "RUB"

        existing_spools = list(
            (await db.execute(select(UserSpool).where(UserSpool.user_id == olga.id))).scalars()
        )
        spools_by_key = {
            spool.extra.get("showcase_key"): spool
            for spool in existing_spools
            if isinstance(spool.extra, dict) and spool.extra.get("showcase_key")
        }
        spools_by_lot = {spool.lot_nr: spool for spool in existing_spools if spool.lot_nr}
        olga_spools: dict[str, UserSpool] = {}
        for definition in OLGA_SPOOLS:
            spool = spools_by_key.get(definition["key"])
            if spool is None and definition.get("legacy_lot"):
                spool = spools_by_lot.get(definition["legacy_lot"])
            if spool is None:
                spool = UserSpool(user_id=olga.id, initial_weight_g=definition["initial"])
                db.add(spool)
            apply_values(spool, {
                "filament_id": filaments[definition["filament"]].id,
                "initial_weight_g": definition["initial"],
                "used_weight_g": definition["used"],
                "state": UserSpoolState(definition.get("state", "shelf")),
                "price": definition["price"],
                "source": SHOWCASE_SOURCE,
                "lot_nr": definition["lot"],
                "comment": definition["comment"],
                "extra": {"showcase_key": definition["key"]},
                "first_used_at": now - timedelta(days=55),
                "last_used_at": now - timedelta(days=definition["used"] % 11),
            })
            olga_spools[definition["key"]] = spool
        await db.flush()

        usage_definitions = (
            {
                "job_ref": "showcase:usage:coral-badges",
                "spool": olga_spools["olga-coral-a1"],
                "delta": 460.0,
                "note": "Небольшая партия именных бейджей",
                "created_at": now - timedelta(days=2, hours=4),
            },
            {
                "job_ref": "showcase:usage:galaxy-organizers",
                "spool": olga_spools["olga-galaxy-ams"],
                "delta": 681.3,
                "note": "Подарочная серия настольных органайзеров",
                "created_at": now - timedelta(days=4, hours=7),
            },
        )
        for definition in usage_definitions:
            event = await db.scalar(
                select(PresetUsageEvent).where(
                    PresetUsageEvent.user_id == olga.id,
                    PresetUsageEvent.job_ref == definition["job_ref"],
                )
            )
            if event is None:
                event = PresetUsageEvent(
                    user_id=olga.id,
                    spool_id=definition["spool"].id,
                    event_type=PresetUsageEventType.manual_adjust,
                    job_ref=definition["job_ref"],
                )
                db.add(event)
            event.spool_id = definition["spool"].id
            event.event_type = PresetUsageEventType.manual_adjust
            event.delta_weight_g = definition["delta"]
            event.remaining_weight_g = max(
                definition["spool"].initial_weight_g - definition["spool"].used_weight_g,
                0.0,
            )
            event.meta = {"source": SHOWCASE_SOURCE, "note": definition["note"]}
            event.created_at = definition["created_at"]

        p1s = olga_printers["olga-p1s"]
        ams = await db.scalar(
            select(MaterialSystem).where(MaterialSystem.physical_printer_id == p1s.id)
        )
        if ams is None:
            ams = MaterialSystem(
                user_id=olga.id,
                physical_printer_id=p1s.id,
                name="Bambu AMS · ручное назначение",
                kind="bambu_ams",
                provider="manual",
            )
            db.add(ams)
        apply_values(ams, {
            "user_id": olga.id,
            "name": "Bambu AMS · ручное назначение",
            "kind": "bambu_ams",
            "provider": "manual",
            "capabilities": [],
            "declared_slot_count": 4,
            "active": True,
        })
        await db.flush()

        slot_spool_keys = (
            "olga-deep-ocean-ams",
            "olga-galaxy-ams",
            "olga-arctic-ams",
            "olga-aurora-ams",
        )
        slot_preset_slugs = (
            "pla-ocean-blue",
            "fibracraft-galaxy-violet-nebula",
            "northlayer-petg-arctic-blue",
            "pla-silk-aurora",
        )
        for slot_index, (spool_key, preset_slug) in enumerate(
            zip(slot_spool_keys, slot_preset_slugs, strict=True)
        ):
            slot = await db.scalar(
                select(MaterialSlot).where(
                    MaterialSlot.material_system_id == ams.id,
                    MaterialSlot.provider_index == slot_index,
                )
            )
            if slot is None:
                slot = MaterialSlot(
                    user_id=olga.id,
                    material_system_id=ams.id,
                    provider_index=slot_index,
                    kind="slot",
                )
                db.add(slot)
            slot.label = f"AMS {slot_index + 1}"
            slot.active = True
            await db.flush()
            assignment = await db.scalar(
                select(MaterialSlotAssignment).where(
                    MaterialSlotAssignment.material_slot_id == slot.id
                )
            )
            if assignment is None:
                assignment = MaterialSlotAssignment(
                    user_id=olga.id,
                    material_slot_id=slot.id,
                    source="web_manual",
                    source_ts=now,
                )
                db.add(assignment)
            assignment.spool_id = olga_spools[spool_key].id
            assignment.preset_id = official_presets[preset_slug].id
            assignment.source = "web_manual"
            assignment.source_ts = now
            assignment.active = True
            olga_spools[spool_key].state = UserSpoolState.active

        history_definitions = (
            {
                "title": "Корпуса датчиков · 24 шт.", "file": "sensor-housing-batch.gcode",
                "quantity": 24, "weight": 1386.0, "hours": 31.4, "cost": 18480.0,
                "filament": filaments["pla-ocean-blue"], "spool": olga_spools["olga-deep-ocean-ams"],
            },
            {
                "title": "Настольные органайзеры · 8 шт.", "file": "desk-organizer-set.gcode",
                "quantity": 8, "weight": 892.0, "hours": 18.7, "cost": 11240.0,
                "filament": filaments["fibracraft-galaxy-violet-nebula"], "spool": olga_spools["olga-galaxy-ams"],
            },
        )
        histories: dict[str, CalculatorHistoryEntry] = {}
        for definition in history_definitions:
            entry = await db.scalar(
                select(CalculatorHistoryEntry).where(
                    CalculatorHistoryEntry.user_id == olga.id,
                    CalculatorHistoryEntry.title == definition["title"],
                )
            )
            spool_price = float(definition["spool"].price or 0)
            spool_weight_kg = float(definition["spool"].initial_weight_g) / 1000.0
            price_per_gram = spool_price / (spool_weight_kg * 1000.0)
            material_cost = round(definition["weight"] * price_per_gram, 2)
            cost_before_markup = round(definition["cost"] / 1.30, 2)
            direct_cost = round(cost_before_markup / 1.18, 2)
            printing_cost = round(max(0.0, direct_cost - material_cost), 2)
            overhead_cost = round(cost_before_markup - direct_cost, 2)
            markup_cost = round(definition["cost"] - cost_before_markup, 2)
            unit_cost = round(definition["cost"] / definition["quantity"], 2)
            line_id = f"showcase:{definition['file']}:t0"

            request_data = CalculatorEstimateRequest.model_validate({
                "pricing_method": "combined",
                "quantity": definition["quantity"],
                "weight_g": definition["weight"],
                "time_hours": int(definition["hours"]),
                "time_minutes": round((definition["hours"] % 1) * 60),
                "markup_percent": 30.0,
                "overhead_percent": 18.0,
                "material_lines": [{
                    "line_id": line_id,
                    "label": definition["filament"].name,
                    "filament_id": definition["filament"].id,
                    "spool_id": definition["spool"].id,
                    "weight_g": definition["weight"],
                    "spool_price": spool_price,
                    "spool_weight_kg": spool_weight_kg,
                    "price_source": "spool",
                    "density_g_cm3": definition["filament"].density,
                }],
            }).model_dump(mode="json")
            result_data = CalculatorEstimateResponse.model_validate({
                "pricing_method": "combined",
                "quantity": definition["quantity"],
                "weight_kg": round(definition["weight"] / 1000, 3),
                "time_hours": definition["hours"],
                "total_time_hours": definition["hours"],
                "cost_material": material_cost,
                "cost_printing": printing_cost,
                "cost_direct": direct_cost,
                "cost_overhead": overhead_cost,
                "cost_before_markup": cost_before_markup,
                "cost_markup": markup_cost,
                "cost_first_part": unit_cost,
                "cost_subsequent_parts": unit_cost,
                "cost_total": definition["cost"],
                "cost_final": definition["cost"],
                "cost_of_goods_sold": cost_before_markup,
                "profit_margin": markup_cost,
                "profit_margin_percent": round(markup_cost / definition["cost"] * 100.0, 2),
                "material_line_costs": [{
                    "line_id": line_id,
                    "label": definition["filament"].name,
                    "weight_g": definition["weight"],
                    "price_per_gram": price_per_gram,
                    "cost": material_cost,
                    "price_source": "spool",
                    "spool_id": definition["spool"].id,
                    "filament_id": definition["filament"].id,
                }],
                "print_runs": definition["quantity"],
            }).model_dump(mode="json")
            parsed_gcode = {
                "file_name": definition["file"],
                "file_size_bytes": 4_200_000 + definition["quantity"] * 1000,
                "slicer_name": "OrcaSlicer",
                "slicer_version": "2.4.2",
                "printer_model": "Bambu Lab P1S",
                "print_time_seconds": round(definition["hours"] * 3600),
                "total_filament_weight_g": definition["weight"],
                "active_material_count": 1,
                "is_multi_material": False,
                "materials": [{
                    "name": definition["filament"].name,
                    "type": definition["filament"].material_type,
                    "color": definition["filament"].color_hex,
                    "weight_g": definition["weight"],
                    "tool_index": 0,
                }],
                "thumbnail_data_url": None,
            }
            snapshot = {
                "id": definition["filament"].id,
                "name": definition["filament"].name,
                "brand_name": next(
                    brand_name
                    for brand_name, brand in brands.items()
                    if brand.id == definition["filament"].brand_id
                ),
                "material_type": definition["filament"].material_type,
                "color_name": definition["filament"].color_name,
            }
            if entry is None:
                entry = CalculatorHistoryEntry(
                    user_id=olga.id,
                    title=definition["title"],
                    pricing_method="combined",
                    request_data=request_data,
                    result_data=result_data,
                    created_at=now - timedelta(days=10 if definition["quantity"] == 24 else 4),
                )
                db.add(entry)
            apply_values(entry, {
                "pricing_method": "combined",
                "request_data": request_data,
                "result_data": result_data,
                "parsed_gcode": parsed_gcode,
                "filament_snapshot": snapshot,
            })
            histories[definition["title"]] = entry
        await db.flush()

        quote = await db.scalar(
            select(CrmQuote).where(CrmQuote.user_id == olga.id, CrmQuote.number == "OC-2026-014")
        )
        customer = None
        if quote is not None and quote.customer_id is not None:
            customer = await db.get(CrmCustomer, quote.customer_id)
        if customer is None:
            customer = CrmCustomer(user_id=olga.id, name=encrypt_field("Atelier Nord"))
            db.add(customer)
        customer.name = encrypt_field("Atelier Nord")
        customer.contact_name = encrypt_field("Мария Соколова")
        customer.email = encrypt_field("orders@atelier-nord.example")
        customer.note = encrypt_field("Регулярные небольшие партии предметов для витрин")
        customer.archived = False
        await db.flush()

        if quote is None:
            quote = CrmQuote(
                user_id=olga.id,
                customer_id=customer.id,
                number="OC-2026-014",
                title="Корпуса датчиков · 24 шт.",
                status=CrmQuoteStatus.SENT,
                currency="RUB",
            )
            db.add(quote)
        apply_values(quote, {
            "customer_id": customer.id,
            "title": "Корпуса датчиков · 24 шт.",
            "status": CrmQuoteStatus.SENT,
            "currency": "RUB",
            "valid_until": date.today() + timedelta(days=12),
            "sent_at": now - timedelta(days=2),
        })
        await db.flush()

        version = await db.scalar(
            select(CrmQuoteVersion).where(
                CrmQuoteVersion.quote_id == quote.id,
                CrmQuoteVersion.version_number == 1,
            )
        )
        if version is None:
            version = CrmQuoteVersion(
                quote_id=quote.id,
                version_number=1,
                source_history_id=histories["Корпуса датчиков · 24 шт."].id,
                seller_snapshot={"name": "Мастерская OlgaCraft"},
                customer_snapshot={"name": "Atelier Nord"},
                calculation_snapshot=histories["Корпуса датчиков · 24 шт."].result_data,
                subtotal=Decimal("18480.00"),
                tax_total=Decimal("0.00"),
                grand_total=Decimal("18480.00"),
            )
            db.add(version)
        version.source_history_id = histories["Корпуса датчиков · 24 шт."].id
        version.seller_snapshot = {"name": "Мастерская OlgaCraft"}
        version.customer_snapshot = {"name": "Atelier Nord"}
        version.calculation_snapshot = histories["Корпуса датчиков · 24 шт."].result_data
        version.payment_terms = "50% перед запуском, остаток после готовности"
        version.subtotal = Decimal("18480.00")
        version.tax_total = Decimal("0.00")
        version.grand_total = Decimal("18480.00")
        await db.flush()

        line = await db.scalar(
            select(CrmQuoteLine).where(CrmQuoteLine.version_id == version.id, CrmQuoteLine.position == 1)
        )
        if line is None:
            line = CrmQuoteLine(
                version_id=version.id,
                position=1,
                title="Комплект корпусов датчиков",
                quantity=Decimal("24"),
                unit="pcs",
                unit_price=Decimal("770.00"),
                total_price=Decimal("18480.00"),
            )
            db.add(line)
        line.details = ["Deep Ocean PLA", "печать 0.20 мм", "контроль посадочных размеров"]
        line.source_data = {"showcase": True}

        order_quote = await db.scalar(
            select(CrmQuote).where(CrmQuote.user_id == olga.id, CrmQuote.number == "OC-2026-009")
        )
        if order_quote is None:
            order_quote = CrmQuote(
                user_id=olga.id,
                customer_id=customer.id,
                number="OC-2026-009",
                title="Настольные органайзеры · 8 шт.",
                status=CrmQuoteStatus.ACCEPTED,
                currency="RUB",
                accepted_at=now - timedelta(days=3),
            )
            db.add(order_quote)
        order_quote.customer_id = customer.id
        order_quote.status = CrmQuoteStatus.ACCEPTED
        order_quote.accepted_at = order_quote.accepted_at or now - timedelta(days=3)
        await db.flush()

        order_version = await db.scalar(
            select(CrmQuoteVersion).where(
                CrmQuoteVersion.quote_id == order_quote.id,
                CrmQuoteVersion.version_number == 1,
            )
        )
        if order_version is None:
            order_version = CrmQuoteVersion(
                quote_id=order_quote.id,
                version_number=1,
                source_history_id=histories["Настольные органайзеры · 8 шт."].id,
                seller_snapshot={"name": "Мастерская OlgaCraft"},
                customer_snapshot={"name": "Atelier Nord"},
                calculation_snapshot=histories["Настольные органайзеры · 8 шт."].result_data,
                subtotal=Decimal("11240.00"),
                tax_total=Decimal("0.00"),
                grand_total=Decimal("11240.00"),
            )
            db.add(order_version)
        order_version.source_history_id = histories["Настольные органайзеры · 8 шт."].id
        order_version.seller_snapshot = {"name": "Мастерская OlgaCraft"}
        order_version.customer_snapshot = {"name": "Atelier Nord"}
        order_version.calculation_snapshot = histories["Настольные органайзеры · 8 шт."].result_data
        order_version.payment_terms = "Оплата после подтверждения макета"
        order_version.subtotal = Decimal("11240.00")
        order_version.tax_total = Decimal("0.00")
        order_version.grand_total = Decimal("11240.00")
        await db.flush()

        order_line = await db.scalar(
            select(CrmQuoteLine).where(
                CrmQuoteLine.version_id == order_version.id,
                CrmQuoteLine.position == 1,
            )
        )
        if order_line is None:
            order_line = CrmQuoteLine(
                version_id=order_version.id,
                position=1,
                title="Комплект настольных органайзеров",
                quantity=Decimal("8"),
                unit="pcs",
                unit_price=Decimal("1405.00"),
                total_price=Decimal("11240.00"),
            )
            db.add(order_line)
        order_line.details = ["Galaxy PLA · Violet Nebula", "8 изделий", "упаковка по комплектам"]
        order_line.source_data = {"showcase": True}

        order = await db.scalar(select(CrmOrder).where(CrmOrder.quote_id == order_quote.id))
        if order is None:
            order = CrmOrder(
                user_id=olga.id,
                quote_id=order_quote.id,
                customer_id=customer.id,
                number="OC-ORDER-2026-009",
                title="Настольные органайзеры · 8 шт.",
                status=CrmOrderStatus.IN_PRODUCTION,
                currency="RUB",
                total=Decimal("11240.00"),
            )
            db.add(order)
        order.status = CrmOrderStatus.IN_PRODUCTION
        order.due_date = date.today() + timedelta(days=5)
        order.note = "Печать партиями по четыре изделия; проверить оттенок перед второй партией."

        event = await db.scalar(
            select(CrmQuoteEvent).where(
                CrmQuoteEvent.quote_id == quote.id,
                CrmQuoteEvent.event_type == CrmQuoteEventType.SHARED,
            )
        )
        if event is None:
            db.add(CrmQuoteEvent(
                quote_id=quote.id,
                actor_user_id=olga.id,
                event_type=CrmQuoteEventType.SHARED,
                details={"showcase": True},
            ))

        await db.commit()

        print("Showcase готов:")
        print(f"  бренды: {len(brands)}")
        print(f"  материалы: {len(filaments)}")
        print(f"  участники сообщества: {len(COMMUNITY_USERS)}")
        print(f"  пользовательские пресеты: {len(community_presets)}")
        print("  заготовки OlgaCraft из OrcaSlicer: 1")
        print(f"  катушки OlgaCraft: {len(olga_spools)}")
        print("  Bambu AMS: 4 назначенных слота")
        print("  расчёты: 2; КП: 1; заказ в производстве: 1")
        print(
            "  технические dev-fixtures скрыты из витрины: "
            f"брендов {hidden_volume_brands}, материалов {hidden_volume_filaments}, "
            f"пресетов {hidden_volume_presets}"
        )
        print(f"  пароль showcase-аккаунтов: {SHOWCASE_PASSWORD}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    return asyncio.run(seed_showcase())


if __name__ == "__main__":
    raise SystemExit(main())
