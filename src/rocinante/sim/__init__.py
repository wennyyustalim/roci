"""Flight simulation, behind one swappable interface.

`get_simulator()` picks a backend from the ROCINANTE_SIM environment variable.
Nothing above this package knows which one ran.
"""

from __future__ import annotations

import os

from rocinante.sim.base import SimResult, Simulator

__all__ = ["SimResult", "Simulator", "get_simulator"]


def get_simulator(name: str | None = None) -> Simulator:
    name = (name or os.getenv("ROCINANTE_SIM", "openrocket")).lower()
    if name == "openrocket":
        from rocinante.sim.openrocket import OpenRocketSimulator

        return OpenRocketSimulator()
    if name == "rocketpy":
        from rocinante.sim.rocketpy import RocketPySimulator

        return RocketPySimulator()
    raise ValueError(f"unknown simulator: {name!r} (want 'openrocket' or 'rocketpy')")
