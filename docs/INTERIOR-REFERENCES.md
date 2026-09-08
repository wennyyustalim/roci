# Rocinante interior study

The demo uses original procedural geometry inspired by the TV production. It
is a compact six-deck interpretation fitted to this project's existing hull,
not a canonical deck plan or a reproduction of the full shooting sets.

Research accessed 8 September 2026:

- [Ryan Dening — The Expanse: Roci Design](https://deningart.artstation.com/projects/04DvnY).
  Original concept artist's exterior development and rough interior layout.
  Used for the upright, thrust-axis stack and relationship to the armor envelope.
- [ArtStation's interview with Ryan Dening and Tim Warnock](https://magazine.artstation.com/2016/02/scenes-concept-art-expanse/).
  Production discussion of vertical ship design, advanced Martian industrial
  design, armor tiles and the difference between concept work and actual sets.
- [SYFY — Fight or Flight, season 3 episode 1 gallery](https://www.syfy.com/the-expanse/photos/fight-or-flight-season-3-episode-1).
  Galley still: metal cabinetry, coffee machine, circular illuminated planting
  niche. Local research image: `reference/interior/galley-syfy.jpg` (untracked).
- [SYFY — IFF, season 3 episode 2 gallery](https://www.syfy.com/the-expanse/photos/iff-season-3-episode-2).
  Holden and Naomi at the tactical table: utility clothing, orange handrails,
  industrial floor panels, structural ribs and screen-based work surfaces.
  Local research image: `reference/interior/ops-syfy.jpg` (untracked).
- [Rhys Yorke — The Expanse: Rocinante UI](https://rhys.artstation.com/projects/q9Am1L).
  Production screen designer's work; reference for a consistent console palette
  and dense diagnostic readouts. Screens in this model are original geometry.

The cockpit, ops, crew quarters, galley, machine shop and engineering are ordered
bow to stern. Holden, Naomi, Amos and Alex are original stylized static figures,
not scanned or downloaded likenesses. Furniture and people follow their room
module during the assembly animation. The two armor halves retain the semantic
`hull_body` review tag. All reveal transforms exist only in the viewer.

`web/rocinante.glb` is the generated demo asset, so a fresh demo has a furnished
ship even without Blender. Regenerate it after generator changes:

```sh
uv run python -c 'from rocinante.blend import build_ship_mesh; from rocinante.samples import ROCINANTE; build_ship_mesh(ROCINANTE, "web/rocinante.glb")'
```

`roci demo` limits design revisions to `torpedo` and `rationale`. The server
rejects model responses that change any ship field before saving or propagating
a revision. General CLI refits keep their existing scope.
