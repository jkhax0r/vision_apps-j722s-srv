#!/usr/bin/env python3
"""Copy and install the small boot bundle without replacing the camera runtime."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', default='root@192.168.20.222')
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    options = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=6', '-o',
               'UserKnownHostsFile='+str(Path.home()/'.ssh/known_hosts_flex')]
    destination = '/opt/jk-ti-srv-flex/boot_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    subprocess.run(['ssh', *options, args.target, 'mkdir', destination], check=True)
    files = [str(p) for p in (here/'boot').iterdir() if p.is_file()]+[str(here/'stage_table.py')]
    subprocess.run(['scp', *options, *files, args.target+':'+destination+'/'], check=True)
    subprocess.run(['ssh', *options, args.target, 'python3', destination+'/install.py'], check=True)


if __name__ == '__main__':
    main()
