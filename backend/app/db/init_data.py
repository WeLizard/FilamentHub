"""Script for initializing test data."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.brand import Brand
from app.models.filament import Filament


async def init_test_data() -> None:
    """Create test data."""
    async with AsyncSessionLocal() as db:
        # Check if data exists
        from sqlalchemy import select

        result = await db.execute(select(Brand))
        existing = result.scalar_one_or_none()

        if existing:
            print("Test data already exists, skipping...")
            return

        # Create brands
        brands_data = [
            {
                "name": "Bestfilament",
                "slug": "bestfilament",
                "description": "Российский производитель качественного пластика",
                "website": "https://bestfilament.ru",
                "verified": True,
            },
            {
                "name": "Sunlu",
                "slug": "sunlu",
                "description": "Популярный китайский бренд",
                "website": "https://www.sunlu.com",
                "verified": True,
            },
            {
                "name": "eSUN",
                "slug": "esun",
                "description": "Профессиональные материалы для 3D-печати",
                "website": "https://www.esun3d.com",
                "verified": True,
            },
            {
                "name": "Polymaker",
                "slug": "polymaker",
                "description": "Премиум материалы из Китая",
                "website": "https://polymaker.com",
                "verified": True,
            },
        ]

        brands = []
        for brand_data in brands_data:
            brand = Brand(**brand_data)
            db.add(brand)
            brands.append(brand)

        await db.flush()  # Get brand IDs

        # Create filaments
        filaments_data = [
            {
                "brand_id": brands[0].id,  # Bestfilament
                "name": "PLA Red",
                "material_type": "PLA",
                "color_name": "Red",
                "color_hex": "#FF0000",
                "diameter": 1.75,
                "density": 1.24,
                "price_per_kg": 800.0,
                "spool_weight": 1000.0,
                "description": "Красный PLA от Bestfilament",
            },
            {
                "brand_id": brands[0].id,  # Bestfilament
                "name": "PLA Blue",
                "material_type": "PLA",
                "color_name": "Blue",
                "color_hex": "#0000FF",
                "diameter": 1.75,
                "density": 1.24,
                "price_per_kg": 800.0,
                "spool_weight": 1000.0,
                "description": "Синий PLA от Bestfilament",
            },
            {
                "brand_id": brands[1].id,  # Sunlu
                "name": "PETG Black",
                "material_type": "PETG",
                "color_name": "Black",
                "color_hex": "#000000",
                "diameter": 1.75,
                "density": 1.27,
                "price_per_kg": 950.0,
                "spool_weight": 1000.0,
                "description": "Черный PETG от Sunlu",
            },
            {
                "brand_id": brands[1].id,  # Sunlu
                "name": "PLA+ White",
                "material_type": "PLA",
                "color_name": "White",
                "color_hex": "#FFFFFF",
                "diameter": 1.75,
                "density": 1.24,
                "price_per_kg": 850.0,
                "spool_weight": 1000.0,
                "description": "Белый PLA+ от Sunlu",
            },
            {
                "brand_id": brands[2].id,  # eSUN
                "name": "TPU 95A",
                "material_type": "TPU",
                "color_name": "Transparent",
                "color_hex": "#FFFFFF",
                "diameter": 1.75,
                "density": 1.20,
                "price_per_kg": 1800.0,
                "spool_weight": 500.0,
                "description": "Прозрачный TPU от eSUN",
            },
            {
                "brand_id": brands[3].id,  # Polymaker
                "name": "PolyTerra PLA",
                "material_type": "PLA",
                "color_name": "Natural",
                "color_hex": "#F5E6D3",
                "diameter": 1.75,
                "density": 1.24,
                "price_per_kg": 1200.0,
                "spool_weight": 1000.0,
                "description": "Экологичный PLA от Polymaker",
            },
        ]

        for filament_data in filaments_data:
            filament = Filament(**filament_data)
            db.add(filament)

        await db.commit()
        print("Test data created successfully!")
        print(f"Created {len(brands)} brands and {len(filaments_data)} filaments")


if __name__ == "__main__":
    asyncio.run(init_test_data())

