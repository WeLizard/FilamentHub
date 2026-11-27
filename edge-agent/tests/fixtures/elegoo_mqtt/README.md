# Elegoo MQTT printer fixtures

Shared by the OrcaSlicer plugin and FH Edge. All of them are written by hand:
no printer of FilamentHub's own produced any of them. They are an Elegoo
Centauri Carbon 2 over Elegoo's own MQTT interface (not SDCP), with made-up
values and the field names of these sources:

- elegooofficial/elegoo-link @ ec2d2269, `elegoo_fdm_cc2_protocol.cpp` and
  `elegoo_fdm_cc2_message_adapter.cpp`;
- OrcaSlicer's bundled Elegoo panel, `resources/web/elegoolink/lan_service_web`
  (OrcaSlicer @ 7cdc829a).

The files:

- `system_info.json`: `GET /system/info`;
- `status_printing.json`: method 1002;
- `canvas.json`: method 2005;
- `mono_filament.json`: method 1061.

Trays are numbered from 0, as danielcherubini/elegoo-homeassistant @ ce9c1559
reads them (`sdcp/models/ams.py`).
