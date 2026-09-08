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

DEFAULT_MODEL = "gpt-6-astra"


def model_name() -> str:
    """The API model, with blank shell/.env values treated as unset."""
    return os.getenv("ROCINANTE_MODEL", "").strip() or DEFAULT_MODEL


class RefitModelError(RuntimeError):
    """A live proposal failed without changing the current design."""


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
    client: object | None = field(default=None, repr=False)

    def propose(self, ship: ShipSpec, ask: str) -> ShipSpec:
        """Ask Astra for the next revision of this ship.

        Structured output against ShipSpec's JSON schema makes malformed output
        unlikely. Refusals, interrupted responses, and custom Pydantic validators
        can still fail, so those paths become explicit errors without a revision.
        """
        from openai import OpenAI, OpenAIError
        from pydantic import ValidationError

        ask = ask.strip()
        if not ask:
            raise ValueError("A refit request cannot be empty")

        selected_model = model_name()
        client = self.client
        if client is None and not os.getenv("OPENAI_API_KEY", "").strip():
            raise RefitModelError(
                f"{selected_model}: live refit needs OPENAI_API_KEY"
            )
        owns_client = client is None
        try:
            client = client or OpenAI(timeout=90.0, max_retries=1)
            response = client.responses.parse(
                model=selected_model,
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
                store=False,
            )
        except OpenAIError as exc:
            raise RefitModelError(_api_failure(selected_model, exc)) from exc
        except ValidationError as exc:
            raise RefitModelError(
                f"{selected_model} returned a ShipSpec that failed domain validation"
            ) from exc
        finally:
            if owns_client and client is not None:
                client.close()

        proposed = response.output_parsed
        if proposed is None:
            raise RefitModelError(_unparsed_failure(selected_model, response))
        if not proposed.rationale.strip():
            raise RefitModelError(f"{selected_model} returned a ShipSpec without a rationale")
        before = ship.model_dump(exclude={"rationale"})
        after = proposed.model_dump(exclude={"rationale"})
        if before == after:
            raise RefitModelError(f"{selected_model} returned a no-op ShipSpec")
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
            # Uploading the new hull IS the proposal: Kord opens the review
            # session on the changed bytes and hands the id straight back.
            uploaded = kord.upload_version(result.after_glb, note=result.after.rationale)
            result.review_session_id = kord.review_session_id_from(uploaded)
            if result.review_session_id:
                kord.comment(result.review_session_id, result.review_body())
        return result


def _derived_block(ship: ShipSpec) -> str:
    return "\n".join(f"  {k}: {v:,.2f}" for k, v in ship.derived().items())


def _api_failure(selected_model: str, exc: Exception) -> str:
    """Turn SDK failures into short, actionable demo errors without response dumps."""
    name = type(exc).__name__
    if name == "AuthenticationError":
        detail = "authentication failed; set a valid OPENAI_API_KEY"
    elif name in {"PermissionDeniedError", "NotFoundError"}:
        detail = "the API key cannot access that model"
    elif name == "RateLimitError":
        detail = "the API rate limit or spending limit was reached"
    elif name in {"APIConnectionError", "APITimeoutError"}:
        detail = "the API could not be reached before the timeout"
    elif name == "BadRequestError":
        detail = "the API rejected the model or structured-output request"
    else:
        detail = "the API request failed"
    return f"{selected_model}: {detail} ({name})"


def _unparsed_failure(selected_model: str, response: object) -> str:
    """Explain refusals and incomplete responses while keeping raw output private."""
    for item in getattr(response, "output", ()) or ():
        for content in getattr(item, "content", ()) or ():
            if getattr(content, "type", None) == "refusal":
                return f"{selected_model} refused the refit request"

    incomplete = getattr(response, "incomplete_details", None)
    reason = getattr(incomplete, "reason", None)
    if reason:
        return f"{selected_model} returned an incomplete ShipSpec ({reason})"

    status = getattr(response, "status", None)
    suffix = f" (response status: {status})" if status else ""
    return f"{selected_model} returned no parsable ShipSpec{suffix}"
