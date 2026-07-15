# SPDX-License-Identifier: GPL-3.0-or-later
"""Snap-fit retention math (pure functions, unit-testable without bpy).

A ball of diameter D pressed through a socket opening of diameter
d_open = opening_ratio * D + 2 * clearance:

- net interference  i = D - d_open = (1 - rho) * D - 2 * c
- insertion strain  eps = i / d_open

PLA guidelines (thin flexing lip with a lead-in chamfer):
retention needs i >= I_MIN_MM and eps >= EPS_MIN; crack safety needs
eps <= EPS_MAX with a >= 1.2 mm wall.
"""

I_MIN_MM = 0.4
EPS_MIN = 0.015
EPS_MAX = 0.25
RHO_MIN = 0.6
WALL_MIN_MM = 1.2


def net_interference(diameter, opening_ratio, clearance):
    return (1.0 - opening_ratio) * diameter - 2.0 * clearance


def insertion_strain(diameter, opening_ratio, clearance):
    d_open = opening_ratio * diameter + 2.0 * clearance
    if d_open <= 0.0:
        return 0.0
    return net_interference(diameter, opening_ratio, clearance) / d_open


def clamp_opening(diameter_mm, opening_ratio, clearance_mm):
    """Adjust the opening ratio so the snap fit lands in the PLA window.

    Returns (effective_ratio, warnings): shrinks the opening when the net
    interference is below I_MIN_MM; if that would need a ratio below
    RHO_MIN (too small to insert the neck), keeps RHO_MIN's geometry and
    warns that the joint will be loose. Warns (without changing anything)
    when the strain exceeds EPS_MAX.
    """
    warnings = []
    rho = opening_ratio
    i = net_interference(diameter_mm, rho, clearance_mm)
    if i < I_MIN_MM:
        needed = 1.0 - (2.0 * clearance_mm + I_MIN_MM) / diameter_mm
        if needed < RHO_MIN:
            warnings.append(
                "Ball too small for a snap fit at this clearance — the "
                "joint will be loose; scale the joint up")
            rho = max(min(rho, needed), RHO_MIN) if needed > 0 else rho
        else:
            rho = min(rho, needed)
    if insertion_strain(diameter_mm, rho, clearance_mm) > EPS_MAX:
        warnings.append(
            "Snap fit is very tight and may crack on assembly — "
            "increase the opening ratio or clearance")
    return rho, warnings
