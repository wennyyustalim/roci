"""Serialize a RocketSpec to an OpenRocket `.ork` file.

An `.ork` is a zip archive holding a single `rocket.ork` XML entry. Git sees
one opaque blob; that is the whole reason this project has something to say
about diffing.

STATUS: skeleton. The element names below follow the OpenRocket 23.09 document
format, but the schema has corners (auto radii, motor mounts, material density
attributes) that only a real file will teach you.

FIRST TASK ON THE DAY:
  1. Open OpenRocket, build a two-tube rocket with one fin set, save it.
  2. `unzip -p reference.ork rocket.ork | xmllint --format -`
  3. Fix this writer until `tests/test_ork_roundtrip.py` passes against it.
Do not move on until a file this writer produces opens in the OpenRocket GUI.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from rocinante.spec import FinSet, NoseCone, RocketSpec

OPENROCKET_VERSION = "23.09"
DOC_FORMAT_VERSION = "1.9"


def _text(parent: ET.Element, tag: str, value: object) -> ET.Element:
    el = ET.SubElement(parent, tag)
    el.text = str(value).lower() if isinstance(value, bool) else str(value)
    return el


def _material(parent: ET.Element, name: str, density: float = 680.0) -> None:
    el = ET.SubElement(parent, "material", {"type": "bulk", "density": str(density)})
    el.text = name


def _nose_element(nose: NoseCone, ballast_kg: float) -> ET.Element:
    el = ET.Element("nosecone")
    _text(el, "name", "Nose cone")
    _text(el, "finish", "normal")
    _material(el, nose.material)
    _text(el, "length", nose.length_m)
    _text(el, "thickness", nose.wall_thickness_m)
    _text(el, "shape", nose.shape.value)
    _text(el, "shapeclipped", False)
    _text(el, "shapeparameter", nose.shape_parameter)
    _text(el, "aftradius", nose.base_radius_m)
    _text(el, "aftshoulderradius", 0.0)
    _text(el, "aftshoulderlength", 0.0)

    if ballast_kg > 0:
        subs = ET.SubElement(el, "subcomponents")
        mass = ET.SubElement(subs, "masscomponent")
        _text(mass, "name", "Nose ballast")
        _text(mass, "axialoffset", 0.0)
        _text(mass, "axialmethod", "TOP")
        _text(mass, "packedlength", 0.02)
        _text(mass, "packedradius", 0.01)
        _text(mass, "mass", ballast_kg)
        _text(mass, "masscomponenttype", "MASSCOMPONENT")
    return el


def _fin_element(fins: FinSet) -> ET.Element:
    el = ET.Element("trapezoidfinset")
    _text(el, "name", "Fin set")
    _material(el, fins.material, density=630.0)
    _text(el, "finish", "normal")
    _text(el, "axialoffset", -fins.offset_from_aft_m)
    _text(el, "axialmethod", "BOTTOM")
    _text(el, "fincount", fins.count)
    _text(el, "rotation", 0.0)
    _text(el, "thickness", fins.thickness_m)
    _text(el, "crosssection", fins.cross_section.value)
    _text(el, "cant", 0.0)
    _text(el, "rootchord", fins.root_chord_m)
    _text(el, "tipchord", fins.tip_chord_m)
    _text(el, "sweeplength", fins.sweep_m)
    _text(el, "height", fins.height_m)
    return el


def _body_elements(spec: RocketSpec) -> list[ET.Element]:
    elements: list[ET.Element] = []
    last = len(spec.body) - 1
    for i, tube in enumerate(spec.body):
        el = ET.Element("bodytube")
        _text(el, "name", tube.name)
        _text(el, "finish", "normal")
        _material(el, tube.material)
        _text(el, "length", tube.length_m)
        _text(el, "thickness", tube.wall_thickness_m)
        _text(el, "radius", tube.outer_radius_m)

        subs = ET.SubElement(el, "subcomponents")
        if i == last:
            subs.append(_fin_element(spec.fins))
            mount = ET.SubElement(subs, "innertube")
            _text(mount, "name", "Motor mount")
            _text(mount, "axialoffset", 0.0)
            _text(mount, "axialmethod", "BOTTOM")
            _text(mount, "length", spec.motor.length_mm / 1000)
            _text(mount, "outerradius", spec.motor.diameter_mm / 2000 + 0.0005)
            _text(mount, "thickness", 0.0005)
            _text(mount, "motormount", True)
        if not len(subs):
            el.remove(subs)
        elements.append(el)
    return elements


def spec_to_xml(spec: RocketSpec) -> ET.Element:
    root = ET.Element(
        "openrocket",
        {"version": DOC_FORMAT_VERSION, "creator": f"OpenRocket {OPENROCKET_VERSION}"},
    )
    rocket = ET.SubElement(root, "rocket")
    _text(rocket, "name", spec.name)
    _text(rocket, "revision", "rocinante")

    stage_subs = ET.SubElement(ET.SubElement(ET.SubElement(rocket, "subcomponents"), "stage"), "subcomponents")
    stage_subs.append(_nose_element(spec.nose, spec.nose_ballast_kg))
    for el in _body_elements(spec):
        stage_subs.append(el)
    return root


def write_ork(spec: RocketSpec, path: str | Path) -> Path:
    """Write `spec` as a `.ork` archive and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    xml = ET.tostring(spec_to_xml(spec), encoding="unicode")
    body = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml}\n'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("rocket.ork", body)
    return path
