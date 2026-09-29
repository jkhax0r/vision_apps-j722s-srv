# Helios Center Badge

This is the active badge again, restored at its pre-Enovation size. The alternate
[Enovation Controls icon](ENOVATION_ASSET.md) remains available.

`helios-h.svg` contains the three original emblem paths extracted from the
Helios Technologies website's header logo, retrieved September 29, 2026:

- Website: https://www.heliostechnologies.com/
- Original artwork: https://d1io3yog0oux5.cloudfront.net/_2f29f86af95d14c851c3049b11ab36f4/heliostechnologies/files/theme/images/logo-sm.svg

The wordmark and registration symbol are omitted and the SVG viewport is limited
to the emblem. Path geometry and colors are unchanged. The artwork remains the
property/trademark of its owner; this is not an open-source license grant.

The existing Qt CAL overlay places the badge at the center of the right-hand
stitched viewport at 198 pixels wide and 85% opacity (15% see-through). It is decorative, does not
accept input, and sits behind CAL
dialogs. It does not change camera capture, TI rendering, calibration meshes,
recorded images, or offline calibration previews. Its relative placement follows
the existing half-screen comparison layout, not an estimated camera pose.

`deploy_calibration_ui.py` includes this asset automatically. Redeploy the UI and
its boot launcher will use the new bundle on subsequent boots. No TI rebuild is
needed for this overlay.
