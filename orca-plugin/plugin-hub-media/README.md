# Orca Cloud gallery

This directory contains the publication-ready FilamentHub Plugin Hub gallery.
The source screenshots use only public or fictional showcase data.

## Source capture requirements

- PNG at `1920 x 1080` or higher; do not resize or crop before adding it here.
- English UI, one consistent theme and 100% application scaling where possible.
- Use fictional showcase data and hide private addresses, account data and keys.
- Close transient menus and tooltips unless they are the feature being shown.
- Keep the complete OrcaSlicer or embedded-page viewport; the renderer owns the
  final presentation crop.

Render the four `1600 x 900` PNG files from the repository root:

```powershell
python orca-plugin/plugin-hub-media/render_gallery.py
```

Upload the images from `final/` to the FilamentHub card in this order:

1. `01-find-a-profile.png`
2. `02-sync-on-your-terms.png`
3. `03-native-orcaslicer-presets.png`
4. `04-real-spools-and-material-systems.png`

The sources are real plugin/OrcaSlicer screenshots captured with fictional
showcase data. Do not replace them with production account screenshots
containing private data. The old `output/` directory is retained only as a
working archive and must not be uploaded.

The Orca Cloud editor assigns a hosted media URL after upload. Replace the old
image URLs in `orca-plugin/description.md` with the new hosted URLs before saving
the public card. Publication remains an owner action.
