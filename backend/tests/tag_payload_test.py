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
from app.services.tag_payload import decode_tag, identify_tag
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


def _tigertag(**changes: bytes) -> bytes:
    """The Rosa3D red PLA chip of the TigerTag specification's worked example."""
    fields = {
        "magic": bytes.fromhex("5BF59264"), "product": bytes.fromhex("FFFFFFFF"),
        "material": bytes.fromhex("954B"), "aspects": bytes.fromhex("6800"),
        # The example prints the brand as 0x4E19, but its decimal 19961 - the id the
        # registry lists for Rosa3D - is 0x4DF9.
        "type": bytes.fromhex("8E"), "diameter": bytes.fromhex("38"), "brand": bytes.fromhex("4DF9"),
        "color": bytes.fromhex("FF0000FF"), "measure": bytes.fromhex("0003E8"), "unit": bytes.fromhex("15"),
        "nozzle": bytes.fromhex("00C300E6"), "drying": bytes.fromhex("3205"), "bed": bytes.fromhex("323C"),
        "timestamp": bytes.fromhex("2F7A0A5C"), "more_colors": bytes(8), "td": bytes.fromhex("00E60000"),
        "message": b"Starter Red".ljust(28, b"\x00"), "available": bytes.fromhex("0003E8"),
        "reserved": bytes(1),
    }
    fields.update(changes)
    payload = b"".join(fields.values())
    assert len(payload) == 80
    return payload


def test_tigertag_chip_is_read_from_its_ids() -> None:
    payload = _tigertag()
    decoded = decode_tag("TigerTag", payload)

    assert decoded is not None
    assert decoded.as_response() == {
        "material_class": "FFF", "material": "PLA", "name": "PLA", "vendor_name": "Rosa3D",
        "color_hex": "FF0000", "diameter": 1.75, "density": 1.24, "weight": 1000.0,
        "initial_weight": 1000.0, "used_weight": 0.0,
        # One recommended value out of 195-230 and 50-60.
        "extruder_temp": 213, "bed_temp": 55,
    }
    # A full chip dump carries four system pages before the payload.
    assert decode_tag("tigertag", bytes(16) + payload + bytes(64)) == decoded


def test_tigertag_states_only_what_its_ids_and_fields_support() -> None:
    # A scale wrote 640 g left on a 1 kg roll of silk filament.
    used = decode_tag("tigertag", _tigertag(aspects=bytes.fromhex("5C00"), available=bytes.fromhex("000280")))
    assert used is not None and (used.name, used.used_weight) == ("PLA Silk", 360.0)
    # Ids the registry does not know are left out, not guessed.
    unknown = decode_tag("tigertag", _tigertag(material=bytes.fromhex("0001"), brand=bytes.fromhex("0002")))
    assert unknown is not None
    assert (unknown.material, unknown.name, unknown.vendor_name, unknown.density) == (None, None, None, None)
    # A quantity in millilitres is not a filament weight.
    volume = decode_tag("tigertag", _tigertag(unit=bytes.fromhex("30")))
    assert volume is not None and volume.weight is None and volume.used_weight is None
    # A blank initialization chip and a foreign payload carry nothing to decode.
    assert decode_tag("tigertag", _tigertag(magic=bytes.fromhex("6C41A2E1"))) is None
    assert decode_tag("tigertag", bytes(80)) is None
    assert decode_tag("tigertag", _tigertag()[:60]) is None


def _ndef_media(mime: bytes, payload: bytes) -> bytes:
    """One NDEF media record as a TLV block, the way an NTAG21x stores it."""
    record = bytes([0xD2, len(mime)]) + (
        bytes([len(payload)]) if len(payload) < 256 else b""
    ) + mime + payload
    if len(payload) >= 256:  # a long record: header without the short flag
        record = bytes([0xC2, len(mime)]) + len(payload).to_bytes(4, "big") + mime + payload
    tlv = bytes([0x03, len(record)]) if len(record) < 255 else bytes([0x03, 0xFF]) + len(record).to_bytes(2, "big")
    return tlv + record + bytes([0xFE])


def _ntag215_dump(user_pages: bytes) -> bytes:
    """A full NTAG215 dump: UID, lock bytes, the capability container, user memory."""
    system = bytes.fromhex("04112288") + bytes.fromhex("33445566") + bytes.fromhex("77480000") + bytes.fromhex("E1103E00")
    return system + user_pages.ljust(504, b"\x00")


OPENSPOOL = (
    b'{"protocol":"openspool","version":"1.0","type":"petg","color_hex":"#ffaabb",'
    b'"brand":"Elegoo","min_temp":"230","max_temp":"250","subtype":"Rapid"}'
)


def test_openspool_tag_is_read_from_its_json_record() -> None:
    expected = {
        "material_class": "FFF", "material": "PETG", "name": "PETG Rapid", "vendor_name": "Elegoo",
        "color_hex": "FFAABB", "extruder_temp": 240,
    }
    message = _ndef_media(b"application/json", OPENSPOOL)
    # A full chip dump, the user pages alone and a bare NDEF message read the same.
    for contents in (_ntag215_dump(message), message, message[2:-1]):
        decoded = decode_tag("OpenSpool", contents)
        assert decoded is not None and decoded.as_response() == expected


def test_openspool_states_only_what_makes_sense() -> None:
    document = (
        b'{"protocol":"openspool","type":"PLA","color_hex":"not a colour","brand":"Generic",'
        b'"min_temp":900,"max_temp":215}'
    )
    decoded = decode_tag("openspool", _ndef_media(b"application/json", document))
    # The placeholder brand, a broken colour and an impossible temperature are left out.
    assert decoded is not None
    assert decoded.as_response() == {"material_class": "FFF", "material": "PLA", "name": "PLA", "extruder_temp": 215}
    # JSON of another protocol, or a record of another type, is not OpenSpool.
    assert decode_tag("openspool", _ndef_media(b"application/json", b'{"protocol":"other"}')) is None
    assert decode_tag("openspool", _ndef_media(b"text/plain", OPENSPOOL)) is None
    assert decode_tag("openspool", _ndef_media(b"application/json", b"{broken")) is None


def test_the_chip_a_reader_saw_picks_the_format() -> None:
    tigertag_dump = bytes(16) + _tigertag() + bytes(64)
    assert identify_tag("ntag213", tigertag_dump)[0] == "tigertag"
    assert identify_tag("ntag215", _ntag215_dump(_ndef_media(b"application/json", OPENSPOOL)))[0] == "openspool"
    assert identify_tag("iso15693", _tag("01_data.bin"), bytes.fromhex(UID))[0] == "openprinttag"
    # A chip the reader did not name tries every format.
    assert identify_tag(None, tigertag_dump)[0] == "tigertag"
    # A blank tag, or a FilamentHub address alone, describes no filament.
    address = bytes([0xD1, 0x01, 0x10, 0x55, 0x04]) + b"filamenthub.ru/qr/x"
    assert identify_tag("ntag215", _ntag215_dump(bytes([0x03, len(address)]) + address + b"\xfe")) is None
    assert identify_tag("ntag215", _ntag215_dump(b"")) is None


@pytest.mark.asyncio
async def test_identify_answers_with_the_spool_or_with_what_a_free_tag_describes(
    auth_client: AsyncClient, auth_user: User, db_session: AsyncSession,
) -> None:
    brand = Brand(name="Elegoo", slug="elegoo-identify", verified=True, active=True)
    rapid = Filament(
        brand=brand, name="Rapid PETG Pink", slug="elegoo-rapid-petg-pink", material_type="PETG",
        color_hex="#FFAABB", diameter=1.75, active=True,
    )
    spool = UserSpool(user_id=auth_user.id, initial_weight_g=1000.0, source="manual")
    db_session.add_all([brand, rapid, spool])
    await db_session.commit()
    data = base64.b64encode(_ntag215_dump(_ndef_media(b"application/json", OPENSPOOL))).decode()

    free = await auth_client.post(
        "/api/v1/spool-tags/identify", json={"uid": "04:11:22:33:44:55:66", "chip": "ntag215", "data": data},
    )
    assert free.status_code == 200
    assert free.json() == {
        "uid": "04112233445566", "status": "unlinked", "spool_id": None, "format": "openspool",
        "decoded": {
            "material_class": "FFF", "material": "PETG", "name": "PETG Rapid", "vendor_name": "Elegoo",
            "color_hex": "FFAABB", "extruder_temp": 240,
        },
        "filament_id": rapid.id,
    }

    linked = await auth_client.post(
        f"/api/v1/spool-tags/{spool.id}", json={"uid": "04112233445566", "technology": "nfc", "format": "ntag215"},
    )
    assert linked.status_code == 201
    matched = await auth_client.post("/api/v1/spool-tags/identify", json={"uid": "04112233445566", "data": data})
    assert matched.json()["status"] == "matched" and matched.json()["spool_id"] == spool.id
    assert matched.json()["decoded"] is None

    # Contents that are not base64, or not a known format, still answer: the tag is free.
    for broken in ("%%%", base64.b64encode(b"\x00" * 64).decode()):
        answer = await auth_client.post("/api/v1/spool-tags/identify", json={"uid": "0499", "data": broken})
        assert answer.status_code == 200
        assert answer.json()["status"] == "unlinked" and answer.json()["format"] is None

