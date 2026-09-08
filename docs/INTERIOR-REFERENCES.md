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

## Detailed room pass

The September 2026 room pass uses the online SYFY stills above for recessed
galley drawers, restrained supplies, metal cabinetry, structural ribs and
tactical plotting rings. These production images are reference only. Added
workshop tools, bunk fixtures and engineering valves are original interpretive
geometry, not a claim of a screen-exact set reconstruction.

Actual online surface images are bundled in `src/rocinante/blend/textures`:

- [ambientCG Metal 032](https://ambientcg.com/view?id=Metal032): 1K JPG color,
  OpenGL normal and roughness maps for interior panels and exposed metal.
- [ambientCG Fabric 032](https://ambientcg.com/view?id=Fabric032): 1K JPG color,
  OpenGL normal and roughness maps for cushions, bedding and flight suits.
- Both assets are released under [CC0](https://docs.ambientcg.com/license/).
  Retrieved 8 September 2026. They are embedded into the exported GLB; no runtime
  image host, external credentials or network request is needed.

Each room has sealed wall panels, fasteners, service conduits, task-light
fixtures, handrails, a nonslip walkway and an emergency kit. Furniture details
follow room function: cockpit switch banks; ops plotting rings; crew lockers and
bunk restraints; galley sink, faucet and canisters; workshop vise, drill press
and tools; engineering flanges, valve wheels and vessel supports. Small bevels
provide edge highlights. World-scale face UVs keep material grain consistent.

To inspect the exported asset room by room:

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background --python scripts/render-rooms.py
```

This produces six images under `out/room-previews/` from the actual GLB.

`web/rocinante.glb` is the generated demo asset, so a fresh demo has a furnished
ship even without Blender. Regenerate it after generator changes:

```sh
uv run python -c 'from rocinante.blend import build_ship_mesh; from rocinante.samples import ROCINANTE; build_ship_mesh(ROCINANTE, "web/rocinante.glb")'
```

`roci demo` limits design revisions to `torpedo` and `rationale`. The server
rejects model responses that change any ship field before saving or propagating
a revision. General CLI refits keep their existing scope.
