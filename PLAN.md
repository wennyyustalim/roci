# Demo and product checklist

The refit loop is working. The next milestone is a convincing, rehearsed demo:
**one sentence → a visible engineering change → computed consequences → a
reviewable comparison → a human decision → the next revision.**

This checklist works backward from that outcome and replaces the old hourly
schedule. [DEMO.md](DEMO.md) is the operator runbook; the
[historical plan](docs/PLAN-HISTORY.md) preserves the original schedule,
integration research, and cut decisions. Checked items are verified work;
unchecked items are remaining work or explicitly deferred scope. Publishing,
recording and submission are not marked complete without evidence.

**Recommended next:** P1.1, the single refit that changes both visible geometry
and performance. Develop that alongside P1.2 ship fidelity; then integrate and
rehearse before expanding integrations. Keep the schema and part IDs stable so
those tracks can proceed independently.

## Finish line — recorded and live demo

These are the final acceptance checks, performed after the P1 work below.

- [ ] Freeze the demo scope and select the exact request that opens the demo.
- [ ] Rehearse the 60-second narration against actual model, export and upload
  latency; record the timing rather than assuming the steps fit.
- [ ] Rehearse the three-minute live demo, including approval, rejection, and
  a next proposal based on the accepted parent.
- [ ] Make the central frame readable: changed ship geometry, its previous
  version, and computed consequences visible at presentation size.
- [ ] Prepare the live workbench and an already-loaded real Kord comparison
  in separate tabs; verify the public link has not expired.
- [ ] Prepare a clearly labeled fixture fallback and a saved real-model run;
  rehearse recovering from model, network, export and viewer failures.
- [ ] Record and review the 60-second video; check narration, cursor movement,
  text legibility and whether the comparison gets a quiet moment on screen.
- [ ] Prepare judge Q&A: what was built when, how Astra was used in development,
  physics limits, Kord's separate role, and generated fan-work geometry.
- [ ] Confirm applicable event deadlines and submission requirements. The
  archived plan says submission/video at 17:30 and stage at 18:45; those are
  historical targets, not a newly verified schedule.
- [ ] Verify public repository access, final source/version, README build
  boundary, all team members, and video link; submit and save confirmation.

## P1 — make the working loop tell the demo story

### P1.1 — one refit with a visible change and a measurable consequence

The current live torpedo ask increased magazine capacity and fuel but left
external geometry unchanged. The cone ask changed shape but preserved
performance. Neither alone supplies the original “one change, four
consequences” frame. Do not invent a geometry or physics change to bridge that.

- [ ] Choose and test an explicit request that legitimately changes both
  geometry and performance. Candidate: add two torpedo tubes and six magazine
  slots while preserving cruise burn time; inspect the model's actual design.
- [ ] Verify the changed tubes or hull section are visible in both exported
  GLBs and Kord, and that capacity, mass and drive limits follow the spec.
- [ ] Make sure the UI distinguishes displaced geometry from an affected
  assembly whose exterior is unchanged.
- [ ] Update the 60-second script to narrate the verified request and actual
  numbers. Remove the remaining “changed geometry” implication when showing
  the magazine-only torpedo proposal.
- [ ] Retain three stage-ready asks with saved inputs, outputs, rationale,
  computed comparisons, model identity and timing; record enough prompt/code
  provenance to explain and reproduce the runs.
- [ ] Document a concrete account of how Astra helped develop the project;
  saved ship proposals alone do not tell the development story.

### P1.2 — ship fidelity and comparison presentation

- [ ] Improve the generated hull silhouette and proportions until it reads
  as the Roci; keep all geometry parametric and preserve semantic part IDs.
- [ ] Improve materials and lighting, including the drive cone, so shape and
  changed-part highlights remain legible without hiding either version.
- [ ] Verify tube/PDC placement, nose/hull continuity and framing across the
  baseline and chosen stage refits after geometry changes.
- [ ] Recheck local ghost/highlight controls and Kord overlay/side-by-side
  views after export; document camera recovery where needed.
- [ ] Check the full demo at the actual presentation resolution: readable
  consequences, visible review actions, and minimal scrolling/tab switching.
- [ ] Generate and inspect an optional cold-open hero image with `ship-hero`
  after the live ship is ready. Cut this before cutting refit work.

### P1.3 — mission and crew feedback that can be narrated honestly

- [ ] Reconcile the conservative endurance warning with delta-v feasibility;
  the baseline currently has positive delta-v margin but warns “tanks last
  35 h, burn is 42 h.” Explain the estimate clearly until the solver changes.
- [ ] Add a compact mission visualization driven by computed transfer data:
  burn, flip and arrival, with fuel margin/feasibility changing on refit.
- [ ] Keep fixed-route, fixed-acceleration arrival times fixed. Only introduce
  changed timing when the underlying modeled trajectory actually changes.
- [ ] Add the planned compact crew-versus-drive acceleration bar, using the
  weakest crew member as the bound. Keep the existing numeric limits usable
  if the bar is cut.

## P2 — complete the deeper review and engineering loop

### P2.1 — authenticated Kord review sessions

Anonymous public comparison is sufficient for the current demo. These tasks
restore the original “file it for review” beat; local approval is not a Kord
verdict.

- [ ] Bring up and verify the separate local Kord/Supabase environment and
  dedicated demo account. Recheck historical provisioning rather than
  assuming the old local service is still available.
- [ ] Establish stable file identity: upload a baseline, then revise the same
  tracked file instead of creating unrelated filenames.
- [ ] Handle first-upload and changed-upload responses explicitly; use the
  `reviewSessionId` returned by upload rather than opening a duplicate session.
- [ ] Persist the revision-to-file/session mapping and expose the real review
  session link and pending state in the workbench.
- [ ] Implement and test verdict refresh, including rejected and pending
  sessions, and define how Kord verdicts relate to local acceptance.
- [ ] Prepare the rationale and computed comparison as a review comment;
  posting it requires explicit messaging authorization before the final send.
- [ ] Verify authenticated failures, retries and restart recovery without
  corrupting the accepted local design or creating duplicate review sessions.
- [ ] Rehearse the complete authenticated review beat before claiming it in
  DEMO.md; retain the anonymous comparison fallback.

### P2.2 — physics and packaging fidelity

- [ ] Implement a variable-mass mission/endurance solver with meaningful
  conservation and feasibility tests against the current closed-form model.
- [ ] Integrate its results into warnings and mission display; keep model
  assumptions explicit and all displayed values computed from the spec.
- [ ] Model tank and magazine packaging/volume constraints before claiming
  extra propellant or ammunition physically fits inside an unchanged hull.
- [ ] Propagate packaging changes through validation, diffing, geometry and
  the proposal prompt together; reject invalid arrangements before review.

### P2.3 — demo resilience and maintainability

- [ ] Move slow model/export/upload work off the request thread so the server
  stays responsive; specify job states and serialize state mutations first.
- [ ] Add concurrent-request tests only once that execution model exists,
  covering pending-proposal conflicts and duplicate export/share requests.
- [ ] Reduce the viewer's CDN dependency so the prepared local demo can show
  geometry when venue internet is unavailable.
- [ ] Provide a clear expired-share recovery path that preserves the original
  revision and records any newly created comparison link.
- [ ] Turn the manual live acceptance run into a repeatable opt-in smoke
  command with saved evidence, keeping paid model calls and public uploads
  explicit and out of ordinary unit tests.
- [ ] Check README's opening claims against implemented behavior: remove
  unsupported cone/performance examples and claims of real torpedo simulation.
- [ ] Refresh the README build boundary for the added handoff, GLB viewer,
  model failure handling, provenance and regression coverage.

## P3 — deferred product backlog, not demo prerequisites

These were cut or deferred in the source plans. They remain visible here so
“all todos” does not silently turn into a commitment to build them now.

- [ ] Implement and verify the OpenRocket torpedo simulator backend; it is
  currently a stub despite the existing `.ork` import/export tooling.
- [ ] Implement and verify the RocketPy fallback backend.
- [ ] Connect real torpedo simulation results to the design/review viewer;
  keep synthetic runs clearly labeled until then.
- [ ] Add simulated torpedo flights and ship combat: PDC behavior, pursuit
  curves and tracers, after the underlying simulation is real.
- [ ] Revisit generated interiors/decks/galley only after the exterior refit
  and demo are stable; the historical plan explicitly cut interior work.
- [ ] Add cinematic animation beyond the existing slow orbit if still useful.
- [ ] Revisit the Ring/slow-zone experience last.

## Completed — protect these invariants

- [x] Validate complete `ShipSpec` proposals; compute structured changes, mass,
  delta-v, acceleration, capacity, conservative endurance and mission checks.
- [x] Provide labeled deterministic torpedo, armor and cone fixtures.
- [x] Run real Astra structured proposals for all three asks; first request
  completed in 19.35 seconds. A separate gpt-5-mini request also succeeded.
- [x] Show and persist the actual model used, including exported reports.
- [x] Handle missing credentials, API/refusal/incomplete/validation failures
  without advancing the design; close owned SDK clients.
- [x] Preserve pending/approved/rejected history; only approval advances the
  active design, and a rejected proposal never becomes the next parent.
- [x] Persist local state atomically and recover it after server restart.
- [x] Render schematic geometry before export, then load actual Blender GLBs
  with a ghosted parent, semantic part highlights and combined framing.
- [x] Fix the generated nose discontinuity and add a regression test.
- [x] Export the exact accepted-parent/proposal pair with source specs,
  comparison report, GLB downloads and SHA-256 hashes.
- [x] Share the verified pair anonymously with Kord, persist URL/expiry, reuse
  saved links, and retain retry states without discarding review history.
- [x] Verify the real Astra loop in the browser, including exported geometry,
  Kord overlay, rejection, correct next parent, restart and share reuse.
- [x] Keep a saved real Astra run and a separate fixture rehearsal.
- [x] Provide demo/restart instructions and document current physics limits.
- [x] Verify 67 tests passed, 1 skipped at the refit milestone, with changed
  Python lint, JavaScript syntax and diff checks passing.

Evidence from the completed milestone: `out/demo-astra/acceptance.json`,
`live-smoke.json`, `workbench.json` and `exports/`. These are local, ignored
artifacts, not a portable checked-in demo package. The
[verified Astra comparison](https://work.withkord.com/d/17iuGJIpCOLwwZreHoqIQwrI)
expires 15 September 2026 at 18:57 UTC. See DEMO.md for restart instructions.

## Execution order and parallel ownership

| Track | Can run alongside | Serial gate before integration |
|---|---|---|
| P1.1 request and demo narrative | P1.2 geometry; P1.3 display clarification | Agree the target edit and preserve the schema/part-ID contract. |
| P1.2 hull/materials | Model prompt work; Kord client work | Re-export baseline and chosen refits, then visually verify both viewers. |
| P1.3 mission/crew display | Geometry and model work | Agree displayed quantities; solver-dependent UI waits for P2.2. |
| P2.1 Kord sessions | Geometry and physics | Local service/account → stable file → session → verdict → authorized comment. |
| P2.2 solver/packaging | Kord client work | Define schema/physics contract before dependent prompt/UI/geometry edits. |
| P2.3 background jobs | Independent docs/artifact preparation | Agree job/state transitions before UI and concurrency tests. |
| Recording and submission | Q&A and attribution preparation | Integrate → acceptance rehearsal → freeze → record → review → submit. |

Use separate file ownership or worktrees for independent tracks. A single
integrator owns shared schema/state changes and the final acceptance run.
Do not parallelize multiple edits to the same API or persisted-state contract.

## Constraints that remain in force

- Keep the refit/comparison as the subject; numbers explain the engineering
  change. Never cut the refit to make room for optional features.
- Generate ship geometry from `ShipSpec`; preserve `rocinante_part` and
  `hull_*`, `drive_*`, `pdc_*`, `tube_*`, `deck_*` identifiers.
- Keep fixed-route timing and current armor/cone effects honest. An assembly
  highlight does not imply displaced geometry or an unmodeled performance gain.
- Keep Kord separate and integrate through its existing HTTP APIs. Anonymous
  `/api/diff/share` remains the demo path. Authenticated work uses local Kord;
  do not repurpose production's directory-review account or rotate credentials.
  The hosted OAuth MCP path does not upload file bytes and is not used here.
- Preserve the supported `.ork` MIME type (`application/zip`) and existing
  round-trip tooling; do not reopen working torpedo geometry for demo polish.
- Keep the fan-work disclaimer, generated-asset provenance, and accurate
  built-before/built-during attribution. Keep reference stills out of git.
- If time runs short, cut Ring, combat, crew bar, mission visualization and
  hero shot before cutting the refit. Keep mission/crew numbers available.
