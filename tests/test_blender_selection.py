"""Exercise selection resolution and visibility in real Blender when installed."""
import os
import subprocess
from pathlib import Path

import pytest

from rocinante.samples import ROCINANTE


def test_blender_focuses_every_model_and_restores_ship(tmp_path):
    blender = Path(os.getenv("BLENDER_BIN", "/Applications/Blender.app/Contents/MacOS/Blender"))
    if not blender.is_file():
        pytest.skip("Blender is not installed")
    spec = tmp_path / "blender-current.json"
    spec.write_text(ROCINANTE.model_dump_json())
    bridge = Path("src/rocinante/blend/live_ship.py").resolve()
    script = tmp_path / "check.py"
    script.write_text(f'''
import json, runpy, sys, time
from pathlib import Path
import bpy
sys.argv = ["blender", "--factory-startup", "--", {str(spec)!r}]
ns = runpy.run_path({str(bridge)!r})
focus = ns["focus"]
base = {{o.name: o.location.copy() for o in bpy.context.scene.objects}}
selections = [
    {{"kind":"torpedo", "id":"torpedo_01"}},
    *({{"kind":"deck", "id":i}} for i in range(6)),
    *({{"kind":"crew", "id":"crew_"+name}} for name in ("alex", "holden", "amos", "naomi")),
    *({{"kind":"part", "id":name}} for name in ("drive_bell", "drive_cone", "pdc_01", "tube_01")),
    *({{"kind":"landmark", "id":name}} for name in ("ceres", "tycho", "ring")),
    {{"kind":"ship", "expanded":True}}, {{"kind":"ship", "expanded":False}},
]
for i, selection in enumerate(selections):
    command = {{"request_id":i, "selection":selection}}
    focus(command)
    animation = focus.__globals__["animation"]
    assert animation, selection
    assert animation[2] > .12, selection
    selected = list(bpy.context.selected_objects)
    assert selected and all(not o.hide_get() for o in selected), selection
    kind, ident = selection["kind"], selection.get("id")
    for o in bpy.context.scene.objects:
        if not (o.get("rocinante_part") or o.get("landmark_id")):
            continue
        expected = (not o.get("landmark_id") if kind == "ship" else
            o.get("torpedo_id") == ident if kind == "torpedo" else
            o.get("deck_index") == ident if kind == "deck" else
            o.get("deck_index") == selected[0].get("deck_index") if kind == "crew" else
            o.get("landmark_id") == ident if kind == "landmark" else
            o.get("rocinante_part") == ident)
        assert o.hide_get() != expected, (selection, o.name)
    focus.__globals__["animation"] = (time.monotonic()-2, *animation[1:])
    ns["animate"]()
    reply = json.loads(Path({str(tmp_path / 'blender-selection-status.json')!r}).read_text())
    assert reply["status"] == "synced" and reply["request_id"] == i, reply
for name, location in base.items():
    assert (bpy.data.objects[name].location-location).length < 1e-6, name
focus({{"request_id":999,"selection":{{"kind":"part","id":"missing"}}}})
assert focus.__globals__["animation"] is None
print("PASS: every selection frames its meshes, reveals its subject, acknowledges, and restores the ship")
''')
    result = subprocess.run([str(blender), "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(script)], capture_output=True, text=True, timeout=90, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: every selection" in result.stdout
