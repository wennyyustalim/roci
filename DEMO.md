# The end-to-end demo

The demo spine is **intent → validated ShipSpec → computed consequences →
Blender geometry comparison → human decision → next proposal**. Kord hosts a
public comparison of the exported pair; approval and rationale remain in the
local workbench. Authenticated Kord review sessions are a later milestone.

## Verified live run in this checkout

The live Astra workbench is running at http://127.0.0.1:3001/ with saved state
in `out/demo-stage-v2`. It contains a real `gpt-6-astra` two-tube refit (v1),
pending review, with the updated faceted hull and exported Blender geometry.
The local viewer shows the two added tubes in orange and the fuel-affected
drive in blue. Server restart preserved the proposal and shared comparison.
The earlier approve/reject/next-proposal rehearsal remains in `out/demo-astra`.

[Open the real Astra comparison](https://work.withkord.com/d/m51IXPuSIMKfRnoA-X2FyhiW)
(expires 15 September 2026 at 19:27 UTC). The fixture fallback remains saved
separately in `out/demo-fixture`.

Restart this checkout's verified run:

```bash
roci demo --out out/demo-stage-v2
```

Use a new output directory for a fresh live rehearsal. The saved pending v1
requires approval or rejection before a new request; the status banner says so.

## Start

One command. It loads `.env`, serves the torpedo bay UI on port 3001, and
tiles the screen: web UI top-left, OpenRocket top-right, Blender bottom-left,
Kord bottom-right. Every ask is accepted as the ship; there is no review step
in this demo. The UI shows how each ask propagated (Astra, physics, Blender,
OpenRocket, Kord) and offers sample asks that cover arming the ship: more
tubes and magazine, tube placement along the hull, and the torpedo itself.

```bash
uv sync --extra dev
roci demo                              # live model when OPENAI_API_KEY is in .env
roci demo --fixture --out out/demo-fixture   # deterministic rehearsal, no credentials
```

`roci` is `bin/roci`; symlink it onto your PATH once. Shared comparisons go
to the public Kord regardless of the local `KORD_API_BASE` in `.env`; pass
`--kord` to change that. Blender must be installed for Export comparison. Set
`BLENDER_BIN` if it is not at `/Applications/Blender.app/Contents/MacOS/Blender`.
The viewer loads Three.js from jsDelivr; sharing requires access to Kord.
Primitive preview, review and physics work without Blender.

Stop the previous server first if reusing the port; the command refuses a
busy port rather than opening windows onto someone else's workbench. The CLI
checks for a key at startup in live mode. Real `gpt-6-astra` proposals were verified
on 8 September: torpedoes, armor, and a cone extension through the same review
loop. The first request completed in 19.35 seconds. `ROCINANTE_MODEL` defaults
to `gpt-6-astra`; the actual model is shown and saved with each revision.
Never narrate fixture output as a model response.

## Rehearse the complete loop

1. In live mode, submit the tested stage request:

   > Carry eight more torpedoes by adding two launch tubes and six magazine
   > slots, without losing cruise burn time. Keep other design inputs unchanged
   > except the propellant needed to preserve endurance.

   Two independent Astra calls returned only the three intended input changes:
   tubes **4 → 6**, magazine **76.8 → 105.6 m³**, and propellant
   **1000 → 1008.94 t**. Capacity rose **20 → 28**, dry mass rose **19.2 t**,
   and the drive limit fell **12.07 → 11.96 g**. Cruise endurance still displays
   **35.09 h**; fuel rounding increased it by 0.155 seconds, so there was no loss.
   The fixture produces the same type of refit, but is explicitly not a model
   call. Always inspect the actual output before narrating a new live result.
2. Click **Export comparison**. Both the proposal and its accepted parent
   regenerate through Blender. The viewer loads those actual GLBs and marks
   affected parts. Orange marks geometry edits; blue marks input-only edits.
   Count the two added tubes. The fuel change affects engineering inputs,
   not the drive's shape. Toggle Previous hull and Changes, then Fit view.
   Rotation starts off to keep the launch ports visible; enable it deliberately
   when showing the silhouette.
3. Click **Share with Kord**, then **Open Kord comparison**. Inspect the pair
   in Kord's overlay view (scroll out over the canvas if the camera is too
   close). The local comparison report and GLB downloads are
   available beside the link. Keep the local workbench tab open for physics
   and the review decision.
4. Return and **Approve revision**. The active design advances to v1.
5. Propose **Add 2 cm of hull armor and show the performance cost**. Inspect
   lower delta-v and drive acceleration, then **Reject**. Armor changes mass,
   not exterior dimensions in this schema; the hull highlight denotes the
   affected assembly.
6. Propose **Lengthen the drive cone by 4 m; keep engine performance unchanged**.
   Check that the comparison is against accepted **v1**, not rejected v2.
   Export the pair and inspect the longer cone. Its geometry changes without
   invented performance gains.
7. Refresh, then stop and restart the server using the same `--out` directory.
   Check that decisions, v3's parent, and the saved Kord link survive. Reopening
   or repeating Share on a shared revision reuses the saved link.

Use a new `--out` directory to rehearse from a fresh baseline. Keep
`out/demo-fixture` as a clearly labeled fallback; it is not a saved model run.
A pending proposal must be approved or rejected before requesting another.

## 60-second narration

Use the tested stage request above, with the saved real comparison preloaded
as a fallback. The measured model call took 20.108 seconds; do not promise an
instant result. Full recording timing remains a rehearsal task.

- **0:00–0:08:** Submit the request. “Eight more torpedoes: two new launch tubes,
  six magazine slots, without losing cruise endurance.”
- **0:08–0:25:** While the model works: “Astra returns a complete ship spec.
  The geometry and every performance number are computed from it.”
- **0:25–0:40:** Export and show the comparison. “Four launch tubes become six.
  Capacity goes from twenty to twenty-eight. The extra payload adds nineteen
  tonnes.” Pause on the two added tubes and the mass/capacity panel.
- **0:40–0:52:** “We added fuel to preserve endurance. The heavier ship lowers
  the drive limit by about a tenth of a g. The crew limit stays at nine.”
- **0:52–1:00:** Approve locally. “The human decides whether the tradeoff is
  acceptable. The next request starts from the approved design.”

If model/export/upload latency exceeds the slot, explicitly switch to the
saved real run. Keep the local workbench for computed consequences and review;
Kord supplies the public 3D comparison. Do not imply the public Kord viewer
contains the local physics panel.

For the three-minute demo, include the rejected armor revision and the next
cone proposal to prove that rejection does not advance the design.

## Claims to keep accurate

- Fixed route and acceleration give fixed flip and arrival times. Do not claim
  a refit moves those times. Cruise endurance is a conservative initial-wet-mass
  estimate; its warning is not a variable-mass trajectory simulation.
- Tank packaging and volume constraints are not modeled. Added fuel is an
  engineering estimate, not a demonstrated tank installation.
- This milestone uses local approval and anonymous Kord comparisons. It does
  not post rationale comments or set an authenticated Kord verdict.
- OpenRocket and RocketPy simulator backends remain stubs; do not claim the
  torpedoes were simulated. Combat, interiors, and cinematic animation are out
  of scope until the refit loop is complete.
- Kord is a separate, pre-existing product. See README for the build boundary.
  This is unaffiliated fan work, with geometry generated from our own specs.

## Failure recovery

A failed model request leaves the accepted design and history intact. Export
and upload failures retain the proposal and expose retry controls. An upload
that times out may have reached Kord, so a retry can create another public
link. Export hashes prevent uploading changed or missing bytes. Shared links
expire according to Kord's returned expiry; use the saved local comparison
if a link has expired.

## Reproduce the stage model evidence

The opt-in runner makes one model proposal and writes inputs, prompts, output,
model/timing and computed checks. It performs no Kord upload. Use a fresh output
directory so evidence is not overwritten:

```bash
uv run --env-file /Users/w/Projects/rocinante/.env python scripts/stage_refit.py \
  --run-live --model gpt-6-astra --out out/stage-refit-new
```

The recorded probe is in `out/stage-refit-v2`; the independent UI request is in
`out/demo-stage-v2`. A positive sub-second endurance delta from rounded fuel is
recorded explicitly, not presented as exact mathematical equality.
