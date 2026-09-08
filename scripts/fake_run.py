"""Generate a synthetic design run so the viewer can be built before the agent
and the simulator exist.

The numbers are hand-authored, not simulated. They tell a plausible story:
a marginal first design, an overcorrection, a motor change, and a convergence.
Nothing here is on the path of a real run -- delete it once `rocinante design`
produces its own manifest.

    python scripts/fake_run.py --out out
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rocinante.blend import build_mesh
from rocinante.diff import diff_specs
from rocinante.ork import write_ork
from rocinante.samples import BASELINE
from rocinante.sim.base import SimResult
from rocinante.spec import BodyTube, FinSet, Motor, RocketSpec

GOAL = "3000 ft apogee, stable, minimum rail exit 15 m/s"


def variant(name: str, rationale: str, **changes) -> RocketSpec:
    spec = BASELINE.model_copy(deep=True)
    for key, value in changes.items():
        setattr(spec, key, value)
    spec.name = name
    spec.rationale = rationale
    return spec


def tubes(payload: float, booster: float, radius: float = 0.0125) -> list[BodyTube]:
    return [
        BodyTube(name="Payload", length_m=payload, outer_radius_m=radius),
        BodyTube(name="Booster", length_m=booster, outer_radius_m=radius),
    ]


RUN: list[tuple[RocketSpec, SimResult]] = [
    (
        variant(
            "Marginal", "Sized around a 24 mm E motor with a conventional 3FNC layout.",
            fins=FinSet(count=3, root_chord_m=0.045, tip_chord_m=0.025, height_m=0.028),
        ),
        SimResult(apogee_m=612, stability_margin_cal=0.94, rail_exit_velocity_ms=19.2,
                  max_velocity_ms=141, liftoff_mass_kg=0.121,
                  warnings=["Stability margin below 1 caliber"]),
    ),
    (
        variant(
            "Marginal", "Stability was under 1 caliber, so the fins grow to move the CP aft.",
            fins=FinSet(count=3, root_chord_m=0.062, tip_chord_m=0.031, height_m=0.046),
        ),
        SimResult(apogee_m=588, stability_margin_cal=1.31, rail_exit_velocity_ms=18.6,
                  max_velocity_ms=134, liftoff_mass_kg=0.129),
    ),
    (
        variant(
            "Sweep", "Sweeps the leading edge to recover some of the drag the larger fins cost.",
            fins=FinSet(count=3, root_chord_m=0.062, tip_chord_m=0.031, height_m=0.046,
                        sweep_m=0.030),
        ),
        SimResult(apogee_m=604, stability_margin_cal=1.62, rail_exit_velocity_ms=18.4,
                  max_velocity_ms=139, liftoff_mass_kg=0.129),
    ),
    (
        variant(
            "Sweep", "Shortens the payload bay to shed mass now that stability has margin.",
            body=tubes(0.16, 0.25),
            fins=FinSet(count=3, root_chord_m=0.062, tip_chord_m=0.031, height_m=0.046,
                        sweep_m=0.030),
        ),
        SimResult(apogee_m=641, stability_margin_cal=1.44, rail_exit_velocity_ms=18.9,
                  max_velocity_ms=147, liftoff_mass_kg=0.118),
    ),
    (
        variant(
            "Overshoot", "Adds nose ballast to buy margin back. This overcorrects.",
            body=tubes(0.16, 0.25), nose_ballast_kg=0.022,
            fins=FinSet(count=4, root_chord_m=0.062, tip_chord_m=0.031, height_m=0.046,
                        sweep_m=0.030),
        ),
        SimResult(apogee_m=559, stability_margin_cal=2.71, rail_exit_velocity_ms=17.1,
                  max_velocity_ms=128, liftoff_mass_kg=0.148,
                  warnings=["Over-stable: expect weathercocking in wind"]),
    ),
    (
        variant(
            "Uprated", "Drops most of the ballast and steps up to an F motor for the altitude.",
            body=tubes(0.16, 0.28), nose_ballast_kg=0.006,
            motor=Motor(designation="F44", manufacturer="AeroTech", diameter_mm=29,
                        length_mm=98),
            fins=FinSet(count=4, root_chord_m=0.062, tip_chord_m=0.031, height_m=0.046,
                        sweep_m=0.030),
        ),
        SimResult(apogee_m=795, stability_margin_cal=1.98, rail_exit_velocity_ms=22.7,
                  max_velocity_ms=178, liftoff_mass_kg=0.171),
    ),
    (
        variant(
            "Uprated", "Trims fin height to land inside the target band without losing margin.",
            body=tubes(0.16, 0.28), nose_ballast_kg=0.006,
            motor=Motor(designation="F44", manufacturer="AeroTech", diameter_mm=29,
                        length_mm=98),
            fins=FinSet(count=4, root_chord_m=0.058, tip_chord_m=0.029, height_m=0.040,
                        sweep_m=0.030),
        ),
        SimResult(apogee_m=908, stability_margin_cal=1.81, rail_exit_velocity_ms=23.1,
                  max_velocity_ms=189, liftoff_mass_kg=0.166),
    ),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--no-mesh", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    iterations = []
    for i, (spec, result) in enumerate(RUN, start=1):
        result.backend = "synthetic"
        stem = args.out / f"v{i:02d}"
        write_ork(spec, stem.with_suffix(".ork"))
        if not args.no_mesh:
            build_mesh(spec, stem.with_suffix(".glb"))
            print(f"built v{i}")

        d = diff_specs(RUN[i - 2][0], spec) if i > 1 else None
        iterations.append({
            "index": i,
            "name": spec.name,
            "rationale": spec.rationale,
            "spec": spec.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
            "error": None,
            "glb": None if args.no_mesh else f"v{i:02d}.glb",
            "ork": f"v{i:02d}.ork",
            "changed_parts": d.changed_parts if d else [],
            "changes": [c.human() for c in d.changes] if d else [],
            "review_session_id": f"demo-{i:02d}",
        })

    (args.out / "manifest.json").write_text(
        json.dumps({"goal": GOAL, "iterations": iterations}, indent=2)
    )
    print(f"wrote {args.out}/manifest.json ({len(iterations)} iterations)")


if __name__ == "__main__":
    main()
