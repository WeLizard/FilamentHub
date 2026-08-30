# FilamentHub Edge

The Edge runtime keeps FilamentHub connected to local printer hardware without
exposing LAN credentials to the cloud. The first provider reads Moonraker and
Happy Hare, synchronizes observed printer/slot state to FilamentHub, and keeps a
durable local copy of desired spool and preset assignments.

It never treats provider observations as user-approved assignments. Happy Hare
and Moonraker's native Spoolman component handle spool inventory, assignments and
usage. Edge supplies the full gate topology and live observations; it does not
run G-code or replace the native integration. When native Spoolman is configured
or its status is unknown, Edge does not submit an additional consumption stream.
Only with native Spoolman confirmed absent and Happy Hare support off can Edge
send replay-protected usage for an unambiguous active desired spool.

## Installation

Edge is intended to bridge a home, office, or printer farm to FilamentHub: one
node serving multiple printers through supported adapters. Device resources and
adapter capabilities determine capacity, not a one-printer-per-node product rule.

One installation supervises independent entries in `connections`. Each entry
has its own printer binding, revocable cloud credential, observations, and durable
usage queue; a disconnected printer does not pause the others. This runtime
accepts up to 32 configured connections to bound local resource use. Actual
capacity depends on the host and adapter. The current adapter supports Moonraker
with Happy Hare (`happy_hare`) or direct Klipper feed (`legacy`); other printer
protocols require their own adapters.

OrcaSlicer is optional. Install on the printer's Linux computer or another
always-on computer on the same LAN. No inbound internet port, printer API key in
FilamentHub, or separate hardware is required. Do not install into Klipper's or
Moonraker's Python environment.

1. In FilamentHub, add each physical printer and its material system.
   Create physical spools in **My Filaments**, not just catalogue entries.
2. For Happy Hare, open the printer's integration settings and copy its generated Spoolman URL
   into Moonraker's existing `[spoolman]` section. Do not create duplicate sections:

   ```ini
   [spoolman]
   server: https://filamenthub.ru/api/v1/spool_compat/<this-printer-device-key>

   [mmu_server]
   ```

   Reload Moonraker while the printer is idle. Its `[mmu_server]` component must
   be installed and loaded. The URL key identifies this exact physical printer;
   it is not the Moonraker API key or the Edge pairing code.
3. Review the existing gate map before choosing a mode. Current Happy Hare v4
   uses `spoolman_support` in `mmu.cfg` (older versions use `mmu_parameters.cfg`).
   `pull` makes remote assignments authoritative and can replace the local map;
   `push` sends local assignments to the inventory; `readonly` only reads spool
   properties. Follow the [official Happy Hare guide](https://moggieuk.github.io/Happy-Hare-Doc/Feature-Spoolman/).
4. Open **Profile → My Filaments** and expand the printer's material-system card.
   Open **Connection with and without Orca** for Happy Hare, or **Connect through
   Edge (optional)** for direct feed. Create a separate one-time pairing code for
   each system, then add its entry to the same installation below.

### Home Assistant OS

Use **Settings → Apps → Install app → menu → Repositories** and add
`https://github.com/WeLizard/FilamentHub`. Then open **FilamentHub Edge** in the
store. This uses the same runtime as Docker, not a HACS integration.

[Open the repository in Home Assistant](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FWeLizard%2FFilamentHub)

The repository files and matching public image must be published first. This
checkout alone does not make the app installable; do not substitute an unrelated
image if HA cannot download the stated version. See the
[HA installation and update guide](home-assistant/filamenthub_edge/DOCS.md) and
[release checklist](#release-checklist).

Install once, add printers in the app's **Configuration** tab, save and start.
Use the built-in YAML editor if the HA form cannot edit the `connections` list.
Start-on-boot, logs, backups and updates are managed by HA; no SSH, terminal,
Supervisor token, port forwarding or disabled protection mode is required.

### Linux without Docker

Requires Python 3.11 or newer with `venv`. Use a dedicated virtual environment,
leaving the printer software and its dependencies unchanged. From a checkout
containing the matching FilamentHub release:

```sh
python3 -m venv "$HOME/.local/share/filamenthub-edge/venv"
"$HOME/.local/share/filamenthub-edge/venv/bin/pip" install ./edge-agent
install -d -m 700 "$HOME/.config/filamenthub-edge"
```

Create `~/.config/filamenthub-edge/options.json` with permissions `600`:

```json
{
  "filamenthub_url": "https://filamenthub.ru",
  "connections": [
    {
      "id": "workshop-mmu",
      "name": "Workshop MMU",
      "adapter": "moonraker",
      "pairing_code": "FH-XXXXX-XXXXX",
      "material_provider": "happy_hare",
      "moonraker_url": "http://192.168.1.20:7125",
      "moonraker_api_key": ""
    },
    {
      "id": "office-printer",
      "name": "Office printer",
      "adapter": "moonraker",
      "pairing_code": "FH-YYYYY-YYYYY",
      "material_provider": "legacy",
      "moonraker_url": "http://192.168.1.21:7125",
      "moonraker_api_key": ""
    }
  ]
}
```

Use the printer's LAN address when running on another computer. If Moonraker
requires an API key, enter it only in this local file; do not disable its
authentication or expose it to the internet. Test one exchange:

```sh
FH_EDGE_OPTIONS_FILE="$HOME/.config/filamenthub-edge/options.json" \
FH_EDGE_STATE_DIRECTORY="$HOME/.local/share/filamenthub-edge/state" \
  "$HOME/.local/share/filamenthub-edge/venv/bin/filamenthub-edge" --once
```

After a successful exchange, remove only the `pairing_code` from that connection,
preserving its `id` and the state directory. For continuous operation on a systemd Linux host:

```sh
install -d "$HOME/.config/systemd/user"
install -m 644 edge-agent/filamenthub-edge.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now filamenthub-edge.service
journalctl --user -u filamenthub-edge.service -n 30
```

The user service normally runs while that user's session exists. For unattended
startup after reboot, the host administrator must enable user lingering
(`loginctl enable-linger <service-user>`). Verify startup after a reboot. Do not
run multiple copies using the same state directory: Edge refuses a second writer.

### Docker

Build the image from this checkout; the command does not assume a published
registry image exists:

```sh
docker build -t filamenthub-edge:local ./edge-agent
```

Put the options above into a local protected `options.json` (mode `600`). The
container bootstrap reads the file, prepares only its dedicated `/data` mount,
then drops root and supplementary groups before running Edge. It does not change
the options file's contents, owner or permissions. Mount it read-only and keep
durable state in a named volume:

```text
docker run --restart unless-stopped --stop-timeout 210 \
  --name filamenthub-edge \
  -v /absolute/path/options.json:/data/options.json:ro \
  -v filamenthub-edge-data:/data \
  filamenthub-edge:local
```

Use an explicit reachable printer LAN address in the options, not container-local
`127.0.0.1`. This adapter makes outbound connections; it does not need host
networking. LAN firewalls must permit the container's routed connection to the
configured Moonraker endpoint. For an explicitly non-root Docker deployment,
pre-provision the state volume and readable options for the image's `filamenthub`
user and pass `--user filamenthub`; automatic volume preparation is then skipped.

The pairing code is needed only for the first successful connection. Node identity
is stored in `/data/node.json`. Each connection's revocable bridge token, cached
desired state, pending observation, usage tracker, and bounded durable usage outbox
are stored separately in `/data/connections/<id>.json`.
Clear the one-time pairing code from the container or Home Assistant options
after pairing. Supplying a new code rotates the credential for the same printer
binding without discarding queued evidence.

`filamenthub-edge --status` prints secret-free local diagnostics for the node and
each connection, including pending observations and usage backlogs. Use
`--status --connection workshop-mmu` to inspect one entry.
In Docker, use `docker exec filamenthub-edge python -m filamenthub_edge.container --status`
so diagnostics read the private options through the same privilege-dropping entrypoint.
`filamenthub-edge --reset-connection --connection workshop-mmu` revokes only the
selected idle binding; it refuses to discard an active job or durable retry data.
Stop the service before resetting, then restart it afterwards. SIGTERM saves a
checkpoint from the last verified counters without starting new network requests;
it is delivered from the outbox after restart. A lost Moonraker connection also
checkpoints previously verified counters, with delivery retried while cloud is
offline. The stop grace period accommodates a provider request already in flight,
including the configurable request timeout (up to 60 seconds).

To add a printer, append a connection with a new unique `id`, its LAN endpoint,
and its pairing code, then restart the service/container. No second installation
is needed. To pause one printer, set its `enabled` to `false` and restart. Removing
an entry from the configuration also stops its worker but does not revoke or
delete its saved binding and pending events. The status command continues to list
it as unconfigured. Restore the same `id` to resume its queue. Do not rename IDs,
reuse an ID for a different printer, copy state between nodes, or run multiple
connections against the same endpoint.

## Verify the connection

In a normal browser, refresh the printer card after Edge's first exchange. All
gates, including empty ones and the bypass when reported, should appear. A paired
status or heartbeat alone is not evidence of a received map. Edge polls every
30 seconds by default; the UI labels stale observations rather than presenting
them as live. Refreshing the browser does not force an immediate printer query.

Exact spool IDs are accepted only when Moonraker's configured Spoolman URL matches
this printer's FilamentHub inventory and the spools belong to this account.
`spool_id=-1` means unknown identity, not an empty gate. Reported spools appear
separately from the user's assignments; select the detected spool and save only
after reviewing it. Empty or unknown observations never clear desired assignments.

In OrcaSlicer, use **Check printer** for a fresh local comparison and explicit
adopt/apply actions. Without Orca, assignments exchange through native Happy Hare
Spoolman support. For an explicit refresh, the current documented command is
`MMU_SPOOLMAN REFRESH=1`, run in the printer console while idle; Edge does not run
it remotely. Do not switch to `pull` or refresh an unreviewed remote map during
printing. See the [official command reference](https://moggieuk.github.io/Happy-Hare-Doc/Reference-Commands/#mmu_spoolman).

Both local readers can be enabled together. They use one physical printer and
material system. The newest active-source observation wins; delayed data cannot
shrink a newer topology, and neither reader makes an automatic desired assignment.

## Release checklist

The repository root `repository.yaml` identifies the HA feed. Supervisor discovers
the app under `edge-agent/home-assistant/filamenthub_edge/`; there is no second
runtime or separate application repository. The metadata under
`edge-agent/home-assistant/repository.yaml` matches the root for standalone package
exports; tests prevent these copies from drifting.

Before an owner publishes a release:

1. Run `python edge-agent/scripts/check_versions.py`, the Edge tests, Ruff and mypy.
   Test tooling includes PyYAML; the runtime itself has no added dependencies.
2. Build and run `python edge-agent/scripts/smoke_image.py <image>` for both
   supported architectures. This keeps its isolated synthetic containers/volume
   for inspection; it does not contact printers or FilamentHub.
3. Publish the matching `edge-vX.Y.Z` release through the existing Edge workflow.
   It validates both platform images before publishing the versioned multi-arch
   manifest. Make the GHCR package public and verify an unauthenticated pull of
   that exact version; HA users must not need registry credentials.
4. Publish the matching feed metadata only when its versioned image is available.
   Subsequent releases update the package/runtime/image/app versions together and
   the app's `CHANGELOG.md`. Keep the repository URL and app slug stable.
5. On the selected HA host, verify store installation, configuration of two
   printers, pairing, logs, restart and update with preserved identity/queues.
   Container tests do not replace this Supervisor or real-printer verification.

HA uses `config.yaml`'s exact version tag, not `latest`. There is no automatic
publisher inside Edge and no automatic update of printer software. Publication,
HA installation and physical-print verification are separate owner-run steps.
