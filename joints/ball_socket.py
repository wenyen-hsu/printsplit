# SPDX-License-Identifier: GPL-3.0-or-later
"""Ball & socket: all-direction articulation (action-figure style).

The male is a stem + sphere; the female cavity is the inflated sphere
plus a truncated relief cone that is simultaneously the range-of-motion
neck clearance and the press-in lead chamfer. The socket opening is a
fraction (opening ratio) of the ball diameter — the resulting undercut
lip is what snaps and retains the ball."""

import math

from . import _solids, snapfit
from .base import JointShape, JointSize

_MAX_RELIEF = math.radians(75.0)


def ball_dims(size, params):
    """Derive (R, z_c, rho_eff, c) from the size. z_c is the ball-center
    height at which the inflated cavity's opening circle lands exactly on
    the seam plane."""
    c = params['clearance']
    radius = size.width / 2.0
    rho = params.get('_rho_eff', params['opening_ratio'])
    opening = rho * radius + c
    z_c = math.sqrt(max((radius + c) ** 2 - opening ** 2,
                        (0.05 * radius) ** 2))
    return radius, z_c, rho, c


def socket_cutter(size, params, clearance, seg, sign=1.0):
    """Sphere cavity + neck relief cone + face relief dish. ``sign=-1``
    mirrors it below the seam (for the double-ball's male-side socket)."""
    radius, z_c, rho, c = ball_dims(size, params)
    z_c *= sign
    # Facet compensation so the polygonal ball spins inside the
    # polygonal cavity at any angle.
    fs = _solids.facet_scale(seg) ** 2
    bm = _solids.uv_sphere((radius + c) * fs, z_c, seg)

    phi = min(math.asin(min((rho * radius + c) / (radius + c), 1.0))
              + params['rom'], _MAX_RELIEF)
    tan_phi = math.tan(phi)
    delta = 0.05 * radius
    z_inner = 0.2 * (radius + c)  # truncate inside the sphere cavity
    if sign > 0:
        cone = _solids.cone(
            tan_phi * (z_c + delta), tan_phi * z_inner,
            -delta, z_c - z_inner, seg)
    else:
        cone = _solids.cone(
            tan_phi * z_inner, tan_phi * (-z_c + delta),
            z_c + z_inner, delta, seg)
    _solids.merge(bm, cone)

    # ROM face relief: the male's flat cut face swings with the ball, so
    # the female face around the socket is dished into a funnel of the
    # ROM angle — otherwise the faces collide on the first degree of
    # rotation. (Action figures dish their sockets the same way.)
    theta = params['rom']
    if theta > 1e-4:
        opening = rho * radius + c
        r_relief = params.get('_ball_r_relief', 3.0 * radius)
        z_top = (r_relief - opening) * math.tan(theta)
        if z_top > delta:
            ring = _solids.lathe(
                [(opening, -delta * sign),
                 (r_relief, -delta * sign),
                 (r_relief, z_top * sign)],
                seg)
            _solids.merge(bm, ring)
    return bm


def apply_retention_clamp(section, scale, clearance, params):
    """Compute the ball radius and enforce the snap-fit window; stashes
    the effective opening ratio in params['_rho_eff']."""
    unit_mm = params['unit_mm']
    base = min(section.extent_t, section.extent_b)
    radius = 0.22 * base * scale
    rho_eff, warnings = snapfit.clamp_opening(
        (2.0 * radius) / unit_mm,
        params['opening_ratio'],
        clearance / unit_mm,
    )
    params['_rho_eff'] = rho_eff
    params['warnings'].extend(warnings)
    return radius


class BallSocketShape(JointShape):
    id = 'BALL_SOCKET'
    label = "Ball Socket"
    description = ("Snap-in ball joint: all-direction rotation and twist, "
                   "action-figure style")
    movable = True
    fast_ok = False
    assembly = 'PUSH'

    def auto_size(self, section, scale, clearance, avail_male,
                  avail_female, params):
        unit_mm = params['unit_mm']
        radius = apply_retention_clamp(section, scale, clearance, params)
        # Face relief must reach the cut face's farthest corner.
        params['_ball_r_relief'] = 1.05 * math.hypot(
            section.extent_t, section.extent_b) / 2.0

        # Fit ball + wall inside the female material.
        for _ in range(3):
            wall = max(1.2 * unit_mm, 0.3 * radius)
            size_probe = JointSize(width=2 * radius, depth=0,
                                   thickness=2 * radius, embed=0)
            _r, z_c, _rho, _c = ball_dims(size_probe, params)
            need = z_c + radius + clearance + wall
            budget = avail_female * 0.85
            if need <= budget or need <= 0:
                break
            radius *= max(budget / need, 0.1)

        embed = min(0.5 * radius, avail_male * 0.8)
        if embed <= 0.0 or radius <= clearance * 4.0:
            return None
        size = JointSize(width=2 * radius, depth=0,
                         thickness=2 * radius, embed=embed)
        _r, z_c, _rho, _c = ball_dims(size, params)
        size.depth = z_c + radius
        return size

    def build_male(self, size, params):
        radius, z_c, _rho, _c = ball_dims(size, params)
        seg = params['segments']
        neck = params['neck_ratio'] * radius
        # Stem tops out inside the ball — overlapping shells, EXACT-safe.
        bm = _solids.cone(neck * 1.15, neck, -size.embed, z_c, seg)
        ball = _solids.uv_sphere(radius, z_c, seg)
        return _solids.merge(bm, ball)

    def build_cutter(self, size, params, clearance):
        return socket_cutter(size, params, clearance, params['segments'])

    def draw(self, layout, op):
        layout.prop(op, "ball_opening_ratio")
        layout.prop(op, "ball_rom")
        layout.prop(op, "ball_neck_ratio")
        layout.prop(op, "segments")
