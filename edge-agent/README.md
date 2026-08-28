# FilamentHub Edge

The Edge runtime keeps FilamentHub connected to local printer hardware without
exposing LAN credentials to the cloud. The first provider reads Moonraker and
Happy Hare, synchronizes observed printer/slot state to FilamentHub, and keeps a
durable local copy of desired spool and preset assignments.

It never treats provider observations as user-approved assignments. When
Moonraker exposes the cumulative `print_stats.filament_used` counter, Edge sends
replay-protected usage checkpoints only for an unambiguous active desired spool;
FilamentHub remains the only writer of canonical spool consumption.

## Docker

```text
docker run --restart unless-stopped --network host \
  -e FH_EDGE_FILAMENTHUB_URL=https://filamenthub.ru \
  -e FH_EDGE_PAIRING_CODE=FH-XXXXX-XXXXX \
  -e FH_EDGE_MATERIAL_PROVIDER=happy_hare \
  -e FH_EDGE_MOONRAKER_URL=http://127.0.0.1:7125 \
  -e FH_EDGE_MOONRAKER_API_KEY=... \
  -v filamenthub-edge-data:/data \
  filamenthub-edge:local
```

The pairing code is needed only for the first successful connection. The
revocable bridge token, cached desired state, pending observation, usage tracker,
and bounded durable usage outbox are stored in `/data/edge-state.json`.
