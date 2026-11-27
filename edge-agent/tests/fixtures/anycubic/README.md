# Anycubic LAN fixtures

No printer produced these files. They are written by hand to the fields that
open LAN clients of the Kobra 3 / S1 / X read (`chrisfore/anycubic_ha_local`
@ 65d5bd91, `rvanderp3/kobra-connect` @ 3edba246); the research note in the
private documentation keeps the references. Serial numbers, device ids,
tokens and passwords are made up.

- `info_lan_s1.json`, `info_cloud_s1.json` — `GET :18910/info` with LAN mode on
  and off.
- `ctrl_answer.json` — the answer to the signed `POST /ctrl`; its `data.info`
  is `ctrl_session.json` sealed with AES-128-CBC (key `token[16:32]` of
  `info_lan_s1.json`, vector `data.token`, PKCS#7).
- `info_*.json`, `multicolorbox_*.json`, `extfilbox_answer.json` — whole MQTT
  messages as they arrive on `…/printer/public/<model>/<device>/<type>/report`.
