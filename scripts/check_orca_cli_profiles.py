#!/usr/bin/env python3
"""Check that an installed OrcaSlicer accepts FilamentHub's exported presets.

FilamentHub's own tests prove that values survive import, storage and export.
They cannot prove that OrcaSlicer reads the result the same way: a value can be
dropped as unknown, renamed by Orca's legacy handling or parsed into another
shape. This script asks the real program.

It flattens Orca's bundled system profiles (OrcaSlicer resolves `inherits` only
inside its GUI), lays the exported presets over them, slices a 20 mm cube with
the CLI in a throwaway data directory and compares every exported setting with
the full configuration Orca saved into the 3MF project.

The CLI never runs plugins and never touches the user's OrcaSlicer profile,
because `--datadir` points at a temporary folder. Windows only for now; the
installed OrcaSlicer version is what is checked.

Exports come from a running FilamentHub, for example the local dev stack:

    curl -c jar -H 'Content-Type: application/json' \
        -d '{"email": "...", "password": "..."}' http://localhost:8001/api/v1/auth/login
    curl -b jar -o machine.json http://localhost:8001/api/v1/printer-profiles/<id>/export/orcaslicer.json
    curl -b jar -o process.json http://localhost:8001/api/v1/print-profiles/<id>/export/orcaslicer.json

    python scripts/check_orca_cli_profiles.py --machine machine.json --process process.json

Settings may also be given inline, which is the quick way to try field samples:

    python scripts/check_orca_cli_profiles.py --set process:adaptive_infill_mode=lobes \
        --set machine:is_imex=1

Exit status: 0 when every setting was kept or renamed by Orca's legacy handling
to a key that holds the same value, 1 when a value changed or disappeared,
2 when Orca could not slice.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

DEFAULT_ORCA = Path(r'C:\Program Files\OrcaSlicer\orca-slicer.exe')
DEFAULT_BASES = {
    'machine': 'Voron 2.4 350 0.4 nozzle',
    'process': '0.20mm Standard @Voron',
    'filament': 'Generic PLA @System',
}
KINDS = ('machine', 'process', 'filament')
# Preset identity and FilamentHub bookkeeping: Orca rewrites or drops these by design.
IDENTITY_KEYS = {
    'name', 'inherits', 'from', 'instantiation', 'version', 'type', 'setting_id',
    'printer_settings_id', 'print_settings_id', 'filament_settings_id',
    'compatible_printers', 'compatible_printers_condition', 'compatible_prints',
    'compatible_prints_condition', 'bundle_id', 'filament_id', 'base_id',
}
IDENTITY_PREFIXES = ('fhub_',)


def find_profile(profiles: Path, kind: str, name: str) -> Path:
    hits = sorted(profiles.glob(f'*/{kind}/**/{name}.json'))
    if not hits:
        raise SystemExit(f'OrcaSlicer has no {kind} profile named {name!r} in {profiles}')
    return hits[0]


def flatten(profiles: Path, kind: str, name: str) -> dict:
    data = json.loads(find_profile(profiles, kind, name).read_text(encoding='utf-8'))
    parent = data.pop('inherits', '')
    merged = flatten(profiles, kind, parent) if parent else {}
    merged.update(data)
    return merged


def write_cube(path: Path, size: float = 20.0) -> None:
    corners = [(x, y, z) for x in (0, size) for y in (0, size) for z in (0, size)]
    faces = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1),
             (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    with path.open('wb') as stl:
        stl.write(b'\0' * 80 + struct.pack('<I', len(faces)))
        for face in faces:
            stl.write(struct.pack('<3f', 0, 0, 0))
            for index in face:
                stl.write(struct.pack('<3f', *corners[index]))
            stl.write(b'\0\0')


def is_identity(key: str) -> bool:
    return key in IDENTITY_KEYS or key.startswith(IDENTITY_PREFIXES)


def same_value(sent: object, saved: object) -> bool:
    """Orca keeps a vector option as a list; FilamentHub may carry its serialized string."""
    if sent == saved or str(sent) == str(saved):
        return True
    if isinstance(saved, list) and isinstance(sent, str):
        if not saved:
            return sent == ''
        if saved == ['']:
            return sent == '""'
        return sent in (';'.join(saved), ','.join(saved))
    if isinstance(sent, list) and isinstance(saved, list):
        return [str(item) for item in sent] == [str(item) for item in saved]
    return False


def parse_inline(items: list[str]) -> dict[str, dict[str, str]]:
    inline: dict[str, dict[str, str]] = {kind: {} for kind in KINDS}
    for item in items:
        scope, _, assignment = item.partition(':')
        key, sep, value = assignment.partition('=')
        if scope not in KINDS or not key or not sep:
            raise SystemExit(f'--set expects kind:key=value with kind in {KINDS}, got {item!r}')
        inline[scope][key] = value
    return inline


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or '').split('\n\n')[0])
    for kind in KINDS:
        parser.add_argument(f'--{kind}', type=Path, help=f'exported {kind} preset JSON')
        parser.add_argument(f'--base-{kind}', default=DEFAULT_BASES[kind],
                            help=f'bundled Orca {kind} profile to lay it over (default: %(default)s)')
    parser.add_argument('--set', action='append', default=[], metavar='KIND:KEY=VALUE',
                        help='extra setting, applied after the exported file')
    parser.add_argument('--orca', type=Path, default=DEFAULT_ORCA, help='orca-slicer.exe (default: %(default)s)')
    parser.add_argument('--keep', action='store_true', help='keep the work folder for inspection')
    args = parser.parse_args()

    if not args.orca.exists():
        raise SystemExit(f'OrcaSlicer not found: {args.orca}')
    profiles = args.orca.parent / 'resources' / 'profiles'
    inline = parse_inline(args.set)

    workdir = Path(tempfile.mkdtemp(prefix='orca-cli-check-'))
    sent: dict[str, dict] = {}
    for kind in KINDS:
        exported = json.loads(getattr(args, kind).read_text(encoding='utf-8')) if getattr(args, kind) else {}
        exported.update(inline[kind])
        sent[kind] = {key: value for key, value in exported.items() if not is_identity(key)}
    if not any(sent.values()):
        raise SystemExit('nothing to check: pass --machine/--process/--filament or --set')
    bases = {kind: flatten(profiles, kind, getattr(args, f'base_{kind}')) for kind in KINDS}
    cube = workdir / 'cube.stl'
    write_cube(cube)

    def slice_project(label: str, overlay: dict[str, dict]) -> dict | None:
        """Slice with the bundled bases plus `overlay` and return the config saved in the 3MF."""
        files = {}
        for kind in KINDS:
            # Let the presets load together whatever their compatibility conditions say.
            preset = {**bases[kind], **overlay[kind], 'compatible_printers': [], 'compatible_printers_condition': ''}
            files[kind] = workdir / f'{label}_{kind}.json'
            files[kind].write_text(json.dumps(preset, ensure_ascii=False, indent=2), encoding='utf-8')
        output = workdir / f'out_{label}'
        command = [
            str(args.orca), '--datadir', str(workdir / 'data'),
            '--load-settings', f'{files["machine"]};{files["process"]}',
            '--load-filaments', str(files['filament']),
            '--arrange', '1', '--slice', '0', '--export-3mf', f'{label}.3mf',
            '--outputdir', str(output), str(cube),
        ]
        env = {**os.environ, 'TEMP': str(workdir), 'TMP': str(workdir)}
        run = subprocess.run(command, capture_output=True, text=True, errors='replace', env=env, timeout=600)
        project = output / f'{label}.3mf'
        if run.returncode != 0 or not project.exists():
            print(f'OrcaSlicer failed on the {label} run (exit {run.returncode}); work folder kept: {workdir}')
            print((run.stdout + run.stderr)[-3000:])
            return None
        with zipfile.ZipFile(project) as archive:
            return json.loads(archive.read('Metadata/project_settings.config'))

    baseline = slice_project('baseline', {kind: {} for kind in KINDS})
    saved = slice_project('check', sent) if baseline is not None else None
    if baseline is None or saved is None:
        return 2

    failures = 0
    for kind in KINDS:
        for key, value in sorted(sent[kind].items()):
            if key in saved and same_value(value, saved[key]):
                print(f'kept     {kind}:{key} = {value!r}')
                continue
            # A legacy name Orca renamed on load: a key it did not send now holds the sent value.
            renamed = sorted(
                name for name, other in saved.items()
                if name not in sent[kind] and same_value(value, other)
                and not same_value(value, baseline.get(name))
            ) if key not in saved else []
            if renamed:
                print(f'renamed  {kind}:{key} = {value!r} -> {", ".join(renamed)}')
            else:
                failures += 1
                print(f'CHANGED  {kind}:{key}: sent {value!r}, Orca saved {saved.get(key, "<missing>")!r}')

    print(f'\n{failures} changed of {sum(len(v) for v in sent.values())} settings; checked with {args.orca}')
    if args.keep:
        print(f'work folder: {workdir}')
    else:
        shutil.rmtree(workdir, ignore_errors=True)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
