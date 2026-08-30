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

The current runtime supports only one Moonraker endpoint and one printer binding
per instance. Multi-printer configuration within one node is not implemented yet;
the instructions below describe the current single-printer setup.

OrcaSlicer is optional. Install on the printer's Linux computer or another
always-on computer on the same LAN. No inbound internet port, printer API key in
FilamentHub, or separate hardware is required. Do not install into Klipper's or
Moonraker's Python environment.

1. In FilamentHub, add a physical printer and its Happy Hare material system.
   Create physical spools in **My Filaments**, not just catalogue entries.
2. Open the printer's integration settings and copy its generated Spoolman URL
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
4. Under **Connection with and without Orca**, create a one-time pairing code
   for this material system, then use one installation option below.

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
  "pairing_code": "FH-XXXXX-XXXXX",
  "material_provider": "happy_hare",
  "moonraker_url": "http://127.0.0.1:7125",
  "moonraker_api_key": ""
}
```

Use the printer's LAN address when running on another computer. If Moonraker
requires an API key, enter it only in this local file; do not disable its
authentication or expose it to the internet. Test one exchange:

```sh
FH_EDGE_OPTIONS_FILE="$HOME/.config/filamenthub-edge/options.json" \
FH_EDGE_STATE_PATH="$HOME/.local/share/filamenthub-edge/edge-state.json" \
  "$HOME/.local/share/filamenthub-edge/venv/bin/filamenthub-edge" --once
```

After a successful exchange, remove only the `pairing_code` option, preserving
the state file. For continuous operation on a systemd Linux host:

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
run multiple copies using the same state file.

### Docker

Build the image from this checkout; the command does not assume a published
registry image exists:

```sh
docker build -t filamenthub-edge:local ./edge-agent
```

Put the options above into a local protected `options.json` readable by the
container's `filamenthub` user. Resolve its UID with
`docker run --entrypoint id filamenthub-edge:local -u`, then grant that UID read
access without making the file world-readable. Mount it read-only; keep durable state
in a named volume. The host-network example is for Linux:

```text
docker run --restart unless-stopped --network host \
  --name filamenthub-edge \
  -v /absolute/path/options.json:/data/options.json:ro \
  -v filamenthub-edge-data:/data \
  filamenthub-edge:local
```

On Docker Desktop use an explicit reachable printer LAN address in the options,
not container-local `127.0.0.1`. Host networking availability depends on the host.
The Home Assistant packaging in this repository is not a published add-on feed;
use these source-install options unless a release explicitly supplies one.

The pairing code is needed only for the first successful connection. The
revocable bridge token, cached desired state, pending observation, usage tracker,
and bounded durable usage outbox are stored in `/data/edge-state.json`.
Clear the one-time pairing code from the container or Home Assistant options
after pairing. Supplying a new code rotates the credential for the same printer
binding without discarding queued evidence.

`filamenthub-edge --status` prints secret-free local diagnostics, including the
pending observation and usage backlog. `filamenthub-edge --reset-connection`
revokes an idle binding before moving the same Edge to another printer; it
refuses to discard an active job or durable retry data. SIGTERM and a lost
Moonraker connection produce a final safe usage checkpoint when evidence is
available, leaving it in the outbox if the cloud is offline.

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
