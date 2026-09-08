"""The refit: one sentence of intent in, a reviewable engineering revision out.

This is the centre of the project and half of the judging rubric, so read the
shape before you change it.

    "give me eight more torpedoes without losing burn time"
        -> Astra returns a COMPLETE ShipSpec (structured output, not prose)
        -> Blender regenerates the hull from it
        -> the derived properties recompute themselves
        -> Kord diffs the two .glb hulls in 3D
        -> the rationale becomes the review comment a human approves

The model never writes geometry, never writes XML, and never states a number
it could get wrong: every consequence in `RefitResult.deltas` is computed from
the spec it returned, by ship.py. That separation is the technical argument -
the model proposes, the physics reviews, the human approves.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from rocinante.agent import prompts
from rocinante.diff import SpecDiff, diff_ships
from rocinante.ship import ShipSpec


def model_name() -> str:
    return os.getenv("ROCINANTE_MODEL", "gpt-6-astra")


@dataclass
class RefitResult:
    """One revision, and everything a reviewer needs to judge it."""

    ask: str
    before: ShipSpec
    after: ShipSpec
    diff: SpecDiff
    before_glb: Path | None = None
    after_glb: Path | None = None
    share_url: str | None = None
    review_session_id: str | None = None

    @property
    def deltas(self) -> dict[str, tuple[float, float]]:
        """The panel under the 3D diff. Computed, never quoted by the model."""
        a, b = self.before.derived(), self.after.derived()
        return {k: (a[k], b[k]) for k in a if abs(a[k] - b[k]) > 1e-9}

    def deltas_markdown(self) -> str:
        rows = ["| | before | after | change |", "|---|---:|---:|---:|"]
        for key, (old, new) in self.deltas.items():
            rows.append(
                f"| {key.replace('_', ' ')} | {old:,.1f} | {new:,.1f} | {new - old:+,.1f} |"
            )
        return "\n".join(rows) if self.deltas else "_No derived property moved._"

    def review_body(self) -> str:
        """What gets posted to the Kord review session."""
        parts = [
            f"**Ask:** {self.ask}",
            "",
            f"**{model_name()}:** {self.after.rationale}",
            "",
            "**Consequences**",
            self.deltas_markdown(),
            "",
            "**Spec changes**",
            self.diff.markdown(),
        ]
        if self.share_url:
            parts += ["", f"**3D diff:** {self.share_url}"]
        return "\n".join(parts)


@dataclass
class RefitAgent:
    """Wraps one structured-output call. Deliberately not a loop.

    The old `agent/loop.py` iterated until a simulated rocket hit a target.
    A refit is the opposite shape: one proposal, then a human. Keep it that
    way -- an autonomous loop has nothing for a reviewer to review.
    """

    out_dir: Path = Path("out")
    build_meshes: bool = True
    history: list[RefitResult] = field(default_factory=list)

    def propose(self, ship: ShipSpec, ask: str) -> ShipSpec:
        """Ask Astra for the next revision of this ship.

        Structured output against ShipSpec's JSON schema, so a parse failure
        is impossible rather than merely unlikely. Never let it emit free text:
        every retry costs demo seconds, and the schema is the contract.
        """
        from openai import OpenAI

        client = OpenAI()
        response = client.responses.parse(
            model=model_name(),
            input=[
                {"role": "system", "content": prompts.SHIP_SYSTEM},
                {
                    "role": "user",
                    "content": prompts.REFIT.format(
                        ask=ask,
                        spec=ship.model_dump_json(indent=2, exclude={"rationale"}),
                        derived=_derived_block(ship),
                    ),
                },
            ],
            text_format=ShipSpec,
        )
        proposed = response.output_parsed
        if proposed is None:
            raise RuntimeError("model returned no parsable ShipSpec")
        return proposed

    def refit(self, ship: ShipSpec, ask: str, index: int = 1) -> RefitResult:
        """The whole beat: propose, regenerate, diff, and stage for review."""
        after = self.propose(ship, ask)
        result = RefitResult(ask=ask, before=ship, after=after, diff=diff_ships(ship, after))

        if self.build_meshes:
            from rocinante.blend import build_ship_mesh

            self.out_dir.mkdir(parents=True, exist_ok=True)
            result.before_glb = build_ship_mesh(ship, self.out_dir / f"ship_v{index:02d}a.glb")
            result.after_glb = build_ship_mesh(after, self.out_dir / f"ship_v{index:02d}b.glb")

        self.history.append(result)
        return result

    def file_with_kord(self, result: RefitResult, kord=None) -> RefitResult:
        """Hand the revision to Kord: a 3D diff link, and a review session.

        The diff link is anonymous and always works. The review session needs
        an allowlisted account (see kord/client.py) and is skipped without one,
        so this never blocks the demo.
        """
        from rocinante.kord import KordClient

        kord = kord or KordClient()
        if result.before_glb and result.after_glb and kord.can_share:
            share = kord.share_diff(
                result.before_glb,
                result.after_glb,
                title=f"{result.after.name}: {result.ask}",
            )
            result.share_url = share.get("url")

        if kord.enabled and result.after_glb:
            uploaded = kord.upload_version(result.after_glb, note=result.after.rationale)
            file_id = uploaded.get("file_id") or uploaded.get("id") or ""
            session = kord.open_review_session(file_id)
            result.review_session_id = session.get("id")
            if result.review_session_id:
                kord.comment(result.review_session_id, result.review_body())
        return result


def _derived_block(ship: ShipSpec) -> str:
    return "\n".join(f"  {k}: {v:,.2f}" for k, v in ship.derived().items())
