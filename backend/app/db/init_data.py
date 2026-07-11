"""Script for initializing test data."""

import asyncio

from app.db.session import AsyncSessionLocal
from app.models.filament import Filament
from app.models.preset import Preset


async def init_test_data() -> None:
    """Create test data."""
    import socket

    from app.db.session import engine

    # Retry logic for Docker network DNS resolution
    max_retries = 30
    retry_delay = 1

    # Test database connection before proceeding
    from sqlalchemy import text
    for attempt in range(max_retries):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))  # Simple query to test connection
                break  # Success, exit retry loop
        except (socket.gaierror, OSError, Exception) as e:
            if attempt < max_retries - 1:
                print(f"⚠️  Database connection attempt {attempt + 1}/{max_retries} failed: {e}")
                print(f"   Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                # Last attempt failed, raise the error
                raise

    # Now proceed with database operations
    async with AsyncSessionLocal() as db:
        from sqlalchemy import func, select

        # Check if presets already exist
        preset_count = await db.execute(select(func.count(Preset.id)))
        preset_count_val = preset_count.scalar() or 0

        if preset_count_val > 0:
            print(f"Found {preset_count_val} presets in database, skipping preset creation...")
            return

        # Get existing filaments
        filament_result = await db.execute(select(Filament).order_by(Filament.id))
        filaments = list(filament_result.scalars().all())

        if not filaments or len(filaments) < 6:
            print("Not enough filaments in database. Please create filaments first.")
            return

        # Create presets for each filament
        # Official presets (from manufacturers)
        official_presets_data = [
            # PLA Red (filament 0)
            {
                "filament_id": filaments[0].id,
                "name": "Официальный пресет производителя",
                "description": "Рекомендуемые настройки от производителя",
                "is_official": True,
                "extruder_temp": 200.0,
                "bed_temp": 60.0,
                "print_speed": 50.0,
                "travel_speed": 150.0,
                "layer_height": 0.2,
                "flow_rate": 100.0,
                "fan_speed": 100,
                "retraction_length": 5.0,
                "retraction_speed": 45.0,
                "moderation_status": "approved",
            },
            # PLA Blue (filament 1)
            {
                "filament_id": filaments[1].id,
                "name": "Официальный пресет производителя",
                "description": "Рекомендуемые настройки от производителя",
                "is_official": True,
                "extruder_temp": 200.0,
                "bed_temp": 60.0,
                "print_speed": 50.0,
                "travel_speed": 150.0,
                "layer_height": 0.2,
                "flow_rate": 100.0,
                "fan_speed": 100,
                "retraction_length": 5.0,
                "retraction_speed": 45.0,
                "moderation_status": "approved",
            },
            # PETG Black (filament 2)
            {
                "filament_id": filaments[2].id,
                "name": "Официальный пресет производителя",
                "description": "Рекомендуемые настройки от производителя",
                "is_official": True,
                "extruder_temp": 240.0,
                "bed_temp": 80.0,
                "print_speed": 40.0,
                "travel_speed": 150.0,
                "layer_height": 0.2,
                "flow_rate": 98.0,
                "fan_speed": 50,
                "retraction_length": 6.0,
                "retraction_speed": 40.0,
                "moderation_status": "approved",
            },
            # PLA+ White (filament 3)
            {
                "filament_id": filaments[3].id,
                "name": "Официальный пресет производителя",
                "description": "Рекомендуемые настройки от производителя",
                "is_official": True,
                "extruder_temp": 210.0,
                "bed_temp": 60.0,
                "print_speed": 55.0,
                "travel_speed": 150.0,
                "layer_height": 0.2,
                "flow_rate": 100.0,
                "fan_speed": 100,
                "retraction_length": 5.0,
                "retraction_speed": 45.0,
                "moderation_status": "approved",
            },
            # TPU 95A (filament 4)
            {
                "filament_id": filaments[4].id,
                "name": "Официальный пресет eSUN",
                "description": "Рекомендуемые настройки от производителя",
                "is_official": True,
                "extruder_temp": 230.0,
                "bed_temp": 50.0,
                "print_speed": 25.0,
                "travel_speed": 100.0,
                "layer_height": 0.2,
                "flow_rate": 95.0,
                "fan_speed": 0,
                "retraction_length": 3.0,
                "retraction_speed": 30.0,
                "moderation_status": "approved",
            },
            # PolyTerra PLA (filament 5)
            {
                "filament_id": filaments[5].id,
                "name": "Официальный пресет Polymaker",
                "description": "Рекомендуемые настройки от производителя",
                "is_official": True,
                "extruder_temp": 205.0,
                "bed_temp": 60.0,
                "print_speed": 50.0,
                "travel_speed": 150.0,
                "layer_height": 0.2,
                "flow_rate": 100.0,
                "fan_speed": 100,
                "retraction_length": 5.0,
                "retraction_speed": 45.0,
                "moderation_status": "approved",
            },
        ]

        # Community presets (from users)
        community_presets_data = [
            # For PLA Red
            {
                "filament_id": filaments[0].id,
                "name": "3D_Guru",
                "description": "Проверенная настройка для Ender 3 Pro",
                "is_official": False,
                "extruder_temp": 195.0,
                "bed_temp": 60.0,
                "print_speed": 45.0,
                "travel_speed": 150.0,
                "layer_height": 0.2,
                "flow_rate": 100.0,
                "fan_speed": 100,
                "retraction_length": 5.0,
                "retraction_speed": 45.0,
                "moderation_status": "approved",
            },
            {
                "filament_id": filaments[0].id,
                "name": "PrintMaster",
                "description": "Оптимизированная настройка для высокой скорости",
                "is_official": False,
                "extruder_temp": 205.0,
                "bed_temp": 55.0,
                "print_speed": 55.0,
                "travel_speed": 150.0,
                "layer_height": 0.2,
                "flow_rate": 100.0,
                "fan_speed": 100,
                "retraction_length": 5.0,
                "retraction_speed": 45.0,
                "moderation_status": "approved",
            },
            # For PETG Black
            {
                "filament_id": filaments[2].id,
                "name": "PETG_Pro",
                "description": "Оптимальные настройки для прочности",
                "is_official": False,
                "extruder_temp": 235.0,
                "bed_temp": 85.0,
                "print_speed": 35.0,
                "travel_speed": 150.0,
                "layer_height": 0.2,
                "flow_rate": 98.0,
                "fan_speed": 50,
                "retraction_length": 6.0,
                "retraction_speed": 40.0,
                "moderation_status": "approved",
            },
        ]

        # Add all presets. print/travel speed и layer heights — process-scope,
        # на filament-пресете их нет (модель их не имеет) → отбрасываем из сид-данных.
        _process_keys = {"print_speed", "travel_speed", "layer_height", "first_layer_height"}
        for preset_data in official_presets_data + community_presets_data:
            preset = Preset(**{k: v for k, v in preset_data.items() if k not in _process_keys})
            db.add(preset)

        await db.commit()
        print("Presets created successfully!")
        print(f"Created {len(official_presets_data)} official presets and {len(community_presets_data)} community presets")


if __name__ == "__main__":
    asyncio.run(init_test_data())
