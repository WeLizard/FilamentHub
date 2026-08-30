"""Stage B tests: physical printers derived from connection observations."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer import Printer
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.printer_connection_observation import PrinterConnectionObservationIn
from app.services.physical_printer_discovery_service import (
    display_endpoint,
    normalize_endpoint,
    reconcile_user_printers,
)
from app.services.printer_connection_observation_service import record_observations
from app.services.printer_identity_service import discovery_key, endpoint_token


async def _make_profile(db: AsyncSession, user: User, suffix: str, setting_id: str) -> PrinterProfile:
    profile = PrinterProfile(
        owner_user_id=user.id, name=f"Voron {suffix}", slug=f"voron-{suffix}",
        setting_id=setting_id, active=True,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


def _obs(**kw) -> PrinterConnectionObservationIn:
    return PrinterConnectionObservationIn(**kw)


async def _observe(db: AsyncSession, user: User, observations: list[PrinterConnectionObservationIn]) -> None:
    await record_observations(db, user.id, "inst-1", observations)


async def _count(db: AsyncSession, model) -> int:
    return (await db.execute(select(func.count(model.id)))).scalar_one()


@pytest.mark.asyncio
async def test_new_endpoint_creates_physical_printer(db_session: AsyncSession, auth_user: User):
    await _observe(db_session, auth_user, [
        _obs(printer_settings_id="Voron 0.4", printer_model="Voron 2.4",
             print_host="192.168.1.21", host_type="moonraker"),
    ])
    created = await reconcile_user_printers(db_session, auth_user.id)
    assert created == 1
    printer = (await db_session.execute(select(UserPrinterDevice))).scalar_one()
    assert printer.name == "Voron 2.4"
    binding = (await db_session.execute(select(PrinterConnectionBinding))).scalar_one()
    assert binding.provider == "moonraker"
    assert binding.host is None
    assert display_endpoint(binding) == "192.168.1.21:80"
    assert binding.physical_printer_id == printer.id


@pytest.mark.asyncio
async def test_known_endpoint_is_idempotent(db_session: AsyncSession, auth_user: User):
    obs = [_obs(printer_settings_id="Voron 0.4", print_host="192.168.1.21", host_type="moonraker")]
    for _ in range(2):
        await _observe(db_session, auth_user, obs)
        await reconcile_user_printers(db_session, auth_user.id)
    assert await _count(db_session, UserPrinterDevice) == 1
    assert await _count(db_session, PrinterConnectionBinding) == 1


@pytest.mark.asyncio
async def test_sync_does_not_rename_existing_physical_printer(
    db_session: AsyncSession, auth_user: User
):
    preset_name = "Voron 2.4 350 0.4 nozzle - Copy"
    await _observe(
        db_session,
        auth_user,
        [
            _obs(
                preset_name=preset_name,
                printer_model="Voron 2.4 350",
                print_host="192.168.1.21",
                host_type="moonraker",
            )
        ],
    )
    printer = UserPrinterDevice(
        user_id=auth_user.id,
        name=preset_name,
        supports_hh=False,
    )
    db_session.add(printer)
    await db_session.flush()
    db_session.add(
        PrinterConnectionBinding(
            user_id=auth_user.id,
            physical_printer_id=printer.id,
            normalized_endpoint="moonraker|http|192.168.1.21|7125|",
            provider="moonraker",
            scheme="http",
            host="192.168.1.21",
            port=7125,
            print_host="192.168.1.21",
        )
    )
    await db_session.commit()

    await reconcile_user_printers(db_session, auth_user.id)

    await db_session.refresh(printer)
    assert printer.name == preset_name


@pytest.mark.asyncio
async def test_several_presets_one_endpoint_one_printer(db_session: AsyncSession, auth_user: User):
    await _make_profile(db_session, auth_user, "04", "Voron 0.4")
    await _make_profile(db_session, auth_user, "06", "Voron 0.6")
    await _observe(db_session, auth_user, [
        _obs(printer_settings_id="Voron 0.4", print_host="192.168.1.21", host_type="moonraker"),
        _obs(printer_settings_id="Voron 0.6", print_host="192.168.1.21", host_type="moonraker"),
    ])
    await reconcile_user_printers(db_session, auth_user.id)
    assert await _count(db_session, UserPrinterDevice) == 1
    assert await _count(db_session, UserPrinterProfileLink) == 2  # both configs on one printer


@pytest.mark.asyncio
async def test_profile_without_connection_does_not_claim_physical_printer(
    db_session: AsyncSession, auth_user: User
):
    profile = await _make_profile(db_session, auth_user, "04-linked", "Voron linked 0.4")
    printer = UserPrinterDevice(
        user_id=auth_user.id,
        name="Workshop Voron",
        supports_hh=False,
    )
    db_session.add(printer)
    await db_session.flush()
    db_session.add(
        UserPrinterProfileLink(
            user_id=auth_user.id,
            physical_printer_id=printer.id,
            printer_profile_id=profile.id,
        )
    )
    await db_session.commit()

    await _observe(
        db_session,
        auth_user,
        [
            _obs(
                connection_ref="orca-local-v1:account:workshop-voron",
                printer_settings_id=profile.setting_id,
                preset_name=profile.name,
                print_host=None,
                host_type="moonraker",
            )
        ],
    )

    assert await reconcile_user_printers(
        db_session, auth_user.id, source_instance_id="inst-1"
    ) == 0
    assert await _count(db_session, UserPrinterDevice) == 1
    assert await _count(db_session, PrinterConnectionBinding) == 0


@pytest.mark.asyncio
async def test_profile_link_does_not_guess_between_two_observed_connections(
    db_session: AsyncSession, auth_user: User
):
    profile = await _make_profile(db_session, auth_user, "04-shared", "Voron shared 0.4")
    printer = UserPrinterDevice(
        user_id=auth_user.id,
        name="Known Voron",
        supports_hh=False,
    )
    db_session.add(printer)
    await db_session.flush()
    db_session.add(
        UserPrinterProfileLink(
            user_id=auth_user.id,
            physical_printer_id=printer.id,
            printer_profile_id=profile.id,
        )
    )
    await db_session.commit()

    await _observe(
        db_session,
        auth_user,
        [
            _obs(
                connection_ref=f"orca-local-v1:account:shared-{suffix}",
                printer_settings_id=profile.setting_id,
                preset_name=profile.name,
                print_host=f"192.168.1.{host}",
                host_type="moonraker",
            )
            for suffix, host in (("a", 21), ("b", 22))
        ],
    )

    assert await reconcile_user_printers(
        db_session, auth_user.id, source_instance_id="inst-1"
    ) == 2
    assert await _count(db_session, UserPrinterDevice) == 3


@pytest.mark.asyncio
async def test_four_ips_become_four_printers(db_session: AsyncSession, auth_user: User):
    await _observe(db_session, auth_user, [
        _obs(printer_settings_id="Voron 0.4", printer_model="Voron 2.4",
             print_host=f"192.168.1.{n}", host_type="moonraker")
        for n in (21, 22, 23, 24)
    ])
    created = await reconcile_user_printers(db_session, auth_user.id)
    assert created == 4
    assert await _count(db_session, UserPrinterDevice) == 4
    assert await _count(db_session, PrinterConnectionBinding) == 4


@pytest.mark.asyncio
async def test_same_ip_different_endpoint_is_separate(db_session: AsyncSession, auth_user: User):
    await _observe(db_session, auth_user, [
        _obs(printer_settings_id="A", print_host="192.168.1.21", host_type="moonraker"),
        _obs(printer_settings_id="B", print_host="192.168.1.21", host_type="octoprint"),
    ])
    await reconcile_user_printers(db_session, auth_user.id)
    assert await _count(db_session, UserPrinterDevice) == 2  # 7125 vs 5000


@pytest.mark.asyncio
async def test_unmatched_still_creates_printer_without_link(db_session: AsyncSession, auth_user: User):
    await _observe(db_session, auth_user, [
        _obs(printer_settings_id="Unknown", print_host="192.168.1.50", host_type="moonraker"),
    ])
    await reconcile_user_printers(db_session, auth_user.id)
    assert await _count(db_session, UserPrinterDevice) == 1
    assert await _count(db_session, UserPrinterProfileLink) == 0


@pytest.mark.asyncio
async def test_visible_stock_profile_only_offers_catalog_candidate(
    db_session: AsyncSession, auth_user: User
):
    catalog_printer = Printer(
        name="Bambu Lab P2S",
        manufacturer="Bambu Lab",
        model="P2S",
        slug="bambu-lab-p2s",
        source="orcaslicer_bundle",
        active=True,
    )
    db_session.add(catalog_printer)
    await db_session.flush()
    profile = PrinterProfile(
        owner_user_id=None,
        printer_id=catalog_printer.id,
        name="Bambu Lab P2S 0.4 nozzle",
        slug="bambu-lab-p2s-04-nozzle",
        setting_id="BBL-P2S-0.4",
        source="system",
        is_official=True,
        active=True,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)

    observations = [
        _obs(
            preset_name=profile.name,
            printer_settings_id=profile.setting_id,
            printer_model=catalog_printer.name,
            is_system=True,
            is_visible=True,
            is_current=False,
        )
    ]
    await _observe(db_session, auth_user, observations)

    assert await reconcile_user_printers(db_session, auth_user.id, source_instance_id="inst-1") == 0
    assert await _count(db_session, UserPrinterDevice) == 0
    assert await _count(db_session, UserPrinterProfileLink) == 0
    from app.services.physical_printer_discovery_service import list_installed_printer_candidates
    candidates = await list_installed_printer_candidates(db_session, auth_user.id)
    assert [c["printer_id"] for c in candidates] == [catalog_printer.id]


@pytest.mark.asyncio
async def test_unselected_stock_profile_does_not_create_a_physical_printer(
    db_session: AsyncSession, auth_user: User
):
    await _observe(
        db_session,
        auth_user,
        [
            _obs(
                preset_name="Bambu Lab A1 mini 0.4 nozzle",
                printer_model="Bambu Lab A1 mini",
                is_system=True,
                is_current=False,
            )
        ],
    )

    assert await reconcile_user_printers(
        db_session, auth_user.id, source_instance_id="inst-1"
    ) == 0
    assert await _count(db_session, UserPrinterDevice) == 0


@pytest.mark.asyncio
async def test_current_stock_profile_does_not_guess_between_identical_printers(
    db_session: AsyncSession, auth_user: User
):
    catalog_printer = Printer(
        name="Bambu Lab P2S",
        manufacturer="Bambu Lab",
        model="P2S",
        slug="bambu-lab-p2s-ambiguous",
        source="orcaslicer_bundle",
        active=True,
    )
    db_session.add(catalog_printer)
    await db_session.flush()
    profile = PrinterProfile(
        owner_user_id=None,
        printer_id=catalog_printer.id,
        name="Bambu Lab P2S 0.4 nozzle",
        slug="bambu-lab-p2s-04-nozzle-ambiguous",
        setting_id="BBL-P2S-0.4",
        source="system",
        is_official=True,
        active=True,
    )
    db_session.add_all(
        [
            profile,
            UserPrinterDevice(
                user_id=auth_user.id,
                printer_id=catalog_printer.id,
                name="Workshop P2S",
                supports_hh=False,
            ),
            UserPrinterDevice(
                user_id=auth_user.id,
                printer_id=catalog_printer.id,
                name="Office P2S",
                supports_hh=False,
            ),
        ]
    )
    await db_session.commit()
    await _observe(
        db_session,
        auth_user,
        [
            _obs(
                preset_name=profile.name,
                printer_settings_id=profile.setting_id,
                printer_model=catalog_printer.name,
                is_system=True,
                is_current=True,
            )
        ],
    )

    assert await reconcile_user_printers(
        db_session, auth_user.id, source_instance_id="inst-1"
    ) == 0
    assert await _count(db_session, UserPrinterDevice) == 2
    assert await _count(db_session, UserPrinterProfileLink) == 0


@pytest.mark.asyncio
async def test_stable_connection_follows_endpoint_change_without_second_printer(
    db_session: AsyncSession, auth_user: User
):
    db_session.autoflush = False
    await _make_profile(db_session, auth_user, "04", "Voron 0.4")
    await _observe(db_session, auth_user, [
        _obs(connection_ref="stable-voron", printer_settings_id="Voron 0.4", printer_model="Voron 2.4",
             print_host="192.168.1.21", host_type="moonraker"),
    ])
    await reconcile_user_printers(db_session, auth_user.id)

    await _observe(db_session, auth_user, [
        _obs(connection_ref="stable-voron", printer_settings_id="Voron 0.4", printer_model="Voron 2.4",
             print_host="192.168.1.99", host_type="moonraker"),
    ])
    created = await reconcile_user_printers(db_session, auth_user.id)

    assert created == 0
    assert await _count(db_session, UserPrinterDevice) == 1
    bindings = list(
        (
            await db_session.execute(
                select(PrinterConnectionBinding).order_by(PrinterConnectionBinding.id)
            )
        ).scalars()
    )
    assert [display_endpoint(binding) for binding in bindings] == ["192.168.1.99:80"]


@pytest.mark.asyncio
async def test_two_machines_with_distinct_orca_presets_stay_apart(
    db_session: AsyncSession, auth_user: User
):
    await _make_profile(db_session, auth_user, "04", "Voron 0.4")
    await _make_profile(db_session, auth_user, "04-copy", "Voron 0.4 Copy")
    await _observe(db_session, auth_user, [
        _obs(printer_settings_id="Voron 0.4", print_host="192.168.1.21", host_type="moonraker"),
        _obs(printer_settings_id="Voron 0.4 Copy", print_host="192.168.1.22", host_type="moonraker"),
    ])
    await reconcile_user_printers(db_session, auth_user.id)

    assert await _count(db_session, UserPrinterDevice) == 2
    assert await _count(db_session, PrinterConnectionBinding) == 2


@pytest.mark.asyncio
async def test_connection_ref_survives_endpoint_change_without_new_printer(
    db_session: AsyncSession, auth_user: User
):
    first = _obs(
        connection_ref="orca-local-v1:account:machine-a",
        preset_name="Workshop Voron",
        print_host="192.168.1.21",
        host_type="moonraker",
    )
    await _observe(db_session, auth_user, [first])
    assert await reconcile_user_printers(
        db_session, auth_user.id, source_instance_id="inst-1"
    ) == 1

    changed = first.model_copy(update={"print_host": "192.168.1.99"})
    await _observe(db_session, auth_user, [changed])
    assert await reconcile_user_printers(
        db_session, auth_user.id, source_instance_id="inst-1"
    ) == 0

    assert await _count(db_session, UserPrinterDevice) == 1
    binding = (await db_session.execute(select(PrinterConnectionBinding))).scalar_one()
    assert display_endpoint(binding) == "192.168.1.99:80"


@pytest.mark.asyncio
async def test_stable_ref_upgrades_one_profile_linked_legacy_printer(
    db_session: AsyncSession, auth_user: User
):
    profile = await _make_profile(db_session, auth_user, "04", "Voron 0.4")
    await _observe(
        db_session,
        auth_user,
        [
            _obs(
                printer_settings_id=profile.setting_id,
                preset_name=profile.name,
                profile_fingerprint=None,
                print_host="192.168.1.21",
                host_type="moonraker",
            )
        ],
    )
    assert await reconcile_user_printers(
        db_session, auth_user.id, source_instance_id="inst-1"
    ) == 1

    await _observe(
        db_session,
        auth_user,
        [
            _obs(
                connection_ref="orca-local-v1:account:machine-a",
                printer_settings_id=profile.setting_id,
                preset_name=profile.name,
                profile_fingerprint=None,
                print_host=None,
                endpoint_token=endpoint_token(await discovery_key(db_session, auth_user.id), "192.168.1.21", "moonraker"),
                host_type="moonraker",
            )
        ],
    )
    assert await reconcile_user_printers(
        db_session, auth_user.id, source_instance_id="inst-1"
    ) == 0
    assert await _count(db_session, UserPrinterDevice) == 1
    bindings = list((await db_session.execute(select(PrinterConnectionBinding))).scalars())
    assert {binding.connection_ref for binding in bindings} == {
        None,
        "orca-local-v1:account:machine-a",
    }


@pytest.mark.asyncio
async def test_superseded_endpoint_observation_is_not_reconciled(
    db_session: AsyncSession, auth_user: User
):
    profile = await _make_profile(db_session, auth_user, "04", "Voron 0.4")
    await _observe(
        db_session,
        auth_user,
        [
            _obs(
                printer_settings_id=profile.setting_id,
                preset_name=profile.name,
                print_host="192.168.1.21",
                host_type="moonraker",
            )
        ],
    )
    await _observe(
        db_session,
        auth_user,
        [
            _obs(
                connection_ref="orca-local-v1:account:machine-a",
                printer_settings_id=profile.setting_id,
                preset_name=profile.name,
                print_host=None,
                endpoint_token="a" * 64,
                host_type="moonraker",
            )
        ],
    )

    assert await reconcile_user_printers(
        db_session, auth_user.id, source_instance_id="inst-1"
    ) == 1
    assert await _count(db_session, UserPrinterDevice) == 1
    binding = (await db_session.execute(select(PrinterConnectionBinding))).scalar_one()
    assert binding.connection_ref == "orca-local-v1:account:machine-a"
    assert display_endpoint(binding) is None


@pytest.mark.asyncio
async def test_local_only_connection_ref_creates_no_server_endpoint(
    db_session: AsyncSession, auth_user: User
):
    await _observe(
        db_session,
        auth_user,
        [
            _obs(
                connection_ref="orca-local-v1:account:machine-local",
                preset_name="Local-only printer",
                print_host=None,
                endpoint_token="b" * 64,
                host_type="moonraker",
            )
        ],
    )
    assert await reconcile_user_printers(
        db_session, auth_user.id, source_instance_id="inst-1"
    ) == 1

    binding = (await db_session.execute(select(PrinterConnectionBinding))).scalar_one()
    assert binding.connection_ref == "orca-local-v1:account:machine-local"
    assert binding.endpoint_ciphertext is None
    assert display_endpoint(binding) is None


@pytest.mark.asyncio
async def test_two_profile_refs_at_one_endpoint_share_physical_printer(
    db_session: AsyncSession, auth_user: User
):
    observations = [
        _obs(
            connection_ref=f"orca-local-v1:account:machine-{suffix}",
            preset_name=f"Workshop {suffix}",
            print_host="192.168.1.21",
            host_type="moonraker",
        )
        for suffix in ("04", "06")
    ]
    await _observe(db_session, auth_user, observations)
    assert await reconcile_user_printers(
        db_session, auth_user.id, source_instance_id="inst-1"
    ) == 1

    assert await _count(db_session, UserPrinterDevice) == 1
    bindings = list((await db_session.execute(select(PrinterConnectionBinding))).scalars())
    assert len(bindings) == 2
    assert {binding.connection_ref for binding in bindings} == {
        "orca-local-v1:account:machine-04",
        "orca-local-v1:account:machine-06",
    }


def test_normalize_endpoint():
    assert normalize_endpoint("192.168.1.21", "moonraker")["normalized"] == "moonraker|http|192.168.1.21|80|"
    assert normalize_endpoint("http://192.168.1.21:5000/x", "octoprint")["normalized"] == "octoprint|http|192.168.1.21|5000|/x"
    assert (
        normalize_endpoint("192.168.1.21", "moonraker")["normalized"]
        != normalize_endpoint("192.168.1.21", "octoprint")["normalized"]
    )
