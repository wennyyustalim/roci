"""Known-good designs. Fixtures, and the agent's starting point when you want
a deterministic demo rather than a cold start."""

from rocinante.spec import FinSet, baseline_torpedo

BASELINE = baseline_torpedo().model_copy(update={
    "name": "Baseline",
    "rationale": "Hand-built starting point: a stable 3FNC on a 24 mm E motor.",
})

# Deliberately marginal. Good for showing the agent fix something.
UNSTABLE = BASELINE.model_copy(
    deep=True,
    update={
        "name": "Marginal",
        "fins": FinSet(count=3, root_chord_m=0.03, tip_chord_m=0.02, height_m=0.02),
        "rationale": "Fins too small; stability margin should come out under 1 caliber.",
    },
)


# --- the ship ---------------------------------------------------------------

from rocinante.ship import CrewMember, Deck, DeckKind, EpsteinDrive, Hull, ShipSpec, Weapons

# Corvette-class light frigate. The starting numbers are placeholders sized to
# land near the canonical figures, NOT canon -- check them against the wiki
# before anyone reads them off a screen.
ROCINANTE = ShipSpec(
    name="Rocinante",
    hull=Hull(length_m=46.0, beam_m=23.0, taper=0.42, deck_count=6, armor_cm=5.5),
    drive=EpsteinDrive(
        exhaust_velocity_km_s=1300.0,
        max_thrust_kn=372_600.0,
        cone_length_m=11.0,
        cone_radius_m=6.5,
        propellant_t=1000.0,
    ),
    weapons=Weapons(torpedo_tubes=4, magazine_m3=76.8, pdc_mounts=6, railgun=True),
    decks=[
        Deck(name="Cockpit", kind=DeckKind.OPS, height_m=2.6),
        Deck(name="Ops", kind=DeckKind.OPS, height_m=2.8),
        Deck(name="Crew", kind=DeckKind.CREW, height_m=2.8),
        Deck(name="Galley", kind=DeckKind.GALLEY, height_m=3.0, detailed=True),
        Deck(name="Machine shop", kind=DeckKind.MACHINE, height_m=3.2),
        Deck(name="Engineering", kind=DeckKind.ENGINEERING, height_m=4.0),
    ],
    crew=[
        CrewMember(name="Holden", role="captain", g_tolerance=5.0, juiced_g_tolerance=12.0),
        CrewMember(name="Naomi", role="engineer", g_tolerance=3.5, juiced_g_tolerance=9.0),
        CrewMember(name="Amos", role="mechanic", g_tolerance=6.0, juiced_g_tolerance=14.0),
        CrewMember(name="Alex", role="pilot", g_tolerance=5.5, juiced_g_tolerance=13.0),
    ],
    rationale="Baseline as salvaged. Everything a refit is measured against.",
)
