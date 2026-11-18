# OpenPrintTag reference tags

Raw NFC-V memory dumps from the OpenPrintTag specification's own test suite
(`tests/encode_decode/*_data.bin` in https://github.com/prusa3d/OpenPrintTag,
commit 060e4208, 2026-10-09). Copyright 2025 Prusa Research a.s., MIT licence.

- `01_data.bin` - a complete Prusament PLA tag;
- `03_data.bin` - a tag the specification marks invalid (print temperature
  range reversed) with a consumed weight in its auxiliary region;
- `05_data.bin` - a minimal tag carrying unknown keys and enum values.
