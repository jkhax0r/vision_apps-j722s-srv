#!/usr/bin/env python3
"""Replace only the private native runtime, keeping the active calibration and launchers."""
import argparse
import hashlib
from pathlib import Path
import shlex
import subprocess

INSTALL = r'''
from datetime import datetime, timezone
import fcntl, hashlib, json, os
from pathlib import Path
import shutil, socket, subprocess, sys
stage=Path(sys.argv[1]); expected=sys.argv[2:]
runtime=Path('/opt/jk-ti-srv-flex')
names=('vx_app_jk_srv_live.out', 'libtivision_apps.so.11.0.0')
for name, digest in zip(names, expected):
    if hashlib.sha256((stage/name).read_bytes()).hexdigest()!=digest:
        raise RuntimeError('Staged checksum mismatch: '+name)
launcher=Path(json.loads((runtime/'active_table_calibration.json').read_text())['launcher'])
if not launcher.is_relative_to(runtime) or not launcher.is_file():
    raise RuntimeError('No valid active calibration launcher')
with (runtime/'calibration.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if Path('/run/jk-calibration-ui.sock').exists():
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(3); connection.connect('/run/jk-calibration-ui.sock')
            connection.sendall(b'{"action":"status"}\n')
            state=json.loads(connection.recv(8192))
        if state.get('busy') or state.get('camera_busy'):
            raise RuntimeError('Calibration or camera command in progress')
    backup=runtime/('before_preview_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir()
    for name in (*names, 'active_table_calibration.json'):
        shutil.copy2(runtime/name, backup/name)
    subprocess.run(['systemctl','stop','jk-calibration-ui.service'],check=True)
    subprocess.run(['systemctl','stop','jk-flex-ti-srv.service'],check=True)
    try:
        for name in names:
            temporary=runtime/(name+'.new')
            shutil.copy2(stage/name,temporary)
            temporary.chmod(0o755 if name.endswith('.out') else 0o644)
            temporary.replace(runtime/name)
        subprocess.run([str(launcher)],check=True,timeout=90)
    except Exception:
        subprocess.run(['systemctl','stop','jk-flex-ti-srv.service'],check=False)
        for name in names:
            temporary=runtime/(name+'.rollback')
            shutil.copy2(backup/name,temporary); temporary.replace(runtime/name)
        subprocess.run([str(launcher)],check=True,timeout=90)
        raise
    print('Native preview runtime installed. Previous binaries:',backup)
shutil.rmtree(stage)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', default='root@192.168.20.222')
    parser.add_argument('--known-hosts', type=Path, default=Path.home()/'.ssh/known_hosts_flex')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    out = repo/'out/J722S/A53/LINUX/release'
    files = [out/name for name in ('vx_app_jk_srv_live.out', 'libtivision_apps.so.11.0.0')]
    digests = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
    options = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=6', '-o', 'ServerAliveInterval=3',
               '-o', 'ServerAliveCountMax=2', '-o', f'UserKnownHostsFile={args.known_hosts}']
    stage = subprocess.check_output(['ssh', *options, args.target,
                                     'mktemp -d /tmp/jk-preview-runtime.XXXXXX'], text=True).strip()
    subprocess.run(['scp', *options, *map(str, files), f'{args.target}:{stage}/'], check=True)
    subprocess.run(['ssh', *options, args.target, 'python3 - '+shlex.join([stage, *digests])],
                   input=INSTALL, text=True, check=True)


if __name__ == '__main__':
    main()
