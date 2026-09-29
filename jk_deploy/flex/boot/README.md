# Flex Boot Startup

The Flex now boots into the four-camera TI stitching comparison with CAL controls.
The old Ahsoka SimpleUI application, its application-services process, and its
installer are stopped and disabled. Their binaries are not deleted: the platform
still needs the shared Ahsoka Weston configuration, layer manager, drivers,
backlights, touch mapping, networking, and system housekeeping.

## Reproduce

The four-camera runtime, CAL bundle, and saved calibration must already work on
the target. From the repository root:

```sh
python3 jk_deploy/flex/deploy_boot.py
```

The small versioned bundle includes `run_boot.py`, `stage_table.py`, the unit,
retirement drop-in, and installer. Installation checks the saved calibration and
verifies the unit before changing startup. It refuses an existing boot install
rather than silently overwriting it. It backs up vendor unit files and enable
states under `/opt/jk-ti-srv-flex/before_boot_<UTC>/`.

Installed on September 29:

- Bundle: `/opt/jk-ti-srv-flex/boot_20260929T190143Z`.
- Backup: `/opt/jk-ti-srv-flex/before_boot_20260929T190159Z`.
- Receipt: `/opt/jk-ti-srv-flex/boot_install.json`.
- Boot service: `jk-flex-autostart.service`, enabled under `ahsoka.target`.

The vendor Application/Services/Installer units get
`90-jk-demo-retired.conf` drop-ins. These suppress stop/failure hooks that would
launch the competing installer, and require a deliberately absent
`/opt/jk-ti-srv-flex/allow-vendor-demo` flag before the old applications can start.
No platform unit, BSP, firmware, network configuration, or TI renderer is replaced.

## Behavior

The boot service runs **after** the platform's `ahsoka.target` and display/driver
bring-up. Network/SSH startup has no dependency on this unit. It waits up to 60
seconds for DSI-1's overlay layer, then uses the existing camera launcher. Failed
startup retries after ten seconds without holding the rest of boot.

It loads the last successful `active_table_calibration.json` launcher, verifying
its report, binaries, hashes, and camera order. If no active metadata exists, it
uses the initial named marker preset. A corrupt recorded preset is an error, not
a silent switch to a different calibration. A CAL in progress holds a lock;
starting this service then leaves that session alone. An already-running renderer
is also left alone. Every later successful CAL updates the next boot's preset.

The boot service is a oneshot launcher with `RemainAfterExit`, not a second
renderer supervisor. Existing transient renderer/UI services do the actual work.
Intentional renderer stops during CAL are not counteracted by a restart loop.

```sh
systemctl status jk-flex-autostart.service
journalctl -u jk-flex-autostart.service -b --no-pager
systemctl stop jk-flex-autostart.service
systemctl start jk-flex-autostart.service
```

Stopping the boot service stops the CAL UI first, allowing worker cancellation
cleanup, then stops the camera renderer. Do not restart it during a calibration
unless cancellation is intended. The old demo no longer appears during capture;
the CAL controls remain visible while camera video is paused.

## Restore The Original Demo

```sh
python3 /opt/jk-ti-srv-flex/boot/install.py --restore
```

This stops/disables the stitching boot service, removes only this install's
retirement drop-ins, restores the previous enable states, and starts the original
application. Calibration files and the TI runtime remain available.

Verification at installation: systemd unit verification passed; 73 regression
tests passed; all three old application units are disabled/inactive; display and
layer-manager services remain active; video frames advance and CAL remains on
layer 102. The in-progress user CAL was not interrupted and subsequently applied
successfully in 473.2 seconds, with a movement warning. Its saved preset is
`table_20260929T185653Z_4f6252` and will be selected at the next boot. A reboot test
has not yet been performed.
