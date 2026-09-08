# The end-to-end demo

The demo spine is **intent → validated ShipSpec → computed consequences →
Blender geometry comparison → human decision → next proposal**. Kord hosts a
public comparison of the exported pair; approval and rationale remain in the
local workbench. Authenticated Kord review sessions are a later milestone.

## Verified live run in this checkout

The live Astra workbench is running at http://127.0.0.1:3001/ with saved state
in `out/demo-astra`. It contains approved torpedoes (v1), rejected armor (v2),
and a pending cone extension (v3) correctly based on v1. All three were real
`gpt-6-astra` responses. Blender export, local GLB rendering, Kord overlay,
server restart and saved-link reuse were verified.

[Open the real Astra comparison](https://work.withkord.com/d/17iuGJIpCOLwwZreHoqIQwrI)
(expires 15 September 2026 at 18:57 UTC). The fixture fallback remains saved
separately in `out/demo-fixture`.

Restart this checkout's verified run with the main project's configured env:

```bash
ROCINANTE_MODEL=gpt-6-astra KORD_API_BASE=https://work.withkord.com \
  uv run --env-file /Users/w/Projects/rocinante/.env rocinante demo \
  --live --port 3001 --out out/demo-astra
```

Use a new output directory for a fresh live rehearsal. The saved pending v3
requires approval or rejection before a new request; the status banner says so.

## Start

```bash
uv sync --extra dev
# Reliable fixture rehearsal; no model credentials needed.
KORD_API_BASE=https://work.withkord.com uv run rocinante demo \
  --port 3001 --out out/demo-fixture
# Open http://127.0.0.1:3001/
```

Blender must be installed for Export comparison. Set `BLENDER_BIN` if it is
not at `/Applications/Blender.app/Contents/MacOS/Blender`. The viewer loads
Three.js from jsDelivr; sharing requires access to Kord. Primitive preview,
review and physics work without Blender.

For live English requests, set `OPENAI_API_KEY` in `.env`, then run:

```bash
KORD_API_BASE=https://work.withkord.com uv run --env-file .env rocinante demo \
  --live --port 3001 --out out/demo-live
```

Stop the fixture server first if using the same port. The explicit Kord
setting avoids accidentally targeting an unavailable local server from `.env`.
The CLI checks for a key at startup. Real `gpt-6-astra` proposals were verified
on 8 September: torpedoes, armor, and a cone extension through the same review
loop. The first request completed in 19.35 seconds. `ROCINANTE_MODEL` defaults
to `gpt-6-astra`; the actual model is shown and saved with each revision.
Never narrate fixture output as a model response.

## Rehearse the complete loop

1. Propose **Carry eight more torpedoes without losing cruise burn time**.
   In live mode, type that request. Inspect the rationale and computed spec
   changes before deciding. The fixture goes from 20 to 28 torpedoes, adds
   19.2 t dry mass, and preserves delta-v and cruise endurance by adding fuel.
   A model proposal can differ; narrate the actual computed values. The verified
   Astra run added magazine capacity without adding tubes, so its exterior
   geometry stayed unchanged. Use the cone revision below for the visible
   shape comparison; the model does not invent tank or magazine geometry.
2. Click **Export comparison**. Both the proposal and its accepted parent
   regenerate through Blender. The viewer loads those actual GLBs and marks
   affected parts. Toggle Previous hull and Changes, then Fit view.
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

- **0:00–0:10:** “A sentence of intent becomes a reviewable engineering revision.”
  Enter the request in live mode, or explicitly introduce the fixture fallback.
- **0:10–0:25:** “The proposal is a complete validated ship spec. Every number
  here is computed from that spec.” Point to capacity, dry mass and endurance.
- **0:25–0:42:** Export and open the Kord comparison. “Same parts, changed
  geometry, with the previous hull available for comparison.” Pause on the
  overlay. Pre-open a saved comparison if network latency exceeds the slot.
- **0:42–0:52:** “The route stays at one-third g, so arrival stays fixed. Fuel
  margin changes with the design. The drive and crew limits are separate.”
- **0:52–1:00:** Approve locally. “The model proposes, physics computes the
  consequences, and the human approves. The next request starts here.”

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
