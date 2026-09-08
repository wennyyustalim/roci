"""The design loop: propose -> simulate -> file a version -> revise.

STATUS: the loop is wired end to end and the model call is a stub. Fill in
`propose()` on the day; everything around it already runs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from rocinante.agent import prompts
from rocinante.blend import build_mesh
from rocinante.diff import SpecDiff, diff_results, diff_specs
from rocinante.kord import KordClient
from rocinante.ork import write_ork
from rocinante.sim import SimResult, get_simulator
from rocinante.sim.base import SimulationError
from rocinante.spec import RocketSpec


@dataclass
class DesignGoal:
    text: str
    target_apogee_m: float | None = None
    min_stability_cal: float = 1.5
    max_stability_cal: float = 2.5
    apogee_tolerance: float = 0.05

    def satisfied_by(self, r: SimResult) -> bool:
        if not self.min_stability_cal <= r.stability_margin_cal <= self.max_stability_cal:
            return False
        if self.target_apogee_m is None:
            return True
        error = abs(r.apogee_m - self.target_apogee_m) / self.target_apogee_m
        return error <= self.apogee_tolerance


@dataclass
class Iteration:
    index: int
    spec: RocketSpec
    result: SimResult | None = None
    error: str | None = None
    diff: SpecDiff | None = None
    ork_path: Path | None = None
    glb_path: Path | None = None
    review_session_id: str | None = None


@dataclass
class DesignLoop:
    goal: DesignGoal
    out_dir: Path = Path("out")
    max_iterations: int = 12
    sim_backend: str | None = None
    kord: KordClient = field(default_factory=KordClient)
    build_meshes: bool = True
    require_approval: bool = False
    history: list[Iteration] = field(default_factory=list)

    # --- the model ------------------------------------------------------

    def propose(self, previous: Iteration | None) -> RocketSpec:
        """Ask the model for the next design.

        TODO on the day: one structured-output call against RocketSpec's JSON
        schema. Do not let it emit free text -- parse failures cost iterations,
        and iterations are the demo.

            from openai import OpenAI
            client = OpenAI()
            resp = client.responses.parse(
                model=os.getenv("ROCINANTE_MODEL", "gpt-6-astra"),
                input=[{"role": "system", "content": prompts.SYSTEM},
                       {"role": "user", "content": user_prompt}],
                text_format=RocketSpec,
            )
            return resp.output_parsed
        """
        if previous is None:
            _ = prompts.FIRST.format(goal=self.goal.text)
        else:
            _ = prompts.ITERATION.format(
                goal=self.goal.text,
                spec=previous.spec.model_dump_json(indent=2, exclude={"rationale"}),
                result=previous.result.summary() if previous.result else previous.error,
                history=self._history_digest(),
            )
        raise NotImplementedError("wire the model call")

    def _history_digest(self, limit: int = 6) -> str:
        rows = [
            f"  #{i.index}: {i.result.summary() if i.result else i.error} -- {i.spec.rationale}"
            for i in self.history[-limit:]
        ]
        return "Iterations so far:\n" + "\n".join(rows) if rows else ""

    # --- one turn -------------------------------------------------------

    def step(self, index: int) -> Iteration:
        previous = self.history[-1] if self.history else None
        spec = self.propose(previous)
        it = Iteration(index=index, spec=spec)

        stem = self.out_dir / f"v{index:02d}"
        it.ork_path = write_ork(spec, stem.with_suffix(".ork"))
        if self.build_meshes:
            it.glb_path = build_mesh(spec, stem.with_suffix(".glb"))

        try:
            it.result = get_simulator(self.sim_backend).run(spec)
        except SimulationError as exc:
            it.error = str(exc)

        if previous is not None:
            it.diff = diff_specs(previous.spec, spec)

        self._file_with_kord(it, previous)
        self.history.append(it)
        self._write_manifest()
        return it

    def _file_with_kord(self, it: Iteration, previous: Iteration | None) -> None:
        if not self.kord.enabled or it.ork_path is None:
            return
        uploaded = self.kord.upload_version(it.ork_path, note=it.spec.rationale)
        file_id = uploaded.get("file_id") or uploaded.get("id")

        body = [f"**{it.spec.rationale}**", ""]
        if it.result:
            body.append(it.result.summary())
        if it.error:
            body.append(f"Simulation failed: {it.error}")
        if previous and previous.result and it.result:
            body.append("")
            body.append(diff_results(previous.result, it.result))
        if it.diff:
            body += ["", "**Geometry**", it.diff.markdown()]

        session = self.kord.open_review_session(
            title=f"{it.spec.name} v{it.index}",
            description=it.spec.rationale,
            file_ids=[file_id] if file_id else [],
        )
        it.review_session_id = session.get("id")
        self.kord.comment(it.review_session_id or "", "\n".join(body))

    def _write_manifest(self) -> None:
        """out/manifest.json is what the web viewer reads. Keep it flat."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "goal": self.goal.text,
            "iterations": [
                {
                    "index": i.index,
                    "name": i.spec.name,
                    "rationale": i.spec.rationale,
                    "spec": i.spec.model_dump(mode="json"),
                    "result": i.result.model_dump(mode="json") if i.result else None,
                    "error": i.error,
                    "glb": i.glb_path.name if i.glb_path else None,
                    "ork": i.ork_path.name if i.ork_path else None,
                    "changed_parts": i.diff.changed_parts if i.diff else [],
                    "changes": [c.human() for c in i.diff.changes] if i.diff else [],
                    "review_session_id": i.review_session_id,
                }
                for i in self.history
            ],
        }
        (self.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # --- the run --------------------------------------------------------

    def run(self, on_iteration=None) -> list[Iteration]:
        for index in range(1, self.max_iterations + 1):
            it = self.step(index)
            if on_iteration:
                on_iteration(it)
            if self.require_approval and self.kord.verdict(it.review_session_id or "") == "rejected":
                continue
            if it.result and self.goal.satisfied_by(it.result):
                break
        return self.history


def model_name() -> str:
    return os.getenv("ROCINANTE_MODEL", "gpt-6-astra")
