#!/usr/bin/env python3
"""Stage a passed calibration in a NEW target directory; never start/stop the demo."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
REMOTE = "/opt/jk-ti-srv-flex"
FILES = ("four_mesh.bin", "four_blend.bin", "calibration.json", "report.json", "camera_order.txt")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_candidate(session):
    report = json.loads((session/"report.json").read_text())
    config = json.loads((session/"calibration.json").read_text())
    if report.get("status") != "passed" or config.get("schema_version") != 2:
        raise ValueError("Only passed schema-2 candidates can be staged")
    if report.get("simulated_input"):
        raise ValueError("Simulated test input cannot be staged as a live calibration")
    if report.get("deployment_policy") == "repeat-child":
        raise ValueError("Stage the complete repeated-capture result, not an individual pass")
    if report.get("deployment_policy") == "repeat-confirmed" and not report.get("repeat_consistency", {}).get("passed"):
        raise ValueError("Repeated-capture consistency was not accepted")
    if "clean_refinement" in config or "clean_refinement" in report:
        refinement = report.get("clean_refinement", {})
        if (refinement != config.get("clean_refinement") or not refinement.get("passed") or
                not refinement.get("crop_preserved") or len(refinement.get("cameras", [])) != 4):
            raise ValueError("Two-stage checker refinement was not accepted")
    order = list(map(int, (session/"camera_order.txt").read_text().split()))
    if sorted(order) != [0, 1, 2, 3] or order != config["capture_order"] or order != report["capture_order"]:
        raise ValueError("Camera order file does not match validated calibration")
    for name, size in (("four_mesh.bin", 4*136*136*7*2), ("four_blend.bin", 4*136*136*2)):
        path = session/name
        if path.stat().st_size != size or digest(path) != config["sha256"][name] or digest(path) != report["artifact_sha256"][name]:
            raise ValueError(f"Changed or invalid artifact: {name}")


def stage(session, target, known_hosts):
    if target.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_@.:-]+", target):
        raise ValueError("Use a plain SSH host or user@host")
    validate_candidate(session)
    options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=6", "-o", "ServerAliveInterval=3",
               "-o", "ServerAliveCountMax=2", "-o", f"UserKnownHostsFile={known_hosts}"]
    def ssh(command):
        return subprocess.run(["ssh", *options, target, command], check=True,
                              text=True, capture_output=True, timeout=60).stdout.strip()
    token = re.sub(r"[^a-zA-Z0-9_-]", "_", session.name)
    destination = f"{REMOTE}/table_{token}_{digest(session/'four_mesh.bin')[:10]}"
    temporary = ""
    with tempfile.TemporaryDirectory(prefix="jk-table-install-") as tmp:
        local = Path(tmp)
        for name in FILES:
            shutil.copy2(session/name, local/name)
        shutil.copy2(HERE/"run_table_candidate.sh", local/"run.sh")
        # Validate the copied snapshot too, so all deployed files belong together.
        validate_candidate(local)
        names = [*FILES, "run.sh"]
        (local/"SHA256SUMS").write_text("".join(f"{digest(local/name)}  {name}\n" for name in names))
        try:
            temporary = ssh(f"test -x {REMOTE}/run_flex_stitch.sh && test ! -e {shlex.quote(destination)} && "
                            f"mktemp -d {REMOTE}/.table-stage.XXXXXX")
            if not re.fullmatch(re.escape(REMOTE)+r"/\.table-stage\.[A-Za-z0-9]+", temporary):
                raise ValueError("Unexpected remote staging path")
            subprocess.run(["scp", *options, *[str(local/n) for n in [*names, "SHA256SUMS"]],
                            f"{target}:{temporary}/"], check=True, timeout=120)
            ssh(f"cd {shlex.quote(temporary)} && sha256sum -c SHA256SUMS && chmod 0755 run.sh && "
                f"test ! -e {shlex.quote(destination)} && mv -T {shlex.quote(temporary)} {shlex.quote(destination)}")
            temporary = ""
        finally:
            if re.fullmatch(re.escape(REMOTE)+r"/\.table-stage\.[A-Za-z0-9]+", temporary):
                ssh(f"rm -rf -- {shlex.quote(temporary)}")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--target", default="root@192.168.20.222")
    parser.add_argument("--known-hosts", type=Path, default=Path.home()/".ssh/known_hosts_flex")
    args = parser.parse_args()
    try:
        destination = stage(args.session, args.target, args.known_hosts)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Not staged: {error}\n")
    print(f"Staged without changing the running demo.\nOn target, run: {destination}/run.sh\n"
          "Previous marker preset: /root/run_flex_markers.sh")


if __name__ == "__main__":
    main()
