# Rocinante

Redesign a torpedo with one request, open the revised engineering file in
OpenRocket, and compare it with its previous version in Kord.

The one-minute demo follows **intent → validated design → OpenRocket →
Kord comparison**. Astra returns a complete `ShipSpec` containing a
`RocketSpec` torpedo. Python validates the design, writes `.ork` files, and
saves a revision. Valid revisions are accepted automatically, and the
comparison is uploaded in the background.

> Unaffiliated fan work. *The Expanse* belongs to its authors and to Alcon.
> No trademarked assets are in this repository.

Kord is a separate, pre-existing product reached over HTTP. The current
presentation focuses on torpedo geometry and motor configuration. The repo
also contains ship refit and computed mission tooling; automated torpedo
flight simulation remains unimplemented.

## How it works

```text
Request → Astra → validated ShipSpec → saved revision
                            │
                            ├─ torpedo → .ork → OpenRocket
                            │              └─ before/after .ork → Kord comparison
                            ├─ ship geometry → Blender → .glb → ship viewer
                            └─ ship inputs → computed mass, Δv and acceleration
```

Torpedo-only edits compare the torpedo files in Kord. Ship geometry edits
use the ship GLB comparison path. The torpedo's detailed dimensions and motor
are not coupled to ship mass or mission performance. A longer drive cone
alone changes geometry without changing thrust or exhaust velocity.

| Piece | What it does |
|---|---|
| `ship.py` | Validated ship inputs and computed engineering quantities. |
| `spec.py` | Torpedo design schema: nose, body, fins, motor and recovery. |
| `agent/refit.py` | A structured model proposal from a request. |
| `workbench.py` | Persistent revisions, diffs, demo acceptance and tool handoff. |
| `ork/` | OpenRocket `.ork` export and partial geometry import. |
| `blend/` | Parametric mesh generation and GLB export. |
| `diff.py` | Structured input changes and affected ship parts. |
| `flight/` | Closed-form constant-acceleration transfer calculations. |
| `sim/` | OpenRocket and RocketPy backend stubs. |
| `kord/` | HTTP client for comparisons and separate review APIs. |
| `web/` | Ship scene, torpedo workshop, revision details and propagation status. |

## Setup

Install Python 3.11+, `uv`, Blender, and the OpenRocket desktop application.
The full presentation uses macOS window placement. Then:

```bash
uv sync --extra dev
cp .env.example .env   # first setup only; preserve an existing .env
# Set OPENAI_API_KEY and the intended KORD_API_BASE in .env.
bin/roci demo --live --out out/demo-minute
```

`bin/roci` loads `.env` and runs in the project environment. Optionally
symlink it onto your PATH as `roci`. A bare installed entry point does not
load `.env`; use `uv run --env-file .env rocinante demo` when bypassing the
wrapper. `ROCINANTE_MODEL` defaults to `gpt-6-astra`. `--live` requires a key;
omitting it selects live mode when a key is present and fixtures otherwise.

The demo serves port 3001 and opens four windows:

```text
web UI   | OpenRocket
---------+-----------
Blender  | Kord
```

Stop it with Ctrl-C in its terminal, or use `bin/roci kill` if it was detached.
For a demo started with a custom port, pass the same port to `kill --port`.

A torpedo request updates the design file in OpenRocket and automatically
shares the previous/revised `.ork` pair with Kord. The Kord browser follows
the saved comparison link. Select the target torpedo first in builds that
expose individual torpedo selection. Use the prompt in [DEMO.md](DEMO.md)
for the one-minute presentation.

The Kord destination is `--kord`, then `KORD_API_BASE`, then
`https://work.withkord.com`. When using local Kord, start its supporting
services and `pnpm dev` in that checkout first; this command does not start
Kord. Anonymous comparison sharing needs no Kord login. It does not create
an authenticated review verdict or post a rationale comment.

Set `BLENDER_BIN` if Blender is installed elsewhere. The viewer loads
Three.js from jsDelivr. Tiling needs Automation access to Chrome and System
Events. `--no-layout`, `--no-chrome`, `--no-blender`, `--no-openrocket`, and
`--no-share` control the presentation. `--no-blender` disables the desktop
window; automatic mesh export still requires Blender.

For deterministic rehearsal without a model key:

```bash
bin/roci demo --fixture --out out/demo-minute-fixture
```

Fixtures are labeled presets, not model responses. Use a fresh output
directory for each baseline rehearsal; reuse the directory to resume its
saved history. Default state lives in `out/workbench/workbench.json`.
Generated torpedo files live under `<out>/torpedo/`, with ship exports and
comparison reports under `<out>/exports/`. Model failures preserve the
accepted design. Export/share failures may follow automatic acceptance;
inspect the propagation status and use a prepared comparison for recovery.

[DEMO.md](DEMO.md) contains the one-shot request, sixty-second script,
expected baseline changes, and fallback preparation. The combined request
still requires a timed live rehearsal.

## Other tooling

```bash
uv run rocinante ship                         # baseline ship calculations
uv run rocinante burn Tycho Ceres --accel 0.333 # fixed-acceleration transfer
uv run rocinante ship-mesh -o out/roci.glb      # generate the ship mesh
uv run rocinante sample                       # write a sample torpedo
uv run --env-file .env rocinante share a.glb b.glb
```

The separate `refit` command supports ship proposals and GLB comparisons.
It is not the one-minute torpedo script. `simulate` cannot provide real
flight results while the backends remain stubs. Installing optional
`openrocket` or `rocketpy` dependencies does not implement those backends.
The local `.ork` reader imports geometry but currently defaults motor and
recovery settings; use the saved JSON spec to preserve a complete design.

`scripts/fake_run.py` produces explicitly synthetic flight data for the
standalone viewer; its numbers are hand-authored. Current ship endurance is
a conservative initial-wet-mass estimate. Tank/magazine packaging,
variable-mass mission solving, and combat simulation are not demonstrated.

## What was built when

This project was started the evening before the GPT-6 Astra hackathon and
continued during it. The build boundary is recorded here so judges can distinguish prior work
from additions made during the event.

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
  labeled fixtures, automatic demo acceptance and sharing, OpenRocket file
  handoff, torpedo editing, and computed ship/mission panels.

**Kord itself is a separate, pre-existing product**, reached over HTTP. No
part of this project required a change to it — see [DEMO.md](DEMO.md) for the current
anonymous comparison workflow. Authenticated review remains separate scope.

Still stubbed: both torpedo simulator backends.

## Tests

```bash
uv run pytest
```

## License

MIT
