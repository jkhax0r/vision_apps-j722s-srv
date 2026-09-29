#!/usr/bin/env python3
"""Install the Flex boot launcher on target, backing up platform unit state."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/opt/jk-ti-srv-flex')
HERE = Path(__file__).resolve().parent
SYSTEM = Path('/etc/systemd/system')
VENDOR = ('Ahsoka.Application.service', 'Ahsoka.Services.service', 'Ahsoka.Installer.service')
UNIT = 'jk-flex-autostart.service'
DROPIN = '90-jk-demo-retired.conf'


def run(*args, check=True, timeout=30):
    return subprocess.run(args, text=True, capture_output=True, check=check, timeout=timeout)


def install():
    from run_boot import select_launcher
    select_launcher(ROOT)
    if not (ROOT/'run_calibration_ui.sh').is_file():
        raise ValueError('Install CAL controls before enabling boot startup')
    run('systemd-analyze', 'verify', str(HERE/UNIT))
    if (ROOT/'allow-vendor-demo').exists():
        raise ValueError('Remove the vendor-demo override flag before installing')
    if (SYSTEM/UNIT).exists() or (ROOT/'boot').exists():
        raise ValueError('Boot configuration already exists; inspect before replacing')
    for unit in VENDOR:
        if (SYSTEM/(unit+'.d')/DROPIN).exists():
            raise ValueError('Existing retirement override: '+unit)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = ROOT/('before_boot_'+stamp)
    backup.mkdir()
    states = {u: run('systemctl', 'is-enabled', u, check=False).stdout.strip() for u in VENDOR}
    for unit in VENDOR:
        shutil.copy2(SYSTEM/unit, backup/unit)
    (backup/'states.json').write_text(json.dumps(states, indent=2)+'\n')
    for unit in VENDOR:
        drop = SYSTEM/(unit+'.d')
        drop.mkdir(exist_ok=True)
        shutil.copy2(HERE/'retire-demo.conf', drop/DROPIN)
    # Remove the vendor stop/failure hooks before stopping its UI.
    run('systemctl', 'daemon-reload')
    run('systemctl', 'disable', *VENDOR)
    run('systemctl', 'stop', *VENDOR)
    (ROOT/'boot').symlink_to(HERE)
    shutil.copy2(HERE/UNIT, SYSTEM/UNIT)
    receipt = {'backup': str(backup), 'source': str(HERE), 'unit': UNIT, 'vendor_states': states}
    (ROOT/'boot_install.json').write_text(json.dumps(receipt, indent=2)+'\n')
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', UNIT)
    run('systemctl', '--no-block', 'start', UNIT)
    print(json.dumps(receipt, indent=2))


def restore():
    receipt = json.loads((ROOT/'boot_install.json').read_text())
    run('systemctl', 'disable', '--now', UNIT, timeout=120)
    (SYSTEM/UNIT).unlink()
    for unit in VENDOR:
        (SYSTEM/(unit+'.d')/DROPIN).unlink(missing_ok=True)
    run('systemctl', 'daemon-reload')
    for unit, state in receipt['vendor_states'].items():
        if state == 'enabled':
            run('systemctl', 'enable', unit)
    (ROOT/'boot').unlink()
    (ROOT/'boot_install.json').rename(Path(receipt['backup'])/'restored_boot_install.json')
    run('systemctl', '--no-block', 'start', 'Ahsoka.Application.service')
    print('Original demo startup restored.')


if __name__ == '__main__':
    restore() if '--restore' in sys.argv else install()
