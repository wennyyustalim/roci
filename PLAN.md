# Build plan

**Hacking runs 10:30 to 17:30. Submission and the video are due at 17:30.**
That is seven hours, and about **5.5 hours of building** once you subtract
lunch and an hour to record and submit. The previous version of this file was
budgeted for thirteen and scheduled beat 4 for 16:30 — after submissions
close. That was the plan's one fatal bug.

[DEMO.md](DEMO.md) is the target; this is the route to it. Read that first.

The measure of the day is **beat 2**: two hulls superimposed in Kord, the
changed section lit, the flight numbers moving underneath. Protect it.

## What already works, as of 10:30

Verified this morning, before the clock started:

- `ShipSpec` and every derived property — Δv 497 km/s, dry 2,148 t, 20
  torpedoes, 12.1 g, crew-limited to 9 g by Naomi. Rocket equation under test.
- The brachistochrone solver. `rocinante burn Tycho Ceres` returns flip at
  20h 50m, arrival 41h 40m, Δv 491 km/s.
- `blend/build_ship.py` regenerates the whole ship from a spec in **0.9 s**.
- `KordClient.share_diff()` mints a live 3D diff on production Kord in one
  call, anonymously. Smoke-tested against two regenerated hulls.
- 33 tests, lint clean.

So the day starts with the demo's spine already standing. Everything below
makes it *good*, not *exist*.

## The Kord integration, settled

Kord is a separate, pre-existing product. **Nothing in the demo requires a
change to it**, and that is deliberate — the rules say a feature added to your
startup must live in an isolated public repo, so the hackathon contribution is
all on this side of the HTTP boundary.

Three paths, in the order to reach for them:

1. **`POST /api/diff/share` — anonymous, no account, already in production.**
   Two files in, a `/d/<token>` URL out, rendering Kord's real 3D diff: heat
   map, overlay, side-by-side, part tree. `.glb` is an accepted format there.
   **This is the demo path.** It needs nothing from anyone.
2. **`/api/auth/demo-login` → upload → review session.** Kord's REST API is
   cookie-session only; there is no bearer token, which is why the old client
   would have 401'd on every call. The demo-login route is the supported way
   in — but **not against production.** Two locks guard it: the address must
   sit under `demo.withkord.com` (so no real address can ever pass), and
   `DEMO_LOGIN_EMAILS` must name it. That variable is already set in
   production, to `reviewer@demo.withkord.com` — **the account OpenAI's plugin
   directory reviews the Kord MCP connector with.** Rotating its password to
   borrow it would break an in-flight directory review and the continuous
   safety testing behind it. Adding a second address instead means editing the
   variable, and Vercel has no update — it is `env rm` then `env add`, and
   `vercel env rm` is a NEVER rule in Kord's CLAUDE.md.

   So: **run this beat against local Kord.** `.env.local` points at a genuinely
   local Supabase (127.0.0.1:54321), `provision-demo-reviewer.mts` mints a
   reviewer there with no production reach, and `KORD_API_BASE` already
   switches rocinante over. It also removes a live network dependency from the
   stage demo, which is worth having on its own.
3. The hosted MCP server. OAuth 2.1, and deliberately cannot write file bytes.
   Right for an interactive agent, wrong for a CLI uploading a mesh. Not used.

**`.ork` support in Kord is not today's work.** A new format there is a
registry row, a viewer type, an extraction branch, two loader arms, a
dispatcher arm and a viewer pair, under 70% coverage enforcement — a day on
its own, in a repo the rules push out of the demo anyway. The torpedo's
structured diff goes in the review comment instead, which costs twenty minutes
and says the same thing. Open the `.ork` PR next week; mention it on stage in
one sentence as what comes next.

## Two tracks

They meet at glTF. The part-naming convention is already fixed and
`build_ship.py` writes it: every mesh carries `rocinante_part`, named
`hull_*`, `drive_*`, `pdc_*`, `tube_*`, `deck_*`. Kord's viewer reads node
names into its part tree, so the names are load-bearing. Do not rename them.

- **Model track** — the Astra call, the prompt, the refit. This is 50% of the
  judging rubric and it starts first.
- **Systems track** — geometry polish, the mission consequence, the viewer.

## Order

| Time | Model track | Systems track |
|---|---|---|
| 10:30 | ~~Repo~~ done: github.com/wennyyustalim/roci. Decide local-vs-production Kord for the review-session beat. | |
| 10:45 | **Wire `RefitAgent.propose()` against the real GPT-6 Astra.** Check the migration guide first — the Responses/`text_format` shape in `agent/refit.py` is written against the current SDK and may have moved. | Hull silhouette: proportions until it reads as the Roci. Geometry only, no greeble. |
| 12:00 | Prompt iteration. Three asks that produce clean, single-cause diffs. Save the transcripts — "how you worked with the model" is 25%. | Materials and the light rig. This is where "pretty" comes from. |
| 13:00 | The refit beat driven live: ask → spec → regenerate → Kord link. | Mission consequence: the burn line moves when the spec does. |
| 14:00 | Second and third ask, as stage backups. Kord review session with the rationale attached. | Crew as a g-limit bound, rendered. One bar, not a screen. |
| 15:00 | Buffer. Whatever slipped. | Cold-open render (`rocinante ship-hero`). |
| 16:00 | **Feature freeze.** Both of you on the recording. | |
| 16:30 | Record the 60-second video. Do it in three takes, keep the third. | |
| 17:00 | Repo public, README built-before/built-during, all team members on the submission. **Submit.** | |

## Timeboxes

- **The hull: stop at 15:00 regardless.** It regenerates from a spec in under
  a second; that property is worth more than any detail you could add, and
  hand-placed geometry destroys it. Buy looks with lighting.
- **Do not hand-model anything.** If it is not generated from `ShipSpec`, it
  cannot survive a refit, and the refit is the demo.
- **The interior is cut.** Not reduced — cut. The galley was a trap at 13
  hours and it is impossible at 5.5.
- **Do not reopen the torpedo geometry or the `.ork` writer.** Nose, tubes,
  transitions and fins all build and export, and the round-trip test covers it.

## Cut order

1. The Ring.
2. Combat entirely — PDCs, pursuit curves, tracers.
3. The crew bar (keep the g-limit as a number in the panel).
4. The mission consequence (fall back to the refit panel alone).
5. The cold-open render (open on the live viewer instead).

**Never cut the refit.** Two hulls in Kord with the numbers moving is the
demo. If only that exists, you still have something worth showing.

## Rules compliance — do these at 10:30, not at 17:25

- **Public repo, with the boundary marked in the README.** The repo opens with
  a single commit — the pre-hackathon history was lost before it was pushed —
  so the "What was built when" section is the only record of the boundary.
  That makes it load-bearing: keep it accurate, and name the files on each
  side. The rule is an immediate-disqualification rule; being loud about it
  turns a risk into credibility.
- **Kord's own repo stays out of the demo.** Integrate over HTTP, say so.
- **Fan work.** The disclaimer stays in the README's second paragraph.
  Reference stills stay gitignored. Every polygon is generated by our code
  from our spec — say exactly that if a judge asks.
- **Never say "dashboard".** A dashboard as the main feature is a banned
  project. The 3D superimposition is the subject; the numbers are its caption.
