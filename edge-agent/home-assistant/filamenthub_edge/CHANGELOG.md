# Changelog

## 0.1.0

- Initial experimental Home Assistant package for one Edge node with multiple
  independent Moonraker/Happy Hare or direct-feed printer connections.
- Local pairing credentials, persistent per-printer queues and shared node identity.
- Flashforge printers over their LAN API and Bambu Lab printers over LAN MQTT, next to
  Klipper. Both are charged the slicer's estimate for the job.
- Printers on the open SDCP protocol (Elegoo Centauri Carbon) and the Elegoo Centauri
  Carbon 2 over Elegoo's MQTT interface: print state and CANVAS slots, read only. These
  printers count no filament, so nothing is charged. Not yet confirmed on a printer.
- Transparent FilamentHub icon and logo, with app introduction, instructions and configuration
  labels in Russian, English and Chinese.
- Private Supervisor options, unprivileged runtime and graceful shutdown.
- Optional per-printer `auto_refresh` (off by default) updates Happy Hare pull
  assignments without Orca. Requires manual Klipper guard installation; printing,
  pause, unknown state and unverified connections block or defer changes.
- Durable latest target and observed acknowledgement, with refresh status and reasons.
- No inbound port, host networking or Supervisor API access. No arbitrary cloud commands.
