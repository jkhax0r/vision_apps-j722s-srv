# Enovation Controls Center Icon

This alternate icon is retained but inactive. The overlay has returned to the
[Helios H](HELIOS_ASSET.md); dimensions below describe the last N preview.

`enovation-n.svg` contains the two original N-icon paths from Enovation Controls'
official website header artwork, retrieved September 29, 2026:

- Brand kit supplied by the user: https://enovationcontrols.com/shared-files/25422/?Brand%20Kit.pdf
- Original SVG: https://enovationcontrols.com/wp-content/uploads/2024/01/EnovationControlsLogo_Vector-Jan24.svg
- Standalone reference: https://enovationcontrols.com/wp-content/uploads/2023/05/ICON-WHITE-BACKGROUND.png

The wordmark is omitted and the viewport is cropped to the N. Geometry and the
source SVG's black/red colors are unchanged. The artwork remains the property
and trademark of its owner; no open-source artwork license is implied.

The brand kit's Icon Usage page requires Marketing permission for standalone
use. Its Logo Treatments page also advises against effects and busy photographic
backgrounds. This translucent in-camera overlay is a requested demo preview,
not a claim of brand-guideline approval for public/show use.

The existing Qt overlay centers the icon in the stitched right pane, in a
247.5 x 255.5-pixel bounding box (25% larger than the initial N). PreserveAspectFit
keeps its natural, narrower proportions. Opacity remains 85%. No backdrop is
added. The original camera panes, calibration files, capture and TI renderer
are unchanged. The retained `helios-h.svg` is available for switching back.

Deploy with `python3 jk_deploy/flex/deploy_calibration_ui.py` from the repository
root. The existing boot service picks up the new UI bundle automatically.
