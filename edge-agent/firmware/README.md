# FilamentHub Edge C3, telemetry bench build

This local bench prototype runs independently of OrcaSlicer. Its network path
reads printer status from explicitly configured Bambu LAN MQTT connections and
is built for printer-only uploads through the scoped FilamentHub Edge bridge.
Public Bambu Edge pairing and UI are disabled; end-to-end cloud pairing is not
available or accepted. Network end-to-end testing requires separately authorized
local backend integration. Optional PN5180 bench
commands read nearby tags and explicitly write a guarded NDEF URI locally over
USB serial. They do not send NFC observations or grants to the cloud. The
printer bridge does not send AMS slots, consumption, printer commands, camera
data, or vendor cloud credentials. An empty `connections` list is valid for a
local NFC bench. One C3 handles at most two configured printers, sequentially:
each MQTT session has a 20-second window and is closed before HTTPS upload.
This is a resource limit of this firmware, not a product-wide printer limit.

`esp32-c3-devkitm-1` is the cross-compilation target with a 4 MiB flash layout.
It does not establish the pinout, actual flash capacity, USB wiring, or
electrical suitability of a particular SuperMini board. Confirm at least 4 MiB
flash on the target. The build selects the ESP32-C3 native USB Serial/JTAG console
for bidirectional provisioning; verify that the chosen board's USB connector
actually reaches that controller before flashing. No SuperMini/PN5180 pinout is
assumed by this build.

## Build and host checks

From this directory, with PlatformIO Core available:

```powershell
pio run -e esp32-c3-devkitm-1
powershell -NoProfile -ExecutionPolicy Bypass -File tests/run_host_tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File create_flash_manifest.ps1
```

The build uses `espressif32@6.13.0` and its scoped ESP-IDF and RISC-V packages.
It does not require installing another global Python or changing project
dependencies. The build creates `bootloader.bin`, `partitions.bin`, and
`firmware.bin` under `.pio/build/esp32-c3-devkitm-1/`. The manifest command
checks the generated 4 MiB offsets and writes their actual paths, sizes and
SHA-256 hashes to `flash-manifest.json` in that directory. For a blank board,
all three images are required at 0x0, 0x8000 and 0x20000 respectively. The
framework-generated `flasher_args.json` uses different intermediate filenames;
use this build's manifest with the three existing images. No real printer or
board is exercised by a cross-build or host test.

## Provisioning

The USB serial console accepts one JSON line. It never echoes the line or
prints credentials. Disable local echo in the serial terminal too. On an empty
device the console waits for configuration. With saved configuration it accepts
a replacement line during the first 15 seconds after reboot, then starts the
runtime. Invalid or interrupted input leaves the previous NVS copy intact.

```json
{"wifi":{"ssid":"MY_WIFI","password":"MY_PASSWORD"},"cloud":{"origin":"http://192.168.1.2:3000","allow_local_http":true},"connections":[{"id":"p2s-workbench","host":"192.168.1.44","serial":"P2S_SERIAL","access_code":"LAN_ACCESS_CODE","bambu_cert_pem":"-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n","pairing_code":"ONE_TIME_CODE"}]}
```

This example is for a separately configured local development bridge; it cannot
be paired through the public site. Replace every example value before use, and
send the JSON as one line with
escaped `\n` characters inside the PEM value. Obtain the printer's actual
certificate and verify it out of band. MQTT trusts only the configured
certificate for that printer and checks its certificate common name against
the configured serial. The cloud HTTPS connection verifies the system CA
bundle. For a local development server only, `cloud.allow_local_http=true`
permits an HTTP origin on loopback or a private IPv4 address; the flag cannot
enable HTTP to a public host. A printer host must be a private or link-local
IPv4 address. Each `id` and serial must be unique within the node.

For a LAN-only diagnostic bench, omit `pairing_code` from a connection. MQTT
still uses that connection's explicit host, serial, access code and certificate;
without a scoped bridge token the firmware does not upload snapshots. Adding a
one-time code later requires a replacement provisioning line. Public site
pairing for this firmware is unavailable.
The USB event can use monotonic field ages if UTC has not synchronized, but
the printer's TLS certificate and common name are still verified. A cold boot
without trustworthy time may fail certificate validation and yield no MQTT
observation; no trust bypass or time-provisioning path is provided.

The firmware generates a stable node ID and a separate stable source ID for
each connection. Successful pairing stores its scoped `fhpb_` token and the
returned printer and material-system IDs, then removes the one-time code. A
replacement line with the same cloud origin, connection ID and serial keeps
that binding; changing the origin or serial requires a new pairing code. If a
one-time code is consumed but its result cannot be durably saved, a fresh code
is required. A revoked token stops that cloud link until reprovisioning.

Configuration and sequence reservations use two versioned, checksummed NVS
copies in a dedicated 64 KiB partition. A new sequence range is committed
before it is used, so a reboot skips unused numbers instead of replaying them.
Storage errors are reported without erasing NVS. Credentials reside on the
device; physical flash encryption is not enabled by this bench build.

## Observation behavior and acceptance

The firmware subscribes to `device/<serial>/report` over TLS port 8883 and
requests `pushall` only after the subscription acknowledgement. It accepts
fragments up to 24 KiB, rejects larger or disordered messages, and maps only
known printer status fields. A full `push_status` report resets missing facts;
partial facts expire after 30 seconds. Disconnect clears the session cache.
HTTPS upload happens after the MQTT session closes, with the timestamp taken
when the printer report arrived. It never treats an HTTP heartbeat or a stale
cache as a new printer observation. The cloud payload declares only `read` and
has an empty slot list with incomplete topology.

AMS observations are visible locally on USB serial as bounded JSON lines with
`event:"ams"` and the configured `connection_id`. An `observed` event contains
only recognized provider slot indices and fields within their 30-second TTL;
`field_age_ms` gives each retained value's age. `report_age_ms` and
`topology_age_ms` distinguish the newest packet from a prior full topology.
When UTC is unavailable, the event carries `time_basis:"monotonic"` instead
of an absolute `observed_at` timestamp.
Unknown fields are omitted. A full report with no AMS evidence emits
`status:"unknown"`; an explicit empty AMS list can report complete empty
topology. Each deliberate 20-second MQTT session close emits
`status:"stale", reason:"session_closed"`; a transport error emits
`status:"offline", reason:"transport_error"`. Both lifecycle lines have no
slot facts or observation timestamp. A later partial report cannot resurrect
fields from the prior session. The output excludes LAN credentials, tag UID and
spool identity, and makes no physical spool assignment. At most 32 slots are
accepted; larger input is rejected intact. These local diagnostics do not grant
`presence` or `tag_read` to the cloud; Bambu/Edge server authorization remains
disabled. USB and RF behavior still require hardware acceptance.

## Local AMS history journal

The firmware reserves a separate 256 KiB `ams_journal` partition at `0x320000`
on the reviewed 4 MiB layout. The NVS configuration remains at `0x9000` with
its existing 64 KiB size; the app, bootloader and partition-table offsets are
unchanged. The journal holds at most 32 compact snapshots. It is diagnostic
history only: reboot never loads it into live AMS slots, and it is never sent
to the cloud or used for consumption accounting. The USB reader works with
NFC disabled. After the provisioning window, send:

```json
{"command":"journal_read","after_seq":"0","limit":2}
```

`after_seq` is an exact decimal string; `limit` is 1–4. Continue with the
returned `next_after_seq`. Every replay line has `status:"historical"`, the
configured connection ID, stable source instance ID, boot marker and sequence.
Its nested observation also has `status:"historical"` and a separate
`capture_status` describing what was observed at the original sample time.
UTC is included only when known; monotonic time and boot marker are not
converted into a cross-reboot wall clock. When old ring entries have been
overwritten, the reader emits an explicit `ams_journal_gap` range.

Only semantic changes to topology, slot identity, known/presence, material,
color, remaining values and active feed are queued. Field ages, repeated
status ticks and UTC updates do not create records. At most one changed
snapshot is committed globally every five minutes; each configured connection
has one independent pending latest snapshot and the oldest pending connection
is served first. `coalesced_before` reports replaced pending states. Pending
states are volatile: a reset before commit can lose them, and the journal is
not a complete event history. A confirmed record uses CRC and a final commit
marker. A fully erased footer after an interrupted write is ignored on reboot;
a partially programmed footer is ambiguous and fails closed, as does damage to
a committed record. No storage error formats the partition or erases NVS.
Flash endurance and
power-loss behavior on the actual board remain unverified.

Hardware acceptance remains to be done on the owner's actual P2S and AMS:
verify board USB console and flash layout, Wi-Fi recovery, the actual LAN
certificate/common name, MQTT subscription and `pushall` response size, cloud
pairing and revocation, and free heap/stack high-water during repeated two-
printer sessions. LAN Only and Developer Mode behavior must be checked on the
installed P2S firmware; this build does not assume either toggle is required
for telemetry. The NFC bench path is separately described below. Neither path
has been tested on hardware yet.

## Optional local PN5180 bench

An absent `nfc` object disables the reader. To enable it, add an `nfc` object
with six **integer GPIO numbers** named `sck`, `miso`, `mosi`, `nss`, `busy`, and
`rst`. Each must be distinct. This C3 bench build permits only GPIO 0, 1, 3,
4, 5, 6, 7, 10, 20, and 21; it rejects the strap, flash-supply/flash, and
native-USB pins. These permitted numbers are a validation set, **not a wiring
diagram**. Confirm the actual board's exposed pins, voltage and PN5180 wiring
before configuring any numbers or applying power. The reader is never enabled
by default.

With `connections: []` and enabled NFC, `wifi` may be omitted. A local cloud
origin still scopes URI writes; for an offline development bench use a private
IPv4 HTTP origin with `allow_local_http: true`. No cloud connection or site UI
is needed for local tag commands. Wi-Fi credentials remain required when any
Bambu connection is configured. Existing version-1 saved configurations load
with NFC disabled and migrate when next saved; NVS is never erased on failure.

After the provisioning window closes, the same USB serial port accepts one
JSON command per line:

```json
{"command":"read"}
{"command":"write_uri","expected_uid":"04112233445566","uri":"http://192.168.1.2:3000/qr/FHQ1_01_X_U_abcdefghijklmnop"}
```

Replace the UID and URI with the actual values. The `write_uri` command is a
generic NDEF URI write, not a spool-identity claim; a product-only `/qr/FH-...`
URL does not identify one physical spool. The command accepts only a supplied
URI under the configured origin's `/qr/<shortcode>` path, with a shortcode of
3–100 URL-safe characters. It does not create a shortcode, contact the cloud,
pair a tag, or grant printer or account access. A write requires one selected
NTAG213/215/216 with the expected seven-byte UID, exact NXP GET_VERSION,
unlocked static and dynamic memory, writable CC, disabled password protection,
and a supported NDEF layout. NTAG213's factory Lock Control TLV is preserved.
The write uses Type 2 `A2` four-byte page writes only in user memory, stages an
empty NDEF length, commits its new length last, and verifies the full result.
Reissuing a command may repair an interruption between complete page writes;
it does not promise recovery from a physically torn EEPROM page. Unknown
layouts, protections, removal and collisions fail closed.

`read` reports the UID and detected ISO14443A or ISO15693 type. For recognized
NTAG21x tags it reports a known short NDEF URI with uncompressed, `http://`,
or `https://` prefix coding when present. It does not decode arbitrary NDEF,
ISO14443B, ten-byte ISO14443A UIDs, protected factory Bambu data, or 125 kHz
tags. The reader selects four- or seven-byte Type A UIDs, while guarded NTAG
writing requires seven bytes. A fob's color or
shape does not establish its RF protocol. It makes no slot assignment.

PN5180 RF response timing, collision behavior, the true board pinout, and
reader/tag power behavior still need hardware acceptance. The build and fake
tag tests establish only source-level behavior.
