#!/usr/bin/env python3
"""Install isolated AArch64/Python-3.12 calibration tools and the touch overlay."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
WHEELS = ("numpy==2.2.6", "scipy==1.15.3", "opencv-python-headless==4.12.0.88")
ORIGINAL_STITCH_SHA = "5784e3b69eb9ef50c36a2b74c2b61d3f57e5525bd03f840be5984da6d9a5042f"

INSTALL = r'''
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,os,platform,shutil,socket,subprocess,sys,tarfile,zipfile
archive=Path(sys.argv[1]); name=sys.argv[2]; original=sys.argv[3]
runtime=Path('/opt/jk-ti-srv-flex'); dest=runtime/name
if sys.version_info[:2] != (3,12) or platform.machine() != 'aarch64':
 raise RuntimeError('This dependency bundle requires AArch64 Python 3.12')
def ensure_idle():
 if Path('/run/jk-calibration-ui.sock').exists():
  try:
   with socket.socket(socket.AF_UNIX) as s:
    s.settimeout(2); s.connect('/run/jk-calibration-ui.sock'); s.sendall(b'{"action":"status"}\n')
    state=json.loads(s.recv(8192))
   if state.get('busy') or state.get('camera_busy'): raise RuntimeError('Calibration/camera command running; refuse UI replacement')
  except (ConnectionRefusedError, FileNotFoundError): pass
ensure_idle()
if dest.exists(): raise FileExistsError(dest)
dest.mkdir()
with tarfile.open(archive) as data: data.extractall(dest, filter='data')
manifest=json.loads((dest/'manifest.json').read_text())
for relative,expected in manifest.items():
 if hashlib.sha256((dest/relative).read_bytes()).hexdigest()!=expected: raise RuntimeError('Hash mismatch: '+relative)
for wheel in (dest/'wheels').glob('*.whl'):
 with zipfile.ZipFile(wheel) as z: z.extractall(dest/'python')
env=dict(os.environ,PYTHONPATH=str(dest/'python'),OPENBLAS_NUM_THREADS='1')
subprocess.run(['/usr/bin/python3','-c','import cv2,numpy,scipy; from scipy.interpolate import RBFInterpolator; assert hasattr(cv2,"aruco"); print(cv2.__version__,numpy.__version__,scipy.__version__)'],env=env,check=True)
stitch=runtime/'run_flex_stitch.sh'; incoming=dest/'tools/flex/run_flex_stitch.sh'
current=hashlib.sha256(stitch.read_bytes()).hexdigest()
expected=hashlib.sha256(incoming.read_bytes()).hexdigest()
if current not in (original,expected): raise RuntimeError('Runtime launcher has other edits; merge manually before installation')
backup=runtime/('before_cal_ui_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir()
shutil.copy2(stitch,backup/stitch.name)
ensure_idle()
subprocess.run(['systemctl','stop','jk-calibration-ui.service'],check=False)
shutil.copy2(incoming,stitch); stitch.chmod(0o755)
launcher=dest/'tools/flex/ui/run_ui.sh'; launcher.chmod(0o755)
link=runtime/'run_calibration_ui.sh'
if link.exists() or link.is_symlink(): link.rename(backup/link.name)
link.symlink_to(launcher)
rootlink=Path('/root/run_calibration_ui.sh')
if not rootlink.exists() and not rootlink.is_symlink(): rootlink.symlink_to(link)
subprocess.run([str(link)],check=True)
print('Installed:',dest,'Backup:',backup)
archive.unlink()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="root@192.168.20.222")
    parser.add_argument("--wheels", type=Path, default=Path("/tmp/jk-flex-cal-wheels"))
    parser.add_argument("--known-hosts", type=Path, default=Path.home()/".ssh/known_hosts_flex")
    args = parser.parse_args()
    subprocess.run([sys.executable, "-m", "pip", "download", "--dest", str(args.wheels),
                    "--platform", "manylinux2014_aarch64", "--python-version", "312", "--implementation", "cp",
                    "--abi", "cp312", "--only-binary=:all:", *WHEELS], check=True)
    files = {f"tools/flex/{p.name}": p for p in HERE.glob("*.py") if not p.name.startswith("test_")}
    for p in (HERE/"ui").iterdir():
        if p.is_file():
            files[f"tools/flex/ui/{p.name}"] = p
    for name in ("run_table_candidate.sh", "run_flex_stitch.sh"):
        files[f"tools/flex/{name}"] = HERE/name
    for name in ("fit_intrinsics.py", "gmsl0_intrinsics.json", "gmsl1_intrinsics.json"):
        files[f"tools/calibration/lens_20260908/{name}"] = HERE.parent/"calibration/lens_20260908"/name
    marker = "calibration/table_corner_markers/v1/generated/marker_geometry.json"
    files[f"tools/{marker}"] = HERE.parent/marker
    for p in args.wheels.glob("*.whl"):
        files[f"wheels/{p.name}"] = p
    manifest = {relative: hashlib.sha256(path.read_bytes()).hexdigest() for relative, path in files.items()}
    name = "calibration_ui_"+hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:12]
    options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=6", "-o", "ServerAliveInterval=3", "-o",
               "ServerAliveCountMax=2", "-o", f"UserKnownHostsFile={args.known_hosts}"]
    with tempfile.TemporaryDirectory(prefix="jk-cal-ui-") as tmp:
        tmp = Path(tmp)
        (tmp/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
        archive = tmp/(name+".tar.gz")
        with tarfile.open(archive, "w:gz") as tar:
            for relative, path in files.items():
                tar.add(path, arcname=relative)
            tar.add(tmp/"manifest.json", arcname="manifest.json")
        remote = "/tmp/"+archive.name
        subprocess.run(["scp", *options, str(archive), f"{args.target}:{remote}"], check=True)
        subprocess.run(["ssh", *options, args.target,
                        "python3 - "+shlex.join([remote, name, ORIGINAL_STITCH_SHA])], input=INSTALL, text=True, check=True)


if __name__ == "__main__":
    main()
