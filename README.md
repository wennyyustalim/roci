# Rocinante

A spacecraft you can redesign and then fly.

Rocinante models the ship it is named for as a versioned engineering
document. Change the ship — lengthen the drive cone, trade a torpedo tube for
magazine volume — and you get two things back: a 3D diff showing exactly what
moved, and the flight consequences of having moved it. Then you take the
result out and fly it.

> Unaffiliated fan work. *The Expanse* belongs to its authors and to Alcon.
> No trademarked assets are in this repository.

This repo is a client. The version control platform it files revisions into is
a separate, pre-existing product, reached over HTTP.

## Why

An engineering file is a binary blob. Version control sees that it changed and
can tell you nothing else, so the loop that actually matters — propose,
simulate, review, revise — happens by hand, in email, with screenshots.

Rocinante closes that loop and attaches consequences to it. A change is not a
diff of bytes; it is *the drive cone grew 4 m, Δv went up 87 km/s, and max
acceleration dropped 0.7 g* — with the changed section glowing red against a
ghost of the hull it replaced.

## How it works

```
ShipSpec ──▶ Blender ──▶ .glb ──▶ 3D diff ──▶ version + review
    │                                              │
    ├──▶ derived: Δv, mass, accel ─────────────────┘
    │
    └──▶ flight sim ──▶ brachistochrone, combat, crew
             │
             └──▶ torpedoes: .ork ──▶ OpenRocket
```

The Roci flies Newtonian — constant thrust, flip at the midpoint, decelerate
in. Its **torpedoes** are the model rockets, and those go through OpenRocket
for real thrust curves and burn times.

| Piece | What it does |
|---|---|
| `ship.py` | `ShipSpec` and everything derived from it. The structure Astra emits. |
| `spec.py` | `RocketSpec` — the torpedo. |
| `flight/` | Brachistochrone transfers: burn, flip, decelerate. |
| `agent/refit.py` | One sentence of intent → one structured-output call → one revision. |
| `blend/` | Blender builds geometry and exports glTF. Not a renderer for the loop. |
| `diff.py` | Structured design difference, and which 3D parts it touched. |
| `ork/` | Spec ⇄ OpenRocket `.ork`, for the torpedoes. |
| `sim/` | Torpedo simulation. OpenRocket via JPype, RocketPy as the fallback. |
| `kord/` | The Kord integration: 3D diff links, versions, review sessions. |
| `web/` | The interactive viewer: system map, combat, crew, and the diff. |

Blender is the mesh generator, not the viewer. It does the geometry; the
browser does the interaction. Rendered pixels are for the hero shot.

## Setup

For the end-to-end skeleton, Python is enough:

```bash
uv sync --extra dev
uv run rocinante demo --port 3001
# Open http://127.0.0.1:3001/
```

Choose a fixture refit, inspect the primitive ship comparison and computed
consequences, then approve or reject. Repeat: the next proposal starts from
the last approved design. History survives refreshes and server restarts in
`out/workbench/workbench.json`. Use `--out out/another-run` for a fresh loop.
The 3D viewer needs access to jsDelivr; review and metrics remain usable if
its modules fail to load. No Blender or API key is needed for fixture mode.

`uv run rocinante demo --live` uses the existing model proposal method with
free text. Export `OPENAI_API_KEY` and optionally `ROCINANTE_MODEL` in the
launching shell first (`.env` is not loaded automatically). Live model access
is not verified by the fixture demo. Local decisions do not file or approve
Kord sessions. Download selected specs, then use the existing `ship-mesh
--spec <file>` and `share` commands for that separate handoff.

For Blender exports and the torpedo tooling:

```bash
brew install --cask blender temurin

mkdir -p vendor
curl -L -o vendor/OpenRocket-23.09.jar \
  https://github.com/openrocket/openrocket/releases/download/release-23.09/OpenRocket-23.09.jar

uv venv && source .venv/bin/activate
uv pip install -e '.[openrocket,rocketpy,dev]'

cp .env.example .env
rocinante doctor
```

## Use

```bash
rocinante ship                            # the baseline Roci, and what it implies
rocinante burn Tycho Ceres --accel 0.333  # solve a constant-thrust transfer
rocinante ship-mesh -o out/roci.glb       # regenerate the hull from the spec
rocinante refit "eight more torpedoes"    # the whole loop: ask -> revision
rocinante share a.glb b.glb               # a public Kord 3D diff link

rocinante sample                          # a known-good torpedo
rocinante simulate out/sample.ork         # fly it through OpenRocket
```

`rocinante refit` is the project in one command: it asks GPT-6 Astra for a
revision, regenerates the geometry, computes the consequences, and hands back
a live Kord diff of the two hulls.

`scripts/fake_run.py` writes a synthetic run with hand-authored numbers, so
the viewer can be built and demoed before the systems behind it exist:

```bash
python scripts/fake_run.py --out out && rocinante viewer
```

## What was built when

This project was started the evening before the GPT-6 Astra hackathon and
continued during it. This repository opens with a single commit, so the
boundary is stated here rather than read from history. It is drawn honestly
and deliberately — judges should be able to tell exactly what is ours from
the event.

**Before the event**, on the evening of 7 September: the Blender bridge with
its auto-framed camera, the model-rocket geometry that became the torpedoes
(`blend/build_rocket.py`), the `.ork` container and its round-trip test
(`ork/`), structured spec diffing with per-part mapping (`diff.py`), a first
sketch of the Kord client, and the standalone viewer's ghost-and-highlight
rendering (`web/`).

**During the event**, on 8 September:

- `ship.py` — `ShipSpec` and every derived property: the rocket equation,
  masses, acceleration, torpedo capacity, burn times, the crew g-bound.
- `flight/brachistochrone.py` — the constant-thrust transfer solver.
- `blend/build_ship.py` — the parametric ship generator. The hull is
  generated from the spec, never modelled by hand, which is what lets a refit
  regenerate it in under a second.
- `agent/refit.py` and the ship prompts — the GPT-6 Astra refit: one sentence
  of intent, one structured-output call, one complete revision.
- `kord/client.py` — the Kord integration, rewritten against the real API.
- `tests/test_ship.py` and `tests/test_flight.py` — the physics under test.
- The `ship`, `ship-mesh`, `ship-hero`, `burn`, `refit` and `share` commands.
- `workbench.py`, the `demo` command, `web/loop.*`, `web/primitives.js`, and
  `tests/test_workbench.py` — the persistent local proposal/review skeleton,
  labeled fixtures, primitive comparison and computed ship/mission panels.

**Kord itself is a separate, pre-existing product**, reached over HTTP. No
part of this project required a change to it — see [PLAN.md](PLAN.md) for the
three integration paths and why the anonymous diff-share endpoint is the one
the demo stands on.

Still stubbed: both torpedo simulator backends.

## Tests

```bash
pytest
```

## License

MIT
