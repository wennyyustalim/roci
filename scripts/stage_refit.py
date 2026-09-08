"""Run one explicit, provenance-rich live refit for stage rehearsal.

This command never uploads or shares anything. A paid model call only happens
when both ``--run-live`` and ``--model`` are supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from math import isclose
from pathlib import Path

from rocinante.agent import prompts
from rocinante.agent.refit import RefitAgent
from rocinante.diff import diff_ships, ship_geometry_parts
from rocinante.samples import ROCINANTE

STAGE_ASK = (
    "Carry eight more torpedoes by adding two launch tubes and six magazine slots, "
    "without losing cruise burn time. Keep other design inputs unchanged except the "
    "propellant needed to preserve endurance."
)
EXPECTED_INPUT_CHANGES = {
    "drive.propellant_t",
    "weapons.magazine_m3",
    "weapons.torpedo_tubes",
}


def _user_prompt() -> str:
    derived = "\n".join(f"  {key}: {value:,.2f}" for key, value in ROCINANTE.derived().items())
    return prompts.REFIT.format(
        ask=STAGE_ASK,
        spec=ROCINANTE.model_dump_json(indent=2, exclude={"rationale"}),
        derived=derived,
    )


def _write_text(path: Path, value: str) -> None:
    path.write_text(value if value.endswith("\n") else value + "\n")


def _checks(after) -> tuple[dict[str, bool], dict[str, float]]:
    before = ROCINANTE
    diff = diff_ships(before, after)
    paths = {change.path for change in diff.changes}
    expected_propellant = before.drive.propellant_t * after.dry_mass_t / before.dry_mass_t
    expected_dry_delta = 8 * before.weapons.torpedo_mass_t
    magazine_slot_delta = (
        after.weapons.magazine_m3 - before.weapons.magazine_m3
    ) / before.weapons.torpedo_volume_m3

    measurements = {
        "tube_delta": after.weapons.torpedo_tubes - before.weapons.torpedo_tubes,
        "magazine_slot_delta": magazine_slot_delta,
        "capacity_delta": after.weapons.torpedo_capacity - before.weapons.torpedo_capacity,
        "dry_mass_delta_t": after.dry_mass_t - before.dry_mass_t,
        "expected_dry_mass_delta_t": expected_dry_delta,
        "propellant_delta_t": after.drive.propellant_t - before.drive.propellant_t,
        "expected_propellant_t": expected_propellant,
        "sustained_burn_delta_hours": after.sustained_burn_hours - before.sustained_burn_hours,
        "sustained_burn_delta_seconds": (after.sustained_burn_hours - before.sustained_burn_hours)
        * 3600,
        "propellant_rounding_t": after.drive.propellant_t - expected_propellant,
        "delta_v_delta_km_s": after.delta_v_km_s - before.delta_v_km_s,
        "max_accel_delta_g": after.max_accel_g - before.max_accel_g,
    }
    checks = {
        "added_exactly_two_tubes": measurements["tube_delta"] == 2,
        "added_exactly_six_magazine_slots": isclose(magazine_slot_delta, 6.0, abs_tol=1e-9),
        "added_exactly_eight_total_capacity": measurements["capacity_delta"] == 8,
        "dry_mass_matches_eight_torpedoes": isclose(
            measurements["dry_mass_delta_t"], expected_dry_delta, abs_tol=1e-9
        ),
        # Structured numeric output commonly rounds fuel to two decimals. One
        # second is far below the display precision and still proves no
        # meaningful endurance loss; the direction check enforces "without
        # losing" rather than accepting a symmetric shortfall.
        "cruise_endurance_preserved": (
            -1e-9 <= after.sustained_burn_hours - before.sustained_burn_hours <= 1 / 3600
        ),
        "propellant_is_exact_preservation_amount": isclose(
            after.drive.propellant_t,
            expected_propellant,
            rel_tol=1e-5,
            abs_tol=0.01,
        ),
        "only_requested_inputs_changed": paths == EXPECTED_INPUT_CHANGES,
        "tube_change_maps_to_visible_geometry": ship_geometry_parts(before, after) == ["tube_*"],
    }
    return checks, measurements


def _markdown(report: dict) -> str:
    before = report["before_derived"]
    after = report["after_derived"]
    lines = [
        "# Stage refit verification",
        "",
        f"- Status: **{report['status'].upper()}**",
        f"- Model: `{report['model']}`",
        f"- Model latency: {report['latency_seconds']:.3f} seconds",
        f"- Ask: {report['ask']}",
        f"- Rationale: {report['rationale']}",
        "",
        "## Acceptance checks",
        "",
    ]
    for name, passed in report["checks"].items():
        lines.append(f"- [{'x' if passed else ' '}] {name.replace('_', ' ')}")
    lines += [
        "",
        "## Input changes",
        "",
        "| Field | Before | After | Change | Affected assembly |",
        "|---|---:|---:|---:|---|",
    ]
    for change in report["input_changes"]:
        delta = change["after"] - change["before"]
        lines.append(
            f"| `{change['path']}` | {change['before']:.9g} | {change['after']:.9g} | "
            f"{delta:+.9g} | `{change['part'] or ''}` |"
        )
    lines += [
        "",
        "## Computed consequences",
        "",
        "| Quantity | Before | After | Change |",
        "|---|---:|---:|---:|",
    ]
    for key in before:
        lines.append(
            f"| {key.replace('_', ' ')} | {before[key]:,.9g} | {after[key]:,.9g} | "
            f"{after[key] - before[key]:+,.9g} |"
        )
    lines += [
        "",
        "## Scope note",
        "",
        (
            "The visible geometry check proves the changed input maps to the generated `tube_*` "
            "assembly. Fuel affects the drive assembly and computed performance without changing "
            "drive geometry. Visual inspection of exported GLBs is a separate integration check."
        ),
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-live", action="store_true", help="Authorize exactly one paid model call."
    )
    parser.add_argument(
        "--model", help="Explicit model ID for the call; no implicit default is accepted."
    )
    parser.add_argument("--out", type=Path, default=Path("out/stage-refit-v2"))
    args = parser.parse_args()

    if not args.run_live or not args.model:
        parser.error("a live run requires both --run-live and --model MODEL")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        parser.error("OPENAI_API_KEY is not configured")
    if args.out.exists() and any(args.out.iterdir()):
        parser.error(f"refusing to overwrite non-empty evidence directory: {args.out}")

    args.out.mkdir(parents=True, exist_ok=True)
    os.environ["ROCINANTE_MODEL"] = args.model
    user_prompt = _user_prompt()
    started_at = datetime.now(UTC)

    _write_text(args.out / "ask.txt", STAGE_ASK)
    # Preserve the exact strings passed to the API; do not add presentation
    # newlines that would make the recorded hashes disagree with the files.
    (args.out / "system-prompt.txt").write_text(prompts.SHIP_SYSTEM)
    (args.out / "user-prompt.txt").write_text(user_prompt)
    _write_text(args.out / "before.json", ROCINANTE.model_dump_json(indent=2))

    started = time.perf_counter()
    try:
        after = RefitAgent(build_meshes=False).propose(ROCINANTE, STAGE_ASK)
    except Exception as exc:
        latency = time.perf_counter() - started
        failure = {
            "status": "error",
            "model": args.model,
            "ask": STAGE_ASK,
            "started_at": started_at.isoformat(),
            "latency_seconds": latency,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "model_call_count": 1,
            "shared_or_uploaded": False,
        }
        _write_text(args.out / "report.json", json.dumps(failure, indent=2))
        raise
    latency = time.perf_counter() - started

    diff = diff_ships(ROCINANTE, after)
    checks, measurements = _checks(after)
    report = {
        "status": "pass" if all(checks.values()) else "fail",
        "model": args.model,
        "ask": STAGE_ASK,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "latency_seconds": latency,
        "model_call_count": 1,
        "shared_or_uploaded": False,
        "rationale": after.rationale,
        "prompt_sha256": {
            "system": hashlib.sha256(prompts.SHIP_SYSTEM.encode()).hexdigest(),
            "user": hashlib.sha256(user_prompt.encode()).hexdigest(),
        },
        "checks": checks,
        "measurements": measurements,
        "affected_assemblies": diff.changed_parts,
        "geometry_changed_parts": ship_geometry_parts(ROCINANTE, after),
        "input_changes": [change.model_dump(mode="json") for change in diff.changes],
        "before_derived": ROCINANTE.derived(),
        "after_derived": after.derived(),
    }
    _write_text(args.out / "after.json", after.model_dump_json(indent=2))
    _write_text(args.out / "report.json", json.dumps(report, indent=2))
    _write_text(args.out / "report.md", _markdown(report))
    print(f"{report['status'].upper()}: {args.out / 'report.md'}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
