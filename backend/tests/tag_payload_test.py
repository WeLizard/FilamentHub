"""What a scanned tag says about its filament, and what a scan may do with it."""

import base64
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.spool_compat_resource import SpoolCompatResource
from app.models.spool_tag import SpoolTag
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool
from app.services.tag_payload import decode_tag
from app.services.tag_payload.cbor import CborError, read_item

TAGS = Path(__file__).parent / "fixtures" / "openprinttag"
BASE = "/api/v1/spool_compat"
KEY = "tag_payload_device_key"
UID = "E0040108662F6FBC"


def _tag(name: str) -> bytes:
    return (TAGS / name).read_bytes()


def test_reference_tag_is_read_in_full() -> None:
    decoded = decode_tag("OpenPrintTag", _tag("01_data.bin"), bytes.fromhex(UID))

    assert decoded is not None
    assert decoded.as_response() == {
        "material_class": "FFF", "material": "PLA", "name": "PLA Prusa Galaxy Black",
        "vendor_name": "Prusament", "article_number": "8594173675001", "color_hex": "3D3E3D",
        "diameter": 1.75, "density": 1.24, "weight": 1000.0, "initial_weight": 1012.0,
        "spool_weight": 280.0,
        # One recommended value out of the 205-225 and 40-60 ranges on the tag.
        "extruder_temp": 215, "bed_temp": 50,
        # Derived from the tag's UID as the specification defines.
        "instance_uuid": "bf63e92d-9ca5-53d7-9fab-ffdd0240c585",
    }
    # Readers report NFC-V UIDs in either byte order; both name the same roll.
    reversed_uid = bytes.fromhex(UID)[::-1]
    assert decode_tag("openprinttag", _tag("01_data.bin"), reversed_uid) == decoded


def test_doubtful_values_are_left_out_one_by_one() -> None:
    # A reversed temperature range is dropped; what a printer consumed is still read.
    invalid = decode_tag("openprinttag", _tag("03_data.bin"))
    assert invalid is not None
    assert invalid.extruder_temp is None and invalid.bed_temp == 80
    assert invalid.used_weight == 444.0 and invalid.material == "PETG"
    # Unknown keys and enum values are skipped, as the specification requires.
    minimal = decode_tag("openprinttag", _tag("05_data.bin"))
    assert minimal is not None and minimal.as_response() == {"material_class": "FFF", "diameter": 1.75}


@pytest.mark.parametrize("contents", [
    b"",
    b"\xe1\x40\x27\x01\x03\x05trash\xfe",
    _tag("01_data.bin")[:120],
    b"not a tag at all",
])
def test_unreadable_contents_are_not_decoded(contents: bytes) -> None:
    assert decode_tag("openprinttag", contents) is None
    assert decode_tag("ntag", _tag("01_data.bin")) is None


@pytest.mark.parametrize("raw", [
    bytes.fromhex("c11a514b67b0"),  # a semantic tag
    bytes.fromhex("7f6161ff"),  # an indefinite-length text string
    bytes.fromhex("81" * 12 + "00"),  # nested deeper than any tag needs
    bytes.fromhex("a1"),  # a map cut short
    bytes.fromhex("a1f500"),  # a map keyed by a boolean
])
def test_cbor_reader_refuses_what_a_filament_tag_never_needs(raw: bytes) -> None:
    with pytest.raises(CborError):
        read_item(raw)


def test_cbor_reader_reads_the_forms_tags_use() -> None:
    # An indefinite map with integer keys, a byte string, a half float and a nested array.
    value, end = read_item(bytes.fromhex("bf0118d2024301020303f93cf6049f0001ffff00"))
    assert value == {1: 210, 2: b"\x01\x02\x03", 3: 1.240234375, 4: [0, 1]}
    assert end == 19
    # A repeated key keeps its first value.
    assert read_item(bytes.fromhex("a201010102"))[0] == {1: 1}


async def _account(db: AsyncSession) -> User:
    user = User(email="tag-payload@example.com", username="tag_payload_user", password_hash="x", active=True)
    device = UserPrinterDevice(
        user=user, name="Voron", device_fingerprint="tag-payload-fp", api_key=KEY, supports_hh=True,
    )
    db.add_all([user, device])
    await db.commit()
    return user


def _scan(name: str, **extra: object) -> dict:
    return {
        "uid": UID, "reader_id": "bench", "format": "openprinttag",
        "payload_b64": base64.b64encode(_tag(name)).decode(), **extra,
    }


@pytest.mark.asyncio
async def test_scan_describes_an_unknown_tag_and_creates_only_when_asked(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user = await _account(db_session)

    looked = await client.post(f"{BASE}/{KEY}/v1/tag/scan", json=_scan("01_data.bin"))
    assert looked.json()["decoded"]["name"] == "PLA Prusa Galaxy Black"
    assert looked.json()["created"] is False and looked.json()["matched_spool_id"] is None
    assert await db_session.scalar(select(func.count()).select_from(UserSpool)) == 0

    made = await client.post(f"{BASE}/{KEY}/v1/tag/scan", json=_scan("01_data.bin", create=True))
    again = await client.post(f"{BASE}/{KEY}/v1/tag/scan", json=_scan("01_data.bin", create=True))

    assert made.json()["created"] is True
    spool = made.json()["spool"]
    assert made.json()["matched_spool_id"] == spool["id"]
    assert spool["initial_weight"] == 1012.0 and spool["spool_weight"] == 280.0
    assert spool["filament"]["name"] == "PLA Prusa Galaxy Black"
    assert spool["filament"]["vendor"]["name"] == "Prusament"
    assert [tag["uid"] for tag in spool["tags"]] == [UID]
    # The same tag scanned again is an ordinary match, not a second spool.
    assert again.json()["created"] is False and again.json()["matched_spool_id"] == spool["id"]
    assert await db_session.scalar(
        select(func.count()).select_from(UserSpool).where(UserSpool.user_id == user.id)
    ) == 1

    # A tag that states neither its material nor its weight cannot become a spool.
    empty = await client.post(
        f"{BASE}/{KEY}/v1/tag/scan", json={**_scan("05_data.bin", create=True), "uid": "E004010811223344"}
    )
    assert empty.json()["created"] is False and empty.json()["matched_spool_id"] is None
    assert await db_session.scalar(select(func.count()).select_from(SpoolTag)) == 1


@pytest.mark.asyncio
async def test_a_tag_for_a_catalog_filament_creates_a_spool_of_that_filament(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    await _account(db_session)
    brand = Brand(name="PRUSAMENT", slug="prusament-tag", verified=True, active=True)
    galaxy = Filament(
        brand=brand, name="PLA Galaxy Black", slug="prusament-pla-galaxy-black", material_type="PLA",
        color_hex="#3E3F3E", diameter=1.75, density=1.24, spool_weight=1000.0, active=True,
    )
    other = Filament(
        brand=brand, name="PLA Lipstick Red", slug="prusament-pla-red", material_type="PLA",
        color_hex="#C8102E", diameter=1.75, active=True,
    )
    db_session.add_all([brand, galaxy, other])
    await db_session.commit()

    made = await client.post(f"{BASE}/{KEY}/v1/tag/scan", json=_scan("01_data.bin", create=True))

    assert made.json()["created"] is True
    stored = await db_session.scalar(select(UserSpool))
    # The brand differs only in case and the colour by a shade: it is the catalog's filament.
    assert stored is not None and stored.filament_id == galaxy.id
    assert made.json()["spool"]["filament"]["external_id"] == f"filamenthub-{galaxy.id}"
    assert await db_session.scalar(
        select(func.count()).select_from(SpoolCompatResource).where(
            SpoolCompatResource.source_kind == "import"
        )
    ) == 0
