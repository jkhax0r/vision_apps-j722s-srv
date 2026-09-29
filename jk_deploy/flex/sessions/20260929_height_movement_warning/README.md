# Raised Tripod: Advisory Movement Warnings

Source target job: `/root/jk-calibration-jobs/20260929T184100Z_9bc278`.
The user raised the tripod about one foot and walked around during capture.

The original whole-image motion gate stopped at pass01/input0/frame8:
41 of 664 textured tiles changed (6.17%, above the 6% threshold). Changed tiles
were mostly below the table around the arm/chair. Median feature movement was
0.105 native pixels; p95 was 0.314 pixels. Frames 9-11 also exceeded the texture
change threshold. This was not a tripod-height or camera-format limitation.

Per user direction, motion is now diagnostic only. All frames are arithmetically
averaged, with no registration, frame dropping, or motion-triggered abort.
Within-burst and between-pass diagnostics are stored as `motion_warnings` with
`motion_policy: warn_only`. On successful completion the UI shows an amber
movement/scene-change warning. Marker/geometry/fit-consistency validation and
capture-integrity checks remain enforced.

Replaying the capture exposed a second issue: a 17.7-pixel checker-texture false
positive decoded as ID 37 in input1. The actual corner labels 1,2,3,4 were each
seen in two views, with shortest edges about 58-74 pixels. Automatic selection
now uses IDs shared across cameras, then applies all existing geometry checks.
An ambiguous fifth shared ID, an undersized real shared marker, or missing
corners still reject the fit. Single-view extras are recorded, not selected.

The complete saved capture replay passed with **four motion warnings**, all
three independent fits passed, and pass 2 was selected. The fake marker was
ignored in pass01 and pass03. Local result:
`/tmp/jk-height-warning-calibration-v2`.
Local raw copy: `/tmp/jk-height-20260929T184100Z/raw`.

Installed source bundle:
`/opt/jk-ti-srv-flex/calibration_ui_08cfeb6d95c4`.
No fresh capture or new live preset was applied during this fix. The CAL button
uses the corrected tools on its next run. Verification: 67 regression tests,
complete saved-data replay, and an offscreen Qt render of the completion warning
on the target. Original failing job and previous live preset remain intact.
