"""Export an immutable revision pair for a Kord comparison."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse

from rocinante.blend import build_ship_mesh
from rocinante.ship import ShipSpec


def export_pair(out: Path, current: dict, parent: dict) -> dict:
    directory = out / "exports" / f"v{current['index']:04d}"
    directory.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for side, entry in (("before", parent), ("after", current)):
        spec = ShipSpec.model_validate(entry["spec"])
        spec_path = directory / f"{side}.json"
        spec_path.write_text(spec.model_dump_json(indent=2))
        mesh_path = build_ship_mesh(spec, directory / f"{side}.glb")
        artifacts[side] = {
            "file": str(mesh_path.relative_to(out)),
            "sha256": hashlib.sha256(mesh_path.read_bytes()).hexdigest(),
            "bytes": mesh_path.stat().st_size,
        }
    report = {
        "revision": current["index"], "parent": parent["index"],
        "source": current.get("source"), "ask": current.get("ask"),
        "model": current.get("model"),
        "rationale": current["rationale"], "changes": current["changes"],
        "geometry_changed_parts": current.get("geometry_changed_parts", []),
        "before": {key: parent[key] for key in ("derived", "mission", "delta_v_margin")},
        "after": {key: current[key] for key in ("derived", "mission", "delta_v_margin")},
        "artifacts": artifacts,
    }
    (directory / "comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    return artifacts


def verified_pair(out: Path, artifacts: dict) -> tuple[Path, Path]:
    paths = []
    for side in ("before", "after"):
        artifact = artifacts[side]
        path = (out / artifact["file"]).resolve()
        if not path.is_relative_to((out / "exports").resolve()):
            raise ValueError("Export path is outside the export directory")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ValueError("Export bytes changed or are missing; export the comparison again")
        paths.append(path)
    return paths[0], paths[1]


def share_url(base: str, value: str) -> str:
    url = urljoin(base + "/", value)
    if not value or urlparse(url).scheme not in ("http", "https"):
        raise ValueError("Kord returned no usable comparison URL")
    return url
