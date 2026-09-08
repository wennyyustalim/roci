"""Serialize a RocketSpec to an OpenRocket `.ork` file.

An `.ork` is a zip archive holding a single `rocket.ork` XML entry. Git sees
one opaque blob; that is the whole reason this project has something to say
about diffing.

The element layout follows what OpenRocket itself writes (check against
`datafiles/examples/*.ork` inside the OpenRocket jar). Positions are the
modern `<axialoffset method="...">` form plus the legacy `<position type>`
twin, exactly as OpenRocket emits them, so the file opens without warnings in
23.09 and 24.12. Verified by opening the output in the OpenRocket GUI.
"""

from __future__ import annotations

import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from rocinante.spec import FinSet, Motor, NoseCone, Recovery, RocketSpec

OPENROCKET_VERSION = "23.09"
DOC_FORMAT_VERSION = "1.9"

# Bulk densities (kg/m^3) OpenRocket ships for the materials the spec names.
DENSITIES = {"Cardboard": 680.0, "Plywood": 630.0, "Polystyrene": 1050.0, "Balsa": 170.0}


def _text(parent: ET.Element, tag: str, value: object, **attrs: str) -> ET.Element:
    el = ET.SubElement(parent, tag, attrs)
    el.text = str(value).lower() if isinstance(value, bool) else str(value)
    return el


def _material(parent: ET.Element, name: str, tag: str = "material") -> None:
    density = DENSITIES.get(name, 680.0)
    el = ET.SubElement(parent, tag, {"type": "bulk", "density": str(density)})
    el.text = name


def _position(parent: ET.Element, method: str, value: float) -> None:
    """OpenRocket writes both spellings; older loaders read only the second."""
    _text(parent, "axialoffset", value, method=method)
    _text(parent, "position", value, type=method)


def _nose_element(nose: NoseCone, ballast_kg: float) -> ET.Element:
    el = ET.Element("nosecone")
    _text(el, "name", "Nose cone")
    _text(el, "finish", "normal")
    _material(el, nose.material)
    _text(el, "length", nose.length_m)
    _text(el, "thickness", nose.wall_thickness_m)
    _text(el, "shape", nose.shape.value)
    _text(el, "shapeparameter", nose.shape_parameter)
    _text(el, "aftradius", nose.base_radius_m)
    _text(el, "aftshoulderradius", 0.0)
    _text(el, "aftshoulderlength", 0.0)
    _text(el, "aftshoulderthickness", 0.0)
    _text(el, "aftshouldercapped", False)
    _text(el, "isflipped", False)

    if ballast_kg > 0:
        subs = ET.SubElement(el, "subcomponents")
        mass = ET.SubElement(subs, "masscomponent")
        _text(mass, "name", "Nose ballast")
        _position(mass, "top", 0.0)
        _text(mass, "packedlength", 0.02)
        _text(mass, "packedradius", 0.01)
        _text(mass, "radialposition", 0.0)
        _text(mass, "radialdirection", 0.0)
        _text(mass, "mass", ballast_kg)
        _text(mass, "masscomponenttype", "masscomponent")
    return el


def _parachute_element(recovery: Recovery) -> ET.Element:
    el = ET.Element("parachute")
    _text(el, "name", "Parachute")
    _position(el, "top", 0.02)
    _text(el, "packedlength", 0.04)
    _text(el, "packedradius", 0.009)
    _text(el, "radialposition", 0.0)
    _text(el, "radialdirection", 0.0)
    _text(el, "cd", recovery.drag_coefficient)
    surface = ET.SubElement(el, "material", {"type": "surface", "density": "0.067"})
    surface.text = "Ripstop nylon"
    _text(el, "deployevent", "apogee" if recovery.deploy_at_apogee else "ejection")
    _text(el, "deployaltitude", 200.0)
    _text(el, "deploydelay", 0.0)
    _text(el, "diameter", recovery.chute_diameter_m)
    _text(el, "linecount", 6)
    _text(el, "linelength", recovery.chute_diameter_m)
    line = ET.SubElement(el, "linematerial", {"type": "line", "density": "0.0018"})
    line.text = "Elastic cord (round 2mm, 1/16 in)"
    return el


def _fin_element(fins: FinSet) -> ET.Element:
    el = ET.Element("trapezoidfinset")
    _text(el, "name", "Fin set")
    _text(el, "instancecount", fins.count)
    _text(el, "fincount", fins.count)
    _text(el, "radiusoffset", 0.0, method="surface")
    _text(el, "angleoffset", 0.0, method="relative")
    _text(el, "rotation", 0.0)
    _position(el, "bottom", -fins.offset_from_aft_m)
    _text(el, "finish", "normal")
    _material(el, fins.material)
    _text(el, "thickness", fins.thickness_m)
    _text(el, "crosssection", fins.cross_section.value)
    _text(el, "cant", 0.0)
    _text(el, "filletradius", 0.0)
    _material(el, "Cardboard", tag="filletmaterial")
    _text(el, "rootchord", fins.root_chord_m)
    _text(el, "tipchord", fins.tip_chord_m)
    _text(el, "sweeplength", fins.sweep_m)
    _text(el, "height", fins.height_m)
    return el


def _motor_mount_element(motor: Motor, config_id: str) -> ET.Element:
    el = ET.Element("innertube")
    _text(el, "name", "Motor mount")
    _position(el, "bottom", 0.0)
    _material(el, "Cardboard")
    _text(el, "length", motor.length_mm / 1000)
    _text(el, "radialposition", 0.0)
    _text(el, "radialdirection", 0.0)
    _text(el, "outerradius", motor.diameter_mm / 2000 + 0.0005)
    _text(el, "thickness", 0.0005)
    _text(el, "clusterconfiguration", "single")
    _text(el, "clusterscale", 1.0)
    _text(el, "clusterrotation", 0.0)

    mount = ET.SubElement(el, "motormount")
    _text(mount, "ignitionevent", "automatic")
    _text(mount, "ignitiondelay", 0.0)
    _text(mount, "overhang", 0.003)
    m = ET.SubElement(mount, "motor", {"configid": config_id})
    _text(m, "type", "single")
    _text(m, "manufacturer", motor.manufacturer)
    _text(m, "designation", motor.designation)
    _text(m, "diameter", motor.diameter_mm / 1000)
    _text(m, "length", motor.length_mm / 1000)
    _text(m, "delay", motor.delay_s)
    ignition = ET.SubElement(mount, "ignitionconfiguration", {"configid": config_id})
    _text(ignition, "ignitionevent", "automatic")
    _text(ignition, "ignitiondelay", 0.0)
    return el


def _body_elements(spec: RocketSpec, config_id: str) -> list[ET.Element]:
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
        if i == 0:
            subs.append(_parachute_element(spec.recovery))
        if i == last:
            subs.append(_fin_element(spec.fins))
            subs.append(_motor_mount_element(spec.motor, config_id))
        elements.append(el)
    return elements


def spec_to_xml(spec: RocketSpec) -> ET.Element:
    # OpenRocket keys motors to a flight configuration by id. One design, one config.
    config_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "rocinante:" + spec.model_dump_json()))
    root = ET.Element(
        "openrocket",
        {"version": DOC_FORMAT_VERSION, "creator": f"OpenRocket {OPENROCKET_VERSION}"},
    )
    rocket = ET.SubElement(root, "rocket")
    _text(rocket, "name", spec.name)
    _position(rocket, "absolute", 0.0)
    _text(rocket, "designer", "Rocinante")
    if spec.rationale:
        _text(rocket, "comment", spec.rationale)
    config = ET.SubElement(rocket, "motorconfiguration", {"configid": config_id, "default": "true"})
    ET.SubElement(config, "stage", {"number": "0", "active": "true"})
    _text(rocket, "referencetype", "maximum")

    stage = ET.SubElement(ET.SubElement(rocket, "subcomponents"), "stage")
    _text(stage, "name", "Sustainer")
    stage_subs = ET.SubElement(stage, "subcomponents")
    stage_subs.append(_nose_element(spec.nose, spec.nose_ballast_kg))
    for el in _body_elements(spec, config_id):
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
