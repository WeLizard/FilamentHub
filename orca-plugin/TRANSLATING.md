# Translating the FilamentHub OrcaSlicer plugin

The plugin follows `orca.host.app_language()` and accepts every locale currently
published by OrcaSlicer:

`ca`, `cs`, `de`, `en`, `es`, `eu`, `fr`, `hu`, `it`, `ja`, `ko`, `lt`, `nl`,
`pl`, `pt_BR`, `ru`, `sv`, `th`, `tr`, `uk`, `vi`, `zh_CN`, `zh_TW`.

Translations live in `filamenthub_locales/<locale>.json`. A catalog may be
partial: missing keys fall back to English, so contributors can improve one
useful group of messages without translating the whole plugin at once.

To contribute:

1. Copy `filamenthub_locales/en.json` to the required OrcaSlicer locale name,
   or edit an existing catalog.
2. Translate values only. Do not rename keys or placeholders such as `{name}`,
   `{count}` and `{status}`.
3. Keep the file UTF-8 JSON and do not add runtime code or remote resources.
4. Run:

   ```powershell
   python validate_locales.py
   python -m pytest tests/test_filamenthub_plugin.py -q
   ```

Translation-only pull requests are welcome. Translator credit is recorded in
the release notes when the catalog is bundled into a wheel.
