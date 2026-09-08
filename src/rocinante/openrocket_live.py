"""Attach a local document bridge to OpenRocket; never replace its JVM or frame."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from rocinante.demo import open_openrocket

_attached: set[tuple[int, str]] = set()


def java_tools() -> Path:
    candidates = [Path(os.environ.get("JAVA_HOME", "/nonexistent")) / "bin",
                  Path("/opt/homebrew/opt/openjdk/bin"), Path("/usr/local/opt/openjdk/bin")]
    if shutil.which("javac"):
        candidates.append(Path(shutil.which("javac")).resolve().parent)
    for path in candidates:
        if all((path / name).is_file() for name in ("java", "javac", "jar", "jcmd")):
            return path
    raise RuntimeError("A JDK with the Attach API is required for live OpenRocket updates")


def bridge_jar(directory: Path, java: Path) -> Path:
    sources = Path(__file__).with_name("integrations")
    digest = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(sources.glob("*.java")))).hexdigest()[:16]
    build = directory / "openrocket-bridge" / digest
    jar = build / "bridge.jar"
    if jar.exists():
        return jar
    build.mkdir(parents=True, exist_ok=True)
    agent_class = f"RocinanteAgent_{digest}"
    agent_source = build / f"{agent_class}.java"
    agent_source.write_text((sources / "RocinanteAgent.java").read_text().replace("class RocinanteAgent", f"class {agent_class}"))
    subprocess.run([str(java / "javac"), "--release", "11", "--add-modules", "jdk.attach", "-d", str(build),
                    str(agent_source), str(sources / "RocinanteAttach.java")], check=True, capture_output=True, text=True)
    manifest = build / "MANIFEST.MF"
    manifest.write_text(f"Manifest-Version: 1.0\nAgent-Class: {agent_class}\n\n")
    subprocess.run([str(java / "jar"), "cfm", str(jar), str(manifest), "-C", str(build), "."],
                   check=True, capture_output=True)
    return jar


def openrocket_pids(java: Path) -> list[int]:
    listing = subprocess.run([str(java / "jcmd"), "-l"], check=True, capture_output=True, text=True, timeout=10)
    return [int(line.split()[0]) for line in listing.stdout.splitlines()
            if "openrocket" in line.lower() or "com.install4j.runtime.launcher.MacLauncher" in line]


def show_in_openrocket(path: Path, selection: Path, bounds=None, *, simulation=None) -> dict:
    java = java_tools()
    pids = openrocket_pids(java)
    if not pids:
        if not open_openrocket(path, bounds=bounds):
            raise RuntimeError("OpenRocket is not installed")
        for _ in range(30):
            time.sleep(.3)
            pids = openrocket_pids(java)
            if pids:
                break
    if len(pids) != 1:
        raise RuntimeError("Expected one OpenRocket session; no existing window was changed")
    command = json.loads(selection.read_text())
    if simulation is not None:
        command = {**command, **simulation}
    jar = bridge_jar(selection.parent, java)
    props = selection.with_name(f"openrocket-selection-{jar.parent.name}.properties")
    content = (f"request_id={command['request_id']}\n"
               f"file={base64.b64encode(str(path.resolve()).encode()).decode()}\n"
               f"digest={hashlib.sha256(path.read_bytes()).hexdigest()}\n"
               f"label=Rocinante {command['torpedo_id'] or 'general torpedo'} v{command['revision']}\n")
    if simulation is not None:
        content += f"action=simulation\nlaunch_id={simulation['request_id']}\nascent_end={simulation['ascent_end']}\n"
    temp = props.with_suffix(".tmp")
    temp.write_text(content)
    temp.replace(props)
    key = (pids[0], str(props.resolve()))
    if key not in _attached:
        # An initial startup may publish its JVM before the first frame exists.
        for attempt in range(20):
            result = subprocess.run([str(java / "java"), "--add-modules", "jdk.attach", "-cp", str(jar),
                                     "RocinanteAttach", str(pids[0]), str(jar.resolve()), str(props.resolve())],
                                    capture_output=True, text=True, timeout=15, check=False)
            if result.returncode == 0:
                _attached.add(key)
                break
            if attempt == 19:
                raise RuntimeError("OpenRocket rejected the live document bridge; its window was left open")
            time.sleep(.3)
    return {"status": "pending", "request_id": command["request_id"]}
