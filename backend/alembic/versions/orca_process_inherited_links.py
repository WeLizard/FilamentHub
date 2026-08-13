"""backfill effective Orca process-to-machine inheritance

Revision ID: orca_process_inherited_links
Revises: orca_printer_identity_v2
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "orca_process_inherited_links"
down_revision: str | None = "orca_printer_identity_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inherits(settings: object) -> str:
    if not isinstance(settings, dict):
        return ""
    return str(settings.get("inherits") or "").strip()


def upgrade() -> None:
    bind = op.get_bind()
    print_profiles = sa.table(
        "print_profiles",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("owner_user_id", sa.Integer()),
        sa.column("is_official", sa.Boolean()),
        sa.column("active", sa.Boolean()),
        sa.column("compatible_printers", sa.JSON()),
        sa.column("orcaslicer_settings", sa.JSON()),
        sa.column("configuration_links_resolved", sa.Boolean()),
    )
    printer_profiles = sa.table(
        "printer_profiles",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("owner_user_id", sa.Integer()),
        sa.column("is_official", sa.Boolean()),
        sa.column("active", sa.Boolean()),
        sa.column("orcaslicer_settings", sa.JSON()),
    )
    links = sa.table(
        "print_profile_configuration_links",
        sa.column("print_profile_id", sa.Integer()),
        sa.column("printer_profile_id", sa.Integer()),
        sa.column("relation_type", sa.String()),
    )

    processes = list(bind.execute(sa.select(print_profiles)))
    machines = list(bind.execute(sa.select(printer_profiles)))
    existing_rows = list(bind.execute(sa.select(links)))
    existing = {
        (row.print_profile_id, row.printer_profile_id): row.relation_type
        for row in existing_rows
    }
    direct: dict[int, set[int]] = {}
    for row in existing_rows:
        if row.relation_type == "explicit":
            direct.setdefault(row.print_profile_id, set()).add(row.printer_profile_id)

    processes_by_name: dict[str, list[sa.Row]] = {}
    for process in processes:
        if process.active:
            processes_by_name.setdefault(process.name, []).append(process)

    def parent_for(process: sa.Row) -> sa.Row | None:
        name = _inherits(process.orcaslicer_settings)
        if not name:
            return None
        candidates = processes_by_name.get(name, [])
        if process.owner_user_id is None:
            candidates = [
                item
                for item in candidates
                if item.owner_user_id is None and item.is_official
            ]
        else:
            owned = [
                item for item in candidates if item.owner_user_id == process.owner_user_id
            ]
            candidates = owned or [
                item
                for item in candidates
                if item.owner_user_id is None and item.is_official
            ]
        return candidates[0] if len(candidates) == 1 else None

    def effective_process_ids(
        process: sa.Row,
        visited: set[int],
    ) -> tuple[set[int], bool]:
        explicit = direct.get(process.id, set())
        if explicit or process.compatible_printers is not None:
            return explicit, bool(process.configuration_links_resolved)
        parent_name = _inherits(process.orcaslicer_settings)
        if not parent_name:
            return set(), True
        parent = parent_for(process)
        if parent is None or parent.id in visited:
            return set(), False
        return effective_process_ids(parent, {*visited, parent.id})

    machine_by_name: dict[str, list[sa.Row]] = {}
    machine_by_id = {machine.id: machine for machine in machines if machine.active}
    for machine in machine_by_id.values():
        machine_by_name.setdefault(machine.name, []).append(machine)

    def owned_machine_descendants(owner_id: int, base_ids: set[int]) -> set[int]:
        targets = {machine_by_id[item].name for item in base_ids if item in machine_by_id}
        result: set[int] = set()
        for machine in machine_by_id.values():
            if machine.owner_user_id != owner_id or machine.id in base_ids:
                continue
            current = machine
            visited = {current.id}
            while True:
                parent_name = _inherits(current.orcaslicer_settings)
                if not parent_name:
                    break
                if parent_name in targets:
                    result.add(machine.id)
                    break
                candidates = machine_by_name.get(parent_name, [])
                owned = [item for item in candidates if item.owner_user_id == owner_id]
                candidates = owned or [
                    item
                    for item in candidates
                    if item.owner_user_id is None and item.is_official
                ]
                if len(candidates) != 1 or candidates[0].id in visited:
                    break
                current = candidates[0]
                visited.add(current.id)
        return result

    for process in processes:
        if not process.active:
            continue
        effective_ids, resolved = effective_process_ids(process, {process.id})
        explicit_ids = direct.get(process.id, set())
        for machine_id in sorted(effective_ids - explicit_ids):
            if (process.id, machine_id) not in existing:
                bind.execute(
                    links.insert().values(
                        print_profile_id=process.id,
                        printer_profile_id=machine_id,
                        relation_type="inherited_process",
                    )
                )
                existing[(process.id, machine_id)] = "inherited_process"
        if process.owner_user_id is not None and effective_ids:
            for machine_id in sorted(
                owned_machine_descendants(process.owner_user_id, effective_ids)
            ):
                if (process.id, machine_id) not in existing:
                    bind.execute(
                        links.insert().values(
                            print_profile_id=process.id,
                            printer_profile_id=machine_id,
                            relation_type="inherited_machine",
                        )
                    )
                    existing[(process.id, machine_id)] = "inherited_machine"
        if not resolved and process.configuration_links_resolved:
            bind.execute(
                print_profiles.update()
                .where(print_profiles.c.id == process.id)
                .values(configuration_links_resolved=False)
            )


def downgrade() -> None:
    links = sa.table(
        "print_profile_configuration_links",
        sa.column("relation_type", sa.String()),
    )
    op.get_bind().execute(
        links.delete().where(
            links.c.relation_type.in_(["inherited_process", "inherited_machine"])
        )
    )
