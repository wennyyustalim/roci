# The demo

**Skeleton available now:** run `uv run rocinante demo --port 3001` and open
`http://127.0.0.1:3001/`. Propose the torpedo fixture → inspect → approve →
propose armor → reject → propose the cone extension. This demonstrates the
local review loop with simple shapes and computed numbers. Fixture proposals
do not call the model. On a selected proposal, Export comparison → Share with
Kord now generates a real public GLB comparison. Authenticated review sessions
and comments remain later work. See the current milestones in [PLAN.md](PLAN.md).
The stage script below is the target, not a statement of implemented scope.
At fixed cruise acceleration, arrival time does not move with a refit;
narrate the change in fuel margin and feasibility instead.

Two deliverables, and they are not the same thing:

- **A 60-second recorded video**, due 17:30 with the submission.
- **A 3-minute LIVE demo** on stage at 18:45, if you are picked, plus 2
  minutes of judge Q&A. The rubric explicitly punishes anything that is "just
  a presentation" — so on stage it is the running app, no slides.

The one frame that has to land: **the Rocinante, twice, superimposed in Kord —
the refitted hull solid, the old hull ghosted, the changed section lit — with
the flight numbers moving underneath.**

---

## The through-line

The old version of this file listed five features and needed a segue between
each. That is why it was hard to narrate. **They are not five features. They
are four consequences of one change.**

> **The spine:** *one sentence of intent in, a reviewable engineering revision
> out.*

You ask for a change in English. Astra rewrites the ship spec. The hull
regenerates. And the same change shows up in four places at once:

| Surface | What moves |
|---|---|
| **Geometry** | the changed section lit against a ghost of the old hull |
| **Performance** | Δv, dry mass, torpedo capacity, max acceleration |
| **Mission** | Tycho → Ceres flip time and arrival |
| **Crew** | the g the weakest crew member survives, against what the drive can pull |

That is the narration. Never *"and now let me show you the crew system"*.
Always *"and the same change shows up here, as a crew limit"*. You never need
a segue, because you never leave the subject.

It also puts the model at the front, which matters: **50% of the score is
GPT-6 Astra usage**, and a demo that opens on physics spends its best seconds
on the half of the rubric it is not being scored against.

---

## The beats

### 0 · Cold open — 0:00–0:08

The Roci in 3D on black, slow rotate, drive cone lit.

> "Engineering files are binary blobs. Version control sees that one changed
> and can tell you nothing else."

### 1 · The ask — 0:08–0:20

Type it. Out loud, as you type:

> "So we put GPT-6 Astra on the writing end."

```
rocinante refit "give me eight more torpedoes without losing burn time"
```

Astra returns a **complete ShipSpec** — structured output against our schema,
not prose. Show the spec landing.

> "Astra returns the whole ship, schema-validated. It never writes geometry
> and it never writes a number — every consequence you're about to see is
> computed from what it returned."

*Proves:* the model is the designer, and the separation is deliberate.

### 2 · The frame — 0:20–0:40 · **never cut this**

Blender regenerates the hull from the new spec in under a second. Both `.glb`
hulls go to Kord, and the diff opens.

> "New hull solid, old hull ghosted, the changed section lit. Underneath —
> Δv up 45. Dry mass up 19 tons. Torpedoes 20 to 28."

**Then stop talking.** Let the numbers finish moving. This is the money shot
and you must not narrate over it.

*Proves:* a design change to a spacecraft, reviewable, with consequences
attached.

### 3 · The other two columns — 0:40–0:52

> "Not four features — one change, four consequences. Same change, mission
> planner: Tycho to Ceres, constant thrust, flip at the midpoint — the burn
> time moves. Same change, crew: Naomi tops out at 9 g, so the design is
> bounded by what the people on board survive, not by the drive."

*Proves:* the physics is real and it is coupled to the spec.

### 4 · File it — 0:52–1:00

The Kord review session, Astra's rationale attached, awaiting approval.

> "And it files. Every refit is a version with a review session and the
> model's reasoning, waiting on a human. The model proposes, the physics
> reviews, the human approves."

---

## The 3-minute stage script

Same spine, room to breathe. Run it live. Keep a pre-baked run in a second
browser tab as a silent fallback.

**0:00–0:20 — Frame it, and clear the rules bar first.**

> "This is Rocinante. It's version control for engineering files where a
> change carries its consequences. Everything you're about to see is in a
> public repo, tagged: the Blender bridge and the diff engine existed before
> today, and everything that makes the model drive them was built in the last
> seven hours."

That sentence buys enormous goodwill with judges holding a disqualification
rule. Say it early, not defensively.

**0:20–0:50 — The ask.** As in beat 1. Emphasise structured output: *"parse
failures cost iterations, and iterations are the product."*

**0:50–1:40 — The frame.** Slow down. Say the three numbers. Then pause.

**1:40–2:20 — Mission and crew,** as one change with more consequences.

**2:20–2:50 — Kord.** The review session. Land on *"the model proposes, the
physics reviews, the human approves."*

**2:50–3:00 — Close on the spine.**

> "One sentence of intent in. A reviewable engineering revision out."

---

## Q&A prep — they will ask these

- **"What did you build today?"** → The README's "What was built when"
  section names the files on each side. Say the four: `ShipSpec` and its
  physics, the Astra refit, the parametric hull generator, the Kord
  integration. Everything on the "before" side is scaffolding the demo does
  not show.
- **"How did you use Astra in development?"** → 25% of the score and most
  teams fumble it. Track it during the day and have a specific answer.
- **"Is the physics real?"** → Rocket equation and the brachistochrone, both
  under test, closed form. Torpedoes go through actual OpenRocket via JPype.
- **"Isn't this a dashboard?"** → "The 3D superimposition is the product. The
  numbers are its caption."
- **"Isn't Kord your company?"** → "Yes, and it's pre-existing, which is why
  nothing we demo required changing it. Everything today is on this side of
  the HTTP boundary, in the public repo."
- **"The Expanse IP?"** → "Unaffiliated fan work, disclaimed in the README, no
  trademarked assets in the repo. Every polygon is generated by our own code
  from our own spec."

---

## Cut order

1. The Ring.
2. Combat entirely.
3. The crew bar — keep the g-limit as a number.
4. The mission line — keep the refit panel.
5. The cold-open render — open on the live viewer.

**Never cut beat 2.**

---

## Known risks

**The model call is the one unbuilt thing.** `RefitAgent.propose()` is written
against the current Responses/`text_format` shape; GPT-6 Astra may have moved
it. Read the migration quickstart before 10:45, not at 15:00.

**Blender must stay parametric.** The hull regenerates in 0.9 s because
nothing in it was placed by hand. The moment someone sculpts a detail, beat 2
dies. This is the single most important engineering constraint of the day.

**The Kord review session runs against local Kord.** Production's password
account is OpenAI's directory-review account and is not ours to borrow. If
local Kord is not up by noon, cut beat 4 to the diff link — anonymous, against
production, already working.

**Fan work.** The Expanse belongs to its authors and to Alcon. Disclaimer in
the README, no trademarked assets in the repo.
