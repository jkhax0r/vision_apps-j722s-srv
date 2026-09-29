#!/usr/bin/env python3
"""Bounded, per-port TEVS controls; independent of Qt and the image pipeline."""
import argparse
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

MANAGED = ("exposure_mode", "exposure", "gain", "brightness",
           "power_line_frequency", "ae_exposure_upper", "ae_exposure_max")
POSITIONS = ("top left", "top right", "bottom left", "bottom right")


def run(*args):
    result = subprocess.run(list(map(str, args)), text=True, capture_output=True, timeout=5)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[-1200:])
    return result.stdout


def discover(topology, devices):
    entities = {}
    for block in re.split(r"(?m)(?=^- entity )", topology):
        match = re.match(r"- entity \d+: (.+) \(", block)
        if match:
            node = re.search(r"device node name (\S+)", block)
            entities[match[1]] = (node[1] if node else "", block)
    found = {}
    bridge = entities["cdns_csi2rx.30101000.csi-bridge"][1]
    csi = entities["30102000.ticsi2rx"][1]
    for name, (node, block) in entities.items():
        identity = re.fullmatch(r"tevs \d+-(003[9abc])", name)
        if not identity:
            continue
        link = re.search(r'-> "(max96724 [^"]+)":(\d+) \[ENABLED', block)
        if not link:
            raise ValueError(f"Missing MAX96724 link for {name}")
        route = re.search(rf"\b{link[2]}/0 -> 0/(\d+) \[ACTIVE\]", entities[link[1]][1])
        if not route:
            raise ValueError(f"Inactive route for {name}")
        via = re.search(rf"\b0/{route[1]} -> 1/(\d+) \[ACTIVE\]", bridge)
        context = re.search(rf"\b0/{via[1]} -> (\d+)/0 \[ACTIVE\]", csi) if via else None
        if not context:
            raise ValueError(f"Missing CSI route for {name}")
        video = entities[f"30102000.ticsi2rx context {context[1]}"][0]
        if not re.fullmatch(r"/dev/v4l-subdev\d+", node) or video in found:
            raise ValueError("Invalid/ambiguous camera graph")
        found[video] = dict(identity=identity[1], entity=name, device=node, video=video)
    if len(devices) != 4 or len(set(devices)) != 4 or set(devices) != set(found):
        raise ValueError("The renderer must have four distinct TEVS camera inputs")
    return [dict(found[video], label=f"Camera {i+1} ({POSITIONS[i]})")
            for i, video in enumerate(devices)]


def parse_controls(text):
    controls, current = {}, None
    for line in text.splitlines():
        match = re.match(r"\s*(\w+) 0x[0-9a-f]+ \((\w+)\)\s*:\s*(.*)", line)
        if match:
            current = None
            name, kind, fields = match.groups()
            if name not in (*MANAGED, "max_fps"):
                continue
            values = {k: int(v) for k, v in re.findall(r"(min|max|step|default|value)=(-?\d+)", fields)}
            if not all(k in values for k in ("min", "max", "default", "value")):
                raise ValueError(f"Incomplete control metadata: {name}")
            values.update(kind=kind, step=values.get("step", 1), menu={},
                          readonly="read-only" in fields, inactive="inactive" in fields)
            current = controls[name] = values
        elif current is not None and current["kind"] == "menu":
            item = re.match(r"\s*(\d+): (.+)", line)
            if item:
                current["menu"][int(item[1])] = item[2]
    missing = set(MANAGED)-set(controls)
    if missing:
        raise ValueError(f"Missing TEVS controls: {sorted(missing)}")
    return controls


def cameras():
    pid = int(run("systemctl", "show", "jk-flex-ti-srv.service", "-p", "MainPID", "--value").strip())
    if pid <= 0:
        raise ValueError("Live camera renderer is not running")
    argv = Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")
    devices = [a for a in argv if re.fullmatch(r"/dev/video\d+", a)]
    rows = discover(run("media-ctl", "-d", "/dev/media0", "-p"), devices)
    for camera in rows:
        camera["controls"] = read(camera)
    return rows


def read(camera):
    return parse_controls(run("v4l2-ctl", "-d", camera["device"], "--list-ctrls-menus"))


def values(camera):
    return {name: camera["controls"][name]["value"] for name in MANAGED}


def live_limit(name, controls):
    frame = 1000000 // max(1, controls.get("max_fps", {}).get("value", 30))
    if name == "exposure":
        return min(controls[name]["max"], frame)
    if name == "ae_exposure_max":
        return min(controls[name]["max"], max(frame, controls[name]["default"]))
    return controls[name]["max"]


def validate(updates, controls):
    if not isinstance(updates, dict) or not updates or set(updates)-set(MANAGED):
        raise ValueError("Unsupported camera controls")
    for name, value in updates.items():
        control = controls[name]
        if type(value) is not int or not control["min"] <= value <= control["max"]:
            raise ValueError(f"{name}: value outside driver range")
        if control["readonly"] or (value-control["min"]) % control["step"]:
            raise ValueError(f"{name}: read-only or invalid step")
        if control["kind"] == "menu" and value not in control["menu"]:
            raise ValueError(f"{name}: unavailable mode")
        if value > live_limit(name, controls):
            raise ValueError(f"{name}: exceeds live-view limit {live_limit(name, controls)}")
    upper = updates.get("ae_exposure_upper", controls["ae_exposure_upper"]["value"])
    maximum = updates.get("ae_exposure_max", controls["ae_exposure_max"]["value"])
    if upper > maximum:
        raise ValueError("Auto shutter maximum must not be below its upper threshold")


def write(camera, updates):
    validate(updates, camera["controls"])
    def set_one(name, value):
        run("v4l2-ctl", "-d", camera["device"], f"--set-ctrl={name}={value}")
    # Load manual setpoints in manual mode, then restore the requested AE mode.
    manual = bool(set(updates) & {"exposure", "gain"})
    final_mode = updates.get("exposure_mode", camera["controls"]["exposure_mode"]["value"])
    if manual:
        set_one("exposure_mode", 0)
    names = [n for n in updates if n != "exposure_mode"]
    if "ae_exposure_max" in names and "ae_exposure_upper" in names:
        names.remove("ae_exposure_max"); names.remove("ae_exposure_upper")
        pair = ["ae_exposure_max", "ae_exposure_upper"]
        if updates["ae_exposure_max"] < camera["controls"]["ae_exposure_upper"]["value"]:
            pair.reverse()
        names = pair+names
    for name in names:
        set_one(name, updates[name])
    if manual or "exposure_mode" in updates:
        set_one("exposure_mode", final_mode)
    actual = read(camera)
    if any(actual[name]["value"] != value for name, value in updates.items()):
        raise RuntimeError(f"Control readback mismatch on {camera['entity']}")
    camera["controls"] = actual


def load_settings(path):
    if not path.exists():
        return {"schema_version": 1, "cameras": {}}
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1 or not isinstance(data.get("cameras"), dict):
        raise ValueError("Invalid saved camera settings")
    if set(data["cameras"])-{"0039", "003a", "003b", "003c"}:
        raise ValueError("Unknown saved camera port")
    return data


def save_settings(path, data):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as f:
        os.chmod(temporary, 0o600)
        json.dump(data, f, indent=2)
        f.write("\n"); f.flush(); os.fsync(f.fileno())
    temporary.replace(path)


def apply(rows, changes, settings_path, persist=True):
    data = load_settings(settings_path)
    if set(changes)-{c["identity"] for c in rows}:
        raise ValueError("Selected camera is no longer connected")
    for camera in rows:
        if camera["identity"] in changes:
            validate(changes[camera["identity"]], camera["controls"])
    touched = []
    try:
        for camera in rows:
            key = camera["identity"]
            if key not in changes:
                continue
            touched.append((camera, values(camera)))
            write(camera, changes[key])
            data["cameras"][key] = values(camera)
        if persist:
            save_settings(settings_path, data)
    except Exception as error:
        failures = []
        for camera, old in reversed(touched):
            try:
                camera["controls"] = read(camera)
                write(camera, old)
            except Exception as rollback:
                failures.append(f"{camera['entity']}: {rollback}")
        suffix = "; rollback failed: "+"; ".join(failures) if failures else "; previous settings restored"
        raise RuntimeError(str(error)+suffix) from error
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "set", "defaults", "restore"))
    parser.add_argument("--runtime", type=Path, default=Path("/opt/jk-ti-srv-flex"))
    parser.add_argument("--sensor", default="0039")
    parser.add_argument("--updates", default="{}")
    args = parser.parse_args()
    settings_path = args.runtime/"camera_settings.json"
    with ExitStack() as stack:
        # Restore is called by the live launcher, including during CAL recovery.
        if args.action != "restore":
            lock = stack.enter_context((args.runtime/"calibration.lock").open("a"))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Calibration is running; camera settings are locked")
        lock = stack.enter_context((args.runtime/"camera_settings.lock").open("a"))
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "restore" and not settings_path.exists():
            print(json.dumps({"message": "No saved camera settings"})); return
        rows = cameras()
        if args.action == "restore":
            apply(rows, load_settings(settings_path)["cameras"], settings_path, persist=False)
        elif args.action in ("set", "defaults"):
            selected = [c for c in rows if args.sensor in ("all", c["identity"])]
            if not selected:
                raise ValueError("Unknown camera selection")
            changes = {}
            for camera in selected:
                updates = (json.loads(args.updates) if args.action == "set" else
                           {n: camera["controls"][n]["default"] for n in MANAGED})
                mode = updates.get("exposure_mode", camera["controls"]["exposure_mode"]["value"])
                if args.action == "set" and (("exposure" in updates and mode == 1) or
                                             ("gain" in updates and mode != 0)):
                    raise ValueError("Shutter/gain is controlled automatically in this mode")
                changes[camera["identity"]] = updates
            apply(rows, changes, settings_path)
        print(json.dumps({"cameras": rows, "message": "Settings saved" if args.action in ("set", "defaults") else ""}))


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise InterruptedError("Camera command interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    try:
        main()
    except Exception as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
