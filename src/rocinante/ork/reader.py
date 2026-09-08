"""Parse a `.ork` archive back into a RocketSpec.

Only used by the round-trip test and by the `rocinante import` command, which
seeds the agent from a rocket a human already drew. It does not need to
handle every OpenRocket document -- it needs to handle the subset the writer
produces, plus whatever reference file you build on the morning.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from rocinante.spec import BodyTube, FinSet, NoseCone, RocketSpec


def _f(el: ET.Element | None, tag: str, default: float = 0.0) -> float:
    if el is None:
        return default
    found = el.find(tag)
    if found is None or not found.text:
        return default
    try:
        return float(found.text)
    except ValueError:
        # OpenRocket writes "auto" for radii it derives from a neighbour.
        return default


def _s(el: ET.Element | None, tag: str, default: str = "") -> str:
    if el is None:
        return default
    found = el.find(tag)
    return found.text or default if found is not None else default


def read_ork(path: str | Path) -> RocketSpec:
    with zipfile.ZipFile(path) as zf:
        name = "rocket.ork" if "rocket.ork" in zf.namelist() else zf.namelist()[0]
        root = ET.fromstring(zf.read(name))

    rocket = root.find("rocket")
    nose_el = root.find(".//nosecone")
    fin_el = root.find(".//trapezoidfinset")
    tube_els = root.findall(".//bodytube")

    if nose_el is None or fin_el is None or not tube_els:
        raise ValueError(f"{path}: not a rocket this reader understands")

    nose = NoseCone(
        shape=_s(nose_el, "shape", "ogive"),
        length_m=_f(nose_el, "length", 0.1),
        base_radius_m=_f(nose_el, "aftradius", 0.012),
        wall_thickness_m=_f(nose_el, "thickness", 0.002) or 0.002,
        shape_parameter=_f(nose_el, "shapeparameter", 1.0),
        material=_s(nose_el, "material", "Cardboard"),
    )
    body = [
        BodyTube(
            name=_s(t, "name", f"Tube {i + 1}"),
            length_m=_f(t, "length", 0.1),
            outer_radius_m=_f(t, "radius", 0.012) or 0.012,
            wall_thickness_m=_f(t, "thickness", 0.0015) or 0.0015,
            material=_s(t, "material", "Cardboard"),
        )
        for i, t in enumerate(tube_els)
    ]
    fins = FinSet(
        count=int(_f(fin_el, "fincount", 3)),
        root_chord_m=_f(fin_el, "rootchord", 0.05),
        tip_chord_m=_f(fin_el, "tipchord", 0.03),
        height_m=_f(fin_el, "height", 0.04),
        sweep_m=_f(fin_el, "sweeplength", 0.0),
        thickness_m=_f(fin_el, "thickness", 0.003) or 0.003,
        cross_section=_s(fin_el, "crosssection", "square"),
        offset_from_aft_m=abs(_f(fin_el, "axialoffset", 0.0)),
        material=_s(fin_el, "material", "Plywood"),
    )
    ballast = _f(root.find(".//nosecone/subcomponents/masscomponent"), "mass", 0.0)

    return RocketSpec(
        name=_s(rocket, "name", "Imported"),
        nose=nose,
        body=body,
        fins=fins,
        nose_ballast_kg=ballast,
    )
