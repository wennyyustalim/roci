"""Runs inside the visible Blender window used by ``rocinante demo``.

The host writes the currently selected ShipSpec to a JSON file.  This script
polls that small file from Blender's timer API and replaces the generated
scene when it changes.  The geometry functions live in build_ship.py so the
interactive scene and the exported GLB can never drift apart.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import bpy
from build_ship import (
    add_lights,
    apply_materials,
    build_decks,
    build_drive,
    build_hull,
    build_pdcs,
    build_tubes,
    clear_scene,
    frame_camera,
)

SPEC_PATH = Path(sys.argv[sys.argv.index("--") + 1])
last_digest: str | None = None


def refresh():
    global last_digest
    try:
        raw = SPEC_PATH.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest == last_digest:
            return 1.0
        spec = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Rocinante live scene waiting for a valid spec: {exc}")
        return 1.0

    clear_scene()
    objects = (
        build_hull(spec)
        + build_drive(spec)
        + build_pdcs(spec)
        + build_tubes(spec)
        + build_decks(spec)
    )
    apply_materials(objects)
    add_lights(frame_camera(objects))
    bpy.context.scene["rocinante_spec_path"] = str(SPEC_PATH)
    bpy.context.scene["rocinante_parts"] = len(objects)
    last_digest = digest
    print(f"Rocinante live scene refreshed: {len(objects)} parts")
    return 1.0


refresh()
bpy.app.timers.register(refresh, first_interval=1.0, persistent=True)
