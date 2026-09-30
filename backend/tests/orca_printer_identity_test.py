"""Tests for the canonical Orca printer_model resolver.

Printer.name preserves the exact Orca machine name (the value Orca
matches compatible_printers_condition against); Printer.model has the vendor
stripped and must not be used. Only system printers carry a canonical name.
"""

import pytest

from app.models.printer import Printer
from app.services.orca_printer_identity import (
    is_orca_system_printer,
    resolve_orca_printer_id,
    resolve_orca_printer_link,
    resolve_orca_printer_model,
    split_orca_printer_identity,
)


def test_split_preserves_orca_name_and_normalizes_bambu_vendor():
    assert split_orca_printer_identity("BambuLab", "Bambu Lab P2S") == (
        "Bambu Lab P2S",
        "Bambu Lab",
        "P2S",
    )


def test_resolve_uses_name_not_model():
    printer = Printer(name="Bambu Lab X1 Carbon", model="X1 Carbon", source="system")
    assert resolve_orca_printer_model(printer) == "Bambu Lab X1 Carbon"


def test_resolve_none_when_name_empty():
    printer = Printer(name="", model="X1 Carbon", source="system")
    assert resolve_orca_printer_model(printer) is None


def test_system_printer_flag():
    assert is_orca_system_printer(Printer(name="Voron 2.4 350", source="system")) is True
    assert is_orca_system_printer(Printer(name="My Custom Rig", source="user")) is False


@pytest.mark.asyncio
async def test_resolver_never_assigns_ambiguous_model_id(db_session):
    db_session.add_all(
        [
            Printer(
                name="Vendor Model A",
                manufacturer="Vendor",
                model="Model A",
                slug="resolver-vendor-a",
                vendor="Vendor",
                model_id="shared-resolver-id",
                source="system",
            ),
            Printer(
                name="Vendor Model B",
                manufacturer="Vendor",
                model="Model B",
                slug="resolver-vendor-b",
                vendor="Vendor",
                model_id="shared-resolver-id",
                source="system",
            ),
        ]
    )
    await db_session.flush()

    assert await resolve_orca_printer_id(
        db=db_session,
        printer_id=None,
        printer_slug=None,
        profile_metadata={"model_id": "shared-resolver-id"},
        profile_settings={},
        profile_vendor="Vendor",
    ) is None


@pytest.mark.asyncio
async def test_display_substrings_never_assign_a_catalog_model(db_session):
    db_session.add(Printer(
        name="Creality Hi", manufacturer="Creality", model="Hi",
        slug="creality-hi", source="system", vendor="Creality",
    ))
    await db_session.flush()
    assert await resolve_orca_printer_id(
        db=db_session, profile_metadata={"name": "Creality The Machine Spirit"},
        profile_vendor="Creality",
    ) is None


@pytest.mark.asyncio
async def test_resolution_prefers_known_link_and_follows_owned_parent_chain(db_session, auth_user):
    from app.models.printer_profile import PrinterProfile

    model = Printer(name="Bambu Lab P2S", manufacturer="Bambu Lab", model="P2S",
                    vendor="BambuLab", source="system", slug="canonical-p2s")
    wrong = Printer(name="Other model", manufacturer="Other", model="Model",
                    source="system", slug="other-model")
    db_session.add_all([model, wrong])
    await db_session.flush()
    stock = PrinterProfile(name="Bambu Lab P2S 0.4 nozzle", slug="stock-p2s",
                           source="system", vendor="BambuLab", printer_id=model.id)
    personal = PrinterProfile(name="Workshop P2S", slug="workshop-p2s",
                              owner_user_id=auth_user.id,
                              orcaslicer_settings={"inherits": stock.name})
    db_session.add_all([stock, personal])
    await db_session.flush()
    assert await resolve_orca_printer_id(
        db=db_session, owner_user_id=auth_user.id,
        profile_settings={"inherits": personal.name}, profile_vendor="BambuLab",
    ) == model.id
    assert await resolve_orca_printer_id(
        db=db_session, known_printer_id=model.id,
        profile_settings={"printer_model": wrong.name},
    ) == model.id
    assert await resolve_orca_printer_id(
        db=db_session, printer_id=wrong.id, known_printer_id=model.id,
    ) == wrong.id


@pytest.mark.asyncio
async def test_resolution_never_uses_foreign_profile_or_ambiguous_parents(db_session, auth_user):
    from app.models.printer_profile import PrinterProfile
    from app.models.user import User

    foreign = User(email="foreign-printer@example.com", username="foreign-printer",
                   password_hash="unused")
    model = Printer(name="Bambu Lab P2S", manufacturer="Bambu Lab", model="P2S",
                    source="system", vendor="BambuLab", slug="scoped-p2s")
    db_session.add_all([foreign, model])
    await db_session.flush()
    db_session.add(PrinterProfile(name="Private machine", slug="foreign-machine",
                                 owner_user_id=foreign.id, printer_id=model.id))
    await db_session.flush()
    assert (await resolve_orca_printer_link(
        db=db_session, owner_user_id=auth_user.id, identifier="Private machine",
    ))[0] is None
    assert await resolve_orca_printer_id(
        db=db_session, owner_user_id=auth_user.id,
        profile_settings={"inherits": "Private machine"},
    ) is None
    db_session.add_all([
        PrinterProfile(name="Duplicate parent", slug=f"duplicate-parent-{index}",
                       owner_user_id=auth_user.id, printer_id=model.id if index else None)
        for index in range(2)
    ])
    await db_session.flush()
    assert await resolve_orca_printer_id(
        db=db_session, owner_user_id=auth_user.id,
        profile_settings={"inherits": "Duplicate parent", "printer_model": model.name},
    ) is None


@pytest.mark.asyncio
async def test_external_identity_requires_vendor_and_canonical_signal_wins(db_session):
    model = Printer(name="Bambu Lab P2S", manufacturer="Bambu Lab", model="P2S",
                    source="system", vendor="BambuLab", model_id="shared", slug="external-p2s")
    other = Printer(name="Vendor Different", manufacturer="Vendor", model="Different",
                    source="system", vendor="Vendor", model_id="shared", slug="external-other")
    db_session.add_all([model, other])
    await db_session.flush()
    assert await resolve_orca_printer_id(
        db=db_session, profile_settings={"model_id": "shared"},
    ) is None
    assert await resolve_orca_printer_id(
        db=db_session, profile_vendor="BambuLab", profile_settings={"model_id": "shared"},
    ) == model.id
    assert await resolve_orca_printer_id(
        db=db_session, profile_settings={"printer_model": model.name, "model_id": "shared"},
        profile_metadata={"name": other.name},
    ) == model.id
    assert await resolve_orca_printer_id(
        db=db_session, profile_vendor="Display vendor",
        profile_settings={"printer_model": model.name},
    ) == model.id


def test_source_name_preserves_whitespace_and_incomplete_vendor_prefix():
    assert split_orca_printer_identity("BambuLab", "Bambu") == ("Bambu", "BambuLab", "Bambu")
    assert split_orca_printer_identity("BambuLab", "Bambu  Lab P2S")[0] == "Bambu  Lab P2S"


@pytest.mark.asyncio
async def test_imported_custom_machine_keeps_canonical_fk_and_response_identity(db_session, auth_user):
    from sqlalchemy import func, select

    from app.api.v1.endpoints.orca_sync import _upsert_printer_profile
    from app.models.printer_profile import PrinterProfile
    from app.schemas.orca_sync import OrcaPrinterProfilePayload
    from app.schemas.printer_profile import PrinterProfileResponse

    model = Printer(name="Bambu Lab P2S", manufacturer="Bambu Lab", model="P2S",
                    vendor="BambuLab", source="system", slug="import-p2s")
    stock = PrinterProfile(name="Bambu Lab P2S 0.4 nozzle", slug="import-p2s-stock",
                           printer=model, source="system", vendor="BambuLab")
    db_session.add(stock)
    await db_session.flush()
    payload = OrcaPrinterProfilePayload(
        name="Workshop customized machine", external_id="workshop-identity",
        orcaslicer_settings={"inherits": stock.name},
    )
    first = await _upsert_printer_profile(payload=payload, current_user=auth_user, db=db_session)
    assert first.status == "created"
    custom = await db_session.get(PrinterProfile, first.fhub_id)
    assert custom.printer_id == model.id
    # Later observations may omit model/inheritance. Durable profile identity
    # must retain the resolved model, rather than repeating a name guess.
    payload.orcaslicer_settings = {}
    second = await _upsert_printer_profile(payload=payload, current_user=auth_user, db=db_session)
    assert second.fhub_id == first.fhub_id
    assert custom.printer_id == model.id
    assert await db_session.scalar(select(func.count()).select_from(Printer)) == 1
    await db_session.refresh(custom, ["printer", "created_at", "updated_at"])
    response = PrinterProfileResponse.model_validate(custom).model_dump()
    assert response["orca_printer_model"] == "Bambu Lab P2S"
    assert response["printer_model"] == "P2S"


@pytest.mark.asyncio
async def test_new_durable_profile_does_not_inherit_same_named_profiles_model(db_session, auth_user):
    from app.api.v1.endpoints.orca_sync import _upsert_printer_profile
    from app.models.printer_profile import PrinterProfile
    from app.schemas.orca_sync import OrcaPrinterProfilePayload

    old_model = Printer(name="Voron 2.4 350", manufacturer="Voron", model="2.4 350",
                        source="system", slug="same-name-voron")
    new_model = Printer(name="Bambu Lab P2S", manufacturer="Bambu Lab", model="P2S",
                        source="system", slug="same-name-p2s")
    old_profile = PrinterProfile(name="My machine", slug="old-durable-machine",
                                 owner_user_id=auth_user.id, printer=old_model)
    db_session.add_all([old_profile, new_model])
    await db_session.flush()
    local_id = "9c734260-ceb3-4c73-b204-bf826b781e61"
    result = await _upsert_printer_profile(
        payload=OrcaPrinterProfilePayload(
            name=old_profile.name, local_profile_id=local_id,
            external_id=f"orca-local-v1:{local_id}",
            orcaslicer_settings={"printer_model": new_model.name},
        ),
        current_user=auth_user, db=db_session,
    )
    assert result.status == "created"
    assert result.fhub_id != old_profile.id
    created = await db_session.get(PrinterProfile, result.fhub_id)
    assert created.printer_id == new_model.id
    assert old_profile.printer_id == old_model.id


@pytest.mark.asyncio
@pytest.mark.parametrize("machine_name", ["123", "other-model-slug", "other-profile-slug"])
async def test_process_machine_names_are_not_typed_ids_or_slugs(db_session, auth_user, machine_name):
    from app.models.printer_profile import PrinterProfile

    wrong = Printer(id=123, name="Unrelated model", manufacturer="Other", model="Other",
                    source="system", slug="other-model-slug")
    right = Printer(name="Bambu Lab P2S", manufacturer="Bambu Lab", model="P2S",
                    source="system", slug="actual-process-model")
    named = PrinterProfile(name=machine_name, slug="selected-process-machine",
                           owner_user_id=auth_user.id, printer=right)
    unrelated = PrinterProfile(name="Unrelated configuration", slug="other-profile-slug",
                               owner_user_id=auth_user.id, printer=wrong)
    db_session.add_all([wrong, right, named, unrelated])
    await db_session.flush()
    assert await resolve_orca_printer_link(
        db=db_session, owner_user_id=auth_user.id, identifier=machine_name,
    ) == (right.id, right.slug)
