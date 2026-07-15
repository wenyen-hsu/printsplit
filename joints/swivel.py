# SPDX-License-Identifier: GPL-3.0-or-later
"""Swivel: a mushroom peg snapped into an undercut chamber. One degree of
freedom — twist about the cut normal (turn a head, rotate a waist). The
flat shoulder under the cap is the retention lip; the cap taper is its
own insertion chamfer. Optional cross slits let the cap compress during
snap-in instead of stressing the chamber."""

from . import _solids
from .base import JointShape, JointSize


def _dims(size, params):
    unit_mm = params['unit_mm']
    c = params['clearance']
    r_s = size.width / 2.0
    z_n = max(0.6 * r_s, 1.2 * unit_mm)
    h_c = max(size.depth - z_n, 0.4 * r_s)
    # Undercut is specified NET of clearance AND of the polygonal facet
    # envelope (the neck bore is circumscribed so the peg can spin), so
    # neither can eat the retention lip. A proportional floor keeps the
    # grip comparable to the ball joint's on larger models instead of
    # staying a fixed fraction of a millimetre.
    u = max(params['undercut_mm'] * unit_mm, 0.12 * r_s)
    fs = _solids.facet_scale(params['segments'])
    r_c = (r_s + c) * fs + u
    return r_s, z_n, h_c, u, r_c, c


class SwivelShape(JointShape):
    id = 'SWIVEL'
    label = "Swivel"
    description = ("Mushroom snap pivot: parts twist freely around the "
                   "cut normal")
    movable = True
    fast_ok = False
    assembly = 'PUSH'

    def auto_size(self, section, scale, clearance, avail_male,
                  avail_female, params):
        unit_mm = params['unit_mm']
        base = min(section.extent_t, section.extent_b)
        r_s = 0.18 * base * scale
        z_n = max(0.6 * r_s, 1.2 * unit_mm)
        h_c = 0.8 * r_s
        wall = max(1.2 * unit_mm, 0.3 * r_s)
        budget = avail_female * 0.8
        if z_n + h_c + clearance + wall > budget and (z_n + h_c) > 0:
            shrink = budget / (z_n + h_c + clearance + wall)
            r_s *= max(shrink, 0.1)
            z_n = max(0.6 * r_s, 1.2 * unit_mm)
            h_c = 0.8 * r_s
        if params['undercut_mm'] < 0.15:
            params['warnings'].append(
                "Swivel undercut below 0.15 mm — the snap may not hold")
        embed = min(r_s, avail_male * 0.8)
        if embed <= 0.0 or r_s <= clearance * 4.0:
            return None
        return JointSize(width=2.0 * r_s, depth=z_n + h_c,
                         thickness=2.0 * r_s, embed=embed)

    def build_male(self, size, params):
        r_s, z_n, h_c, _u, r_c, c = _dims(size, params)
        seg = params['segments']
        # Straight stem: it must pass the neck channel (r_s + c), so any
        # root flare stays strictly below the seam as its own shell.
        bm = _solids.cone(r_s, r_s, -size.embed, z_n + 0.2 * h_c, seg)
        flare = _solids.cone(r_s * 1.3, r_s, -size.embed,
                             -0.1 * size.embed, seg)
        _solids.merge(bm, flare)
        # Cap shoulder starts one clearance above the retention lip so
        # the joint doesn't bind axially.
        cap = _solids.cone(r_c, 0.6 * r_c, z_n + c, z_n + h_c, seg)
        return _solids.merge(bm, cap)

    def build_male_cutter(self, size, params, clearance):
        if not params['slits']:
            return None
        r_s, z_n, h_c, _u, r_c, _c = _dims(size, params)
        unit_mm = params['unit_mm']
        if 2.0 * r_c < 5.0 * unit_mm:
            return None  # cap too small to need (or survive) slits
        slit = 1.0 * unit_mm / 2.0
        delta = 0.05 * r_c
        bm = _solids.box(-r_c - delta, r_c + delta, -slit, slit,
                         0.3 * z_n, z_n + h_c + delta)
        cross = _solids.box(-slit, slit, -r_c - delta, r_c + delta,
                            0.3 * z_n, z_n + h_c + delta)
        return _solids.merge(bm, cross)

    def build_cutter(self, size, params, clearance):
        r_s, z_n, h_c, _u, r_c, c = _dims(size, params)
        seg = params['segments']
        delta = 0.05 * r_s
        # Facet compensation: the polygonal peg must spin freely inside
        # the polygonal bore at any angle.
        fs = _solids.facet_scale(seg)
        # Neck channel, overlapping up into the chamber.
        bm = _solids.cone((r_s + c) * fs, (r_s + c) * fs,
                          -delta, z_n + 0.2 * h_c, seg)
        chamber = _solids.cone((r_c + c) * fs, (0.6 * r_c + c) * fs,
                               z_n, z_n + h_c + c, seg)
        return _solids.merge(bm, chamber)

    def draw(self, layout, op):
        layout.prop(op, "swivel_undercut_mm")
        layout.prop(op, "swivel_slits")
        layout.prop(op, "segments")
