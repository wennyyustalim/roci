# The one-minute torpedo demo

The story is **one request → a validated torpedo design → an OpenRocket
update → a Kord comparison of the previous and revised `.ork` files**.
Valid revisions are accepted automatically. The one-minute presentation
focuses on the torpedo; ship refits and approval/rejection are outside its script.

## Start and prepare

Install the project dependencies and have Blender and OpenRocket installed
for the four-window presentation:

```bash
uv sync --extra dev
bin/roci demo --live --out out/demo-minute
```

`bin/roci` loads the repository's `.env`. Set `OPENAI_API_KEY` there;
`ROCINANTE_MODEL` defaults to `gpt-6-astra`. `roci` can be a symlink to
`bin/roci`. A bare installed `rocinante`/`roci` command needs configuration
in its environment or an explicit `uv run --env-file .env` launch.
Without `--live`, the demo uses live mode when a key is set and fixtures
otherwise. `--live` fails early if the key is missing.

The command serves http://127.0.0.1:3001/ and opens four windows:

```
web UI   | OpenRocket
---------+-----------
Blender  | Kord
```

Comparisons go to `--kord`, then `KORD_API_BASE`, then the public default
`https://work.withkord.com`. For local Kord, start its supporting services
and run `pnpm dev` in that checkout before starting the demo. The demo
reports an unreachable Kord instance but does not start it.
The Kord window begins at `/diff` or a saved comparison and follows each
new shared revision.

Set `BLENDER_BIN` for a nonstandard Blender installation. The browser viewer
loads Three.js from jsDelivr. Window tiling needs the launching terminal's
Automation access to Chrome and System Events. `--no-layout`, `--no-chrome`,
`--no-blender`, `--no-openrocket`, and `--no-share` disable those features;
`--no-blender` disables the Blender window, not automatic mesh export.

Use an unused `--out` directory for a fresh baseline. Stop the previous
server before reusing port 3001, or supply another `--port`. Existing state
is resumed rather than reset. If the UI supports selecting an individual
loaded torpedo, select it before submitting the request and confirm the
workshop targets that torpedo.

## One-shot request

Paste this before the clock starts, then submit once:

> Redesign only the selected torpedo in one revision. Set the ogive nose length to 15 cm; use four swept fins with 8 cm root chord, 4 cm tip chord, 7 cm semi-span and 4 cm sweep. Set the booster tube length to 30 cm. Set both body tubes to 35 mm outside diameter and the nose base to the same diameter. Use an Estes F15 motor, 29 mm diameter and 114 mm length, with a 6-second delay. Keep the payload tube length, wall thicknesses, materials, recovery, ballast and all other inputs unchanged, including the entire ship. Summarize the changes in one sentence; do not claim simulated flight performance.

The motor dimensions and delay match the manufacturer's
[Estes F15-6 specifications](https://edu.estesrockets.com/products/f15-6-engines).
The wider body accommodates the generated motor mount in the design file.
This is a proposed software-demo configuration; flight performance has not
been established. Exact target dimensions make repeats predictable, but
repeat on a fresh baseline to show the full difference.

Expected changes from the checked-in `baseline_torpedo()` are:

| Detail | Before | Requested after |
|---|---|---|
| Nose length | 10 cm | 15 cm |
| Fin count | 3 | 4 |
| Fin root / tip chord | 6 / 3 cm | 8 / 4 cm |
| Fin semi-span / sweep | 4.5 / 3 cm | 7 / 4 cm |
| Booster length | 25 cm | 30 cm |
| Body / nose-base diameter | 25 mm | 35 mm |
| Motor | Estes E12, 24 × 70 mm | Estes F15, 29 × 114 mm |
| Total length | 55 cm | 65 cm |

These are requested values, not a recorded Astra result. The combined prompt
has not yet been rehearsed live. The earlier fins-only live run documented
in PLAN.md took 29.4 seconds; allow additional time for export and upload.

## Sixty-second script

- **0:00–0:05:** Submit. “Redesign this torpedo: longer nose, four larger fins,
  wider body, and a new motor—all in one request.”
- **0:05–0:25:** While Astra works: “Astra returns a structured engineering
  design. Our code validates it and writes the OpenRocket file.”
- **0:25–0:40:** When ready, show OpenRocket. “Here is the revised torpedo.”
  Point out the longer nose and larger fin set, then the motor configuration.
- **0:40–0:55:** Show Kord's comparison and Changes list. “The previous and
  revised engineering files are compared automatically. You can inspect
  every changed dimension.” Give the comparison a quiet moment on screen.
- **0:55–1:00:** “One request, one saved revision, updated across the tools.”

The times are a rehearsal budget, not measured end-to-end latency. Rehearse
this exact request once before recording; verify all requested values, motor
resolution in OpenRocket, unchanged ship inputs, and the correct `.ork`
comparison. Narrate only what the actual result shows. In a narrow quadrant,
use Kord's Changes list; drawing annotations can clip their after-values.

## Fallback and restart

Prepare a saved real run and preload its Kord comparison before presenting.
If the live result is not ready by about 0:35, say “Here is the result from
our rehearsal” and show that saved result. Do not try a second model request
inside the minute. Wait for sharing to finish before submitting another ask;
network work can currently hold the workbench lock.

Create a separate deterministic fallback in advance:

```bash
bin/roci demo --fixture --out out/demo-minute-fixture
```

Fixture presets cover individual changes, not the complete one-shot prompt.
Label them as fixtures. These paths are preparation commands, not claims that
saved runs already exist in this checkout.

Restart a prepared run with the same mode and `--out` directory. State is
saved in `<out>/workbench.json`; torpedo files are in `<out>/torpedo/` and
ship exports/reports in `<out>/exports/`. Check the saved comparison actually
loads. Local links require the local Kord service; public shares expire
according to their saved `expires_at`. A saved link is reused on restart.

Model failures leave the accepted design intact. Export or upload failures
can occur after automatic acceptance: inspect the propagation status and
server logs, and switch to the prepared comparison for the presentation.
Do not delete the run directory to recover. An upload retry can create an
additional link if the first upload reached Kord. If OpenRocket becomes
unresponsive, quit it cleanly and reopen the saved torpedo file.
Resume from the saved workbench JSON; this project's partial `.ork` importer
does not preserve motor or recovery settings.

## Accurate narration

- The demo writes real `.ork` designs and opens them in OpenRocket. This
  project's OpenRocket and RocketPy simulation backends are stubs; no
  automated flight, altitude, burn-time or stability improvement is proven.
- The ship's mass and mission metrics are not coupled to this torpedo's
  detailed geometry or motor. Do not narrate a ship-performance gain.
- Torpedo-only edits share `.ork` files. The ship GLBs shown by Blender and
  the local ship viewer are a separate output; they are not the torpedo diff.
- The progress tracker reports propagation stages, not a continuous morph.
- Kord is a separate, pre-existing product. Anonymous comparisons do not
  create authenticated review verdicts or post rationale comments.
- This is unaffiliated fan work using generated geometry. See README.md
  for the before/during-event build boundary.
