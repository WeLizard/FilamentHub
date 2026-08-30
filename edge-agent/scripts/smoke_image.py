"""Exercise the published image entrypoint with Supervisor-style private storage.

Uses only synthetic, disabled connections and no network. Containers and their
volume are retained for diagnosis; no user service or printer is contacted.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import uuid


def docker(*args: str, expected: int = 0) -> str:
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, encoding="utf-8", timeout=240
    )
    if result.returncode != expected:
        raise RuntimeError(f"Docker command failed ({result.returncode}): {result.stderr}")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    args = parser.parse_args()
    prefix = f"fh-edge-smoke-{uuid.uuid4().hex[:10]}"
    volume = f"{prefix}-data"
    docker("volume", "create", "--label", "filamenthub.purpose=edge-package-smoke", volume)
    common = ["--network", "none", "--volume", f"{volume}:/data"]
    runtime = f"{prefix}-runtime"
    print(f"Retaining smoke containers {prefix}-* and volume {volume}", flush=True)

    def helper(name: str, code: str) -> str:
        return docker(
            "run",
            "--name",
            f"{prefix}-{name}",
            *common,
            "--user",
            "0",
            "--entrypoint",
            "python",
            args.image,
            "-c",
            code,
        )

    helper(
        "options",
        """
import json, os
from pathlib import Path
data = Path('/data')
os.chown(data, 0, 0)
data.chmod(0o755)
options = {'filamenthub_url': 'https://filamenthub.invalid', 'connections': [
    {'id': 'mmu', 'enabled': False, 'material_provider': 'happy_hare',
     'moonraker_url': 'http://mmu.invalid', 'moonraker_api_key': 'private-fixture'},
    {'id': 'direct', 'enabled': False, 'material_provider': 'legacy',
     'moonraker_url': 'http://direct.invalid'}]}
path = data / 'options.json'
path.write_text(json.dumps(options))
os.chown(path, 0, 0)
path.chmod(0o600)
""",
    )
    docker(
        "run",
        "--detach",
        "--name",
        runtime,
        *common,
        "--cap-drop=ALL",
        "--cap-add=CHOWN",
        "--cap-add=FOWNER",
        "--cap-add=DAC_OVERRIDE",
        "--cap-add=SETUID",
        "--cap-add=SETGID",
        "--security-opt=no-new-privileges",
        args.image,
    )
    try:
        before = None
        for _ in range(40):
            status = subprocess.run(
                [
                    "docker",
                    "exec",
                    runtime,
                    "python",
                    "-m",
                    "filamenthub_edge.container",
                    "--status",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
            )
            if status.returncode == 0:
                before = json.loads(status.stdout)
                if before["initialized"]:
                    break
            time.sleep(0.25)
        assert before and before["initialized"], "Runtime did not initialize"
        process = docker(
            "exec",
            runtime,
            "python",
            "-c",
            """
from pathlib import Path
fields = dict(line.split(':', 1) for line in Path('/proc/1/status').read_text().splitlines())
assert all(int(uid) != 0 for uid in fields['Uid'].split()), 'Runtime is root'
assert not fields['Groups'].strip(), 'Runtime retained supplementary groups'
assert int(fields['CapEff'].strip(), 16) == 0, 'Runtime retained capabilities'
assert fields['NoNewPrivs'].strip() == '1'
path = Path('/data/options.json')
assert path.stat().st_uid == 0 and path.stat().st_mode & 0o777 == 0o600
print('Runtime is unprivileged; Supervisor options remain private and unchanged')
""",
        )
        print(process, flush=True)
    finally:
        docker("stop", "--time", "210", runtime)
    assert docker("inspect", "--format", "{{.State.ExitCode}}", runtime) == "0"

    queued = json.loads(
        helper(
            "queued",
            """
import hashlib, json, os
from dataclasses import asdict
from pathlib import Path
from filamenthub_edge.state import EdgeState
data = Path('/data')
node = json.loads((data / 'node.json').read_text())
(data / 'connections').mkdir(mode=0o700, exist_ok=True)
result = {}
for index, key in enumerate(('mmu', 'direct'), 1):
    state = EdgeState(node_instance_id=node['node_instance_id'],
        bridge_token='fhpb_private_fixture', physical_printer_id=index,
        material_system_id=index, last_snapshot_sequence=2,
        pending_observation={'sequence': 2}, last_usage_batch_sequence=1,
        usage_outbox=[{'sequence': 1, 'events': [{'event_id': key + '-event'}]}])
    path = data / 'connections' / (key + '.json')
    path.write_text(json.dumps(asdict(state)))
    path.chmod(0o600)
    result[key] = {'source': state.instance_id,
                   'hash': hashlib.sha256(path.read_bytes()).hexdigest()}
# Supervisor recreates options on save; restored files can also be owned by root.
options = data / 'options.json'
content = json.loads(options.read_text())
content['sync_interval'] = 45
options.write_text(json.dumps(content))
for path in [data, data / 'node.json', data / 'connections', *data.glob('connections/*.json')]:
    os.chown(path, 0, 0)
print(json.dumps(result))
""",
        )
    )
    report = json.loads(
        docker("run", "--name", f"{prefix}-replacement", *common, args.image, "--once")
    )
    assert report["node_instance_id"] == before["node_instance_id"]
    for connection in report["connections"]:
        assert "error" not in connection
        assert connection["source_instance_id"] == queued[connection["id"]]["source"]
        assert connection["usage_outbox_batches"] == 1 and connection["pending_observation"]
    assert "private_fixture" not in json.dumps(report)
    after = json.loads(
        helper(
            "verify",
            """
import hashlib, json
from pathlib import Path
print(json.dumps({p.stem: hashlib.sha256(p.read_bytes()).hexdigest()
    for p in Path('/data/connections').glob('*.json')}))
""",
        )
    )
    assert after == {key: value["hash"] for key, value in queued.items()}
    print("PASS: private options, privilege drop, SIGTERM, replacement, identity and queued bytes")


if __name__ == "__main__":
    main()
