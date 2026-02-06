"""Tests for OrcaSlicer validator service.

This module tests the OrcaSlicerValidator service which handles:
- Parent preset validation (known system presets vs unknown)
- Batch preset validation with errors and warnings
- Temperature range validation for filaments
- Fallback suggestions for unknown parent presets
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus


# Note: The following imports will work once OrcaSlicerValidator service
# is merged from the main workspace. For now, these tests document expected behavior.
try:
    from app.services.orcaslicer_validator import OrcaSlicerValidator
    VALIDATOR_AVAILABLE = True
except ImportError:
    VALIDATOR_AVAILABLE = False
    OrcaSlicerValidator = None


pytestmark = pytest.mark.skipif(
    not VALIDATOR_AVAILABLE,
    reason="OrcaSlicerValidator service not available in this worktree"
)


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        email="validator_test@example.com",
        username="validator_user",
        hashed_password="$2b$12$test",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_brand(db_session: AsyncSession) -> Brand:
    """Create a test brand."""
    brand = Brand(
        name="Validator Test Brand",
        slug="validator-test-brand",
        verified=True,
        active=True,
    )
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    return brand


@pytest.fixture
async def test_filament(db_session: AsyncSession, test_brand: Brand) -> Filament:
    """Create a test filament."""
    filament = Filament(
        brand_id=test_brand.id,
        name="Test PLA",
        material_type="PLA",
        color_name="Red",
        color_hex="#FF0000",
        diameter=1.75,
        density=1.24,
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    return filament


@pytest.fixture
async def system_preset(
    db_session: AsyncSession, test_user: User, test_filament: Filament
) -> Preset:
    """Create a system preset (parent preset)."""
    preset = Preset(
        name="Generic PLA @System",
        slug="generic-pla-system",
        description="System default PLA preset",
        filament_id=test_filament.id,
        created_by_id=test_user.id,
        preset_type="filament",
        moderation_status=PresetModerationStatus.PUBLISHED,
        is_system_preset=True,
        active=True,
        orcaslicer_json={
            "type": "filament",
            "name": "Generic PLA @System",
            "version": "1.0.0.0",
            "from": "system",
            "inherits": "",
            "filament_settings_id": ["Generic PLA @System"],
            "setting_id": "Generic PLA @System",
            "nozzle_temperature": [220],
            "hot_plate_temp": [60],
            "cool_plate_temp": [35],
        },
    )
    db_session.add(preset)
    await db_session.commit()
    await db_session.refresh(preset)
    return preset


@pytest.fixture
def validator(db_session: AsyncSession) -> OrcaSlicerValidator:
    """Create an OrcaSlicerValidator instance."""
    return OrcaSlicerValidator(db_session)


@pytest.mark.asyncio
async def test_validate_known_parent_preset(
    validator: OrcaSlicerValidator,
    system_preset: Preset,
    db_session: AsyncSession,
):
    """Test validating a preset with a known system parent."""
    # Validate preset that inherits from known system preset
    result = await validator.validate_parent_preset(
        parent_name="Generic PLA @System",
        preset_type="filament"
    )

    assert result["valid"] is True
    assert result["parent_found"] is True
    assert result["parent_preset_id"] == system_preset.id
    assert "errors" not in result or len(result["errors"]) == 0


@pytest.mark.asyncio
async def test_validate_unknown_parent_preset(
    validator: OrcaSlicerValidator,
    db_session: AsyncSession,
):
    """Test validating a preset with an unknown parent - should suggest fallback."""
    # Validate preset with non-existent parent
    result = await validator.validate_parent_preset(
        parent_name="NonExistent PLA @Unknown",
        preset_type="filament"
    )

    assert result["valid"] is False
    assert result["parent_found"] is False
    assert "fallback_suggestion" in result
    assert result["fallback_suggestion"] is not None
    assert "confidence_score" in result
    # Confidence score should be between 0 and 1
    assert 0 <= result["confidence_score"] <= 1
    # Should suggest a known system preset as fallback
    assert "Generic PLA" in result["fallback_suggestion"] or "System" in result["fallback_suggestion"]


@pytest.mark.asyncio
async def test_validate_preset_batch_valid(
    validator: OrcaSlicerValidator,
    system_preset: Preset,
    test_filament: Filament,
    db_session: AsyncSession,
):
    """Test batch validation with all valid presets."""
    # Create batch of valid preset data
    batch = [
        {
            "name": "My Custom PLA",
            "preset_type": "filament",
            "inherits": "Generic PLA @System",
            "orcaslicer_json": {
                "type": "filament",
                "name": "My Custom PLA",
                "version": "1.0.0.0",
                "from": "user",
                "inherits": "Generic PLA @System",
                "filament_settings_id": ["My Custom PLA"],
                "setting_id": "My Custom PLA",
                "nozzle_temperature": [215],
                "hot_plate_temp": [60],
                "cool_plate_temp": [35],
            },
        },
        {
            "name": "My Second PLA",
            "preset_type": "filament",
            "inherits": "Generic PLA @System",
            "orcaslicer_json": {
                "type": "filament",
                "name": "My Second PLA",
                "version": "1.0.0.0",
                "from": "user",
                "inherits": "Generic PLA @System",
                "filament_settings_id": ["My Second PLA"],
                "setting_id": "My Second PLA",
                "nozzle_temperature": [220],
                "hot_plate_temp": [55],
                "cool_plate_temp": [30],
            },
        },
    ]

    result = await validator.validate_batch(batch)

    assert "results" in result
    assert len(result["results"]) == 2
    assert result["total_count"] == 2
    assert result["valid_count"] == 2
    assert result["error_count"] == 0
    assert result["warning_count"] == 0

    # Check individual results
    for item_result in result["results"]:
        assert item_result["valid"] is True
        assert len(item_result.get("errors", [])) == 0


@pytest.mark.asyncio
async def test_validate_preset_batch_with_errors(
    validator: OrcaSlicerValidator,
    db_session: AsyncSession,
):
    """Test batch validation with some invalid presets."""
    # Create batch with invalid preset data
    batch = [
        {
            "name": "Valid PLA",
            "preset_type": "filament",
            "inherits": "Generic PLA @System",
            "orcaslicer_json": {
                "type": "filament",
                "name": "Valid PLA",
                "version": "1.0.0.0",
                "from": "user",
                "inherits": "Generic PLA @System",
                "filament_settings_id": ["Valid PLA"],
                "setting_id": "Valid PLA",
                "nozzle_temperature": [220],
            },
        },
        {
            "name": "Invalid - Unknown Parent",
            "preset_type": "filament",
            "inherits": "NonExistent Parent @System",
            "orcaslicer_json": {
                "type": "filament",
                "name": "Invalid - Unknown Parent",
                "version": "1.0.0.0",
                "from": "user",
                "inherits": "NonExistent Parent @System",
                "filament_settings_id": ["Invalid"],
                "setting_id": "Invalid",
            },
        },
        {
            "name": "Invalid - Missing Fields",
            "preset_type": "filament",
            "inherits": "Generic PLA @System",
            "orcaslicer_json": {
                "type": "filament",
                "name": "Invalid - Missing Fields",
                # Missing required fields: version, from, filament_settings_id, setting_id
            },
        },
        {
            "name": "Invalid - Extreme Temperature",
            "preset_type": "filament",
            "inherits": "Generic PLA @System",
            "orcaslicer_json": {
                "type": "filament",
                "name": "Invalid - Extreme Temperature",
                "version": "1.0.0.0",
                "from": "user",
                "inherits": "Generic PLA @System",
                "filament_settings_id": ["Invalid Temp"],
                "setting_id": "Invalid Temp",
                "nozzle_temperature": [600],  # Too high for PLA
            },
        },
    ]

    result = await validator.validate_batch(batch)

    assert "results" in result
    assert len(result["results"]) == 4
    assert result["total_count"] == 4
    assert result["valid_count"] < 4  # At least some should be invalid
    assert result["error_count"] > 0  # Should have errors

    # First preset should be valid
    assert result["results"][0]["valid"] is True

    # Second preset should be invalid (unknown parent)
    assert result["results"][1]["valid"] is False
    assert len(result["results"][1]["errors"]) > 0
    assert "fallback_suggestion" in result["results"][1]

    # Third preset should be invalid (missing fields)
    assert result["results"][2]["valid"] is False
    assert len(result["results"][2]["errors"]) > 0

    # Fourth preset should have warnings or errors (extreme temperature)
    fourth_result = result["results"][3]
    assert len(fourth_result.get("errors", [])) > 0 or len(fourth_result.get("warnings", [])) > 0


@pytest.mark.asyncio
async def test_temperature_range_validation(
    validator: OrcaSlicerValidator,
    system_preset: Preset,
    db_session: AsyncSession,
):
    """Test temperature range validation for filament presets."""
    # Test with valid temperature
    valid_temp_result = await validator.validate_temperatures(
        preset_type="filament",
        material_type="PLA",
        temperatures={
            "nozzle_temperature": [220],
            "hot_plate_temp": [60],
            "cool_plate_temp": [35],
        }
    )

    assert valid_temp_result["valid"] is True
    assert len(valid_temp_result.get("errors", [])) == 0
    assert len(valid_temp_result.get("warnings", [])) == 0

    # Test with temperature too high for PLA
    high_temp_result = await validator.validate_temperatures(
        preset_type="filament",
        material_type="PLA",
        temperatures={
            "nozzle_temperature": [280],  # Too high for PLA
            "hot_plate_temp": [60],
            "cool_plate_temp": [35],
        }
    )

    assert high_temp_result["valid"] is False or len(high_temp_result.get("warnings", [])) > 0
    # Should have a warning about temperature being outside recommended range

    # Test with temperature too low
    low_temp_result = await validator.validate_temperatures(
        preset_type="filament",
        material_type="PLA",
        temperatures={
            "nozzle_temperature": [150],  # Too low for PLA
            "hot_plate_temp": [60],
            "cool_plate_temp": [35],
        }
    )

    assert low_temp_result["valid"] is False or len(low_temp_result.get("warnings", [])) > 0

    # Test PETG (different material, different range)
    petg_result = await validator.validate_temperatures(
        preset_type="filament",
        material_type="PETG",
        temperatures={
            "nozzle_temperature": [240],  # Valid for PETG
            "hot_plate_temp": [80],
            "cool_plate_temp": [45],
        }
    )

    assert petg_result["valid"] is True
    assert len(petg_result.get("errors", [])) == 0


@pytest.mark.asyncio
async def test_validate_printer_preset(
    validator: OrcaSlicerValidator,
    db_session: AsyncSession,
):
    """Test validation of printer (machine) presets."""
    printer_data = {
        "name": "My Custom Printer",
        "preset_type": "printer",
        "orcaslicer_json": {
            "type": "machine",
            "name": "My Custom Printer",
            "version": "1.0.0.0",
            "from": "user",
            "printer_settings_id": ["My Custom Printer"],
            "setting_id": "My Custom Printer",
            "nozzle_diameter": [0.4],
            "max_print_height": [250],
        },
    }

    result = await validator.validate_preset(printer_data)

    assert "valid" in result
    # Should validate structure even without parent preset for printers
    assert result["valid"] is True or len(result.get("errors", [])) == 0


@pytest.mark.asyncio
async def test_validate_print_preset(
    validator: OrcaSlicerValidator,
    db_session: AsyncSession,
):
    """Test validation of print (process) presets."""
    print_data = {
        "name": "My Custom Print Settings",
        "preset_type": "print",
        "orcaslicer_json": {
            "type": "process",
            "name": "My Custom Print Settings",
            "version": "1.0.0.0",
            "from": "user",
            "print_settings_id": ["My Custom Print Settings"],
            "setting_id": "My Custom Print Settings",
            "layer_height": [0.2],
            "compatible_printers": ["Generic Printer"],  # Required for print presets
        },
    }

    result = await validator.validate_preset(print_data)

    assert "valid" in result
    # Print presets require compatible_printers to not be empty
    assert result["valid"] is True


@pytest.mark.asyncio
async def test_validate_print_preset_missing_compatible_printers(
    validator: OrcaSlicerValidator,
    db_session: AsyncSession,
):
    """Test that print presets fail validation without compatible_printers."""
    print_data = {
        "name": "Invalid Print Settings",
        "preset_type": "print",
        "orcaslicer_json": {
            "type": "process",
            "name": "Invalid Print Settings",
            "version": "1.0.0.0",
            "from": "user",
            "print_settings_id": ["Invalid Print Settings"],
            "setting_id": "Invalid Print Settings",
            "layer_height": [0.2],
            "compatible_printers": [],  # Empty - should fail
        },
    }

    result = await validator.validate_preset(print_data)

    assert result["valid"] is False
    assert len(result.get("errors", [])) > 0
    # Should have error about compatible_printers being empty
    error_messages = " ".join(result.get("errors", []))
    assert "compatible_printers" in error_messages.lower()


@pytest.mark.asyncio
async def test_fallback_suggestion_confidence_scoring(
    validator: OrcaSlicerValidator,
    system_preset: Preset,
    db_session: AsyncSession,
):
    """Test that fallback suggestions have appropriate confidence scores."""
    # Test with similar name
    similar_result = await validator.validate_parent_preset(
        parent_name="Generic PLA Custom",  # Similar to "Generic PLA @System"
        preset_type="filament"
    )

    assert similar_result["parent_found"] is False
    assert "fallback_suggestion" in similar_result
    assert "confidence_score" in similar_result
    # Should have higher confidence for similar names
    assert similar_result["confidence_score"] > 0.5

    # Test with very different name
    different_result = await validator.validate_parent_preset(
        parent_name="Completely Different Material @XYZ",
        preset_type="filament"
    )

    assert different_result["parent_found"] is False
    assert "fallback_suggestion" in different_result
    assert "confidence_score" in different_result
    # May have lower confidence for very different names
