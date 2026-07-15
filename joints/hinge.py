# SPDX-License-Identifier: GPL-3.0-or-later
"""Hinge: 1-DOF bend (knee/elbow) as a full-width barrel hinge.

The male carries a full-width knuckle cylinder on a thin tongue (both
trimmed flush to the model surface, like the dovetail rail). The female
gets a matching full-width groove, a V-slot for the tongue's swing, and
wedge reliefs on its seam face. Assembly slides in from the side; the
V-slot is much narrower than the knuckle, so the barrel cannot escape
vertically — mechanical retention with no loose pin.

Geometry keys:
- knuckle radius = pivot height z_h: the male face plane is tangent to
  the radius-z_h circle around the pivot at EVERY bend angle (that circle
  is the envelope of the rotating face), so the groove of radius z_h + c
  fully relieves intermediate angles;
- the V-slot walls and the seam wedges are both inclined at the ROM
  angle, forming a clean flat hard stop at +-ROM.

Hinge axis = local X (the cross-section major axis); re-aim it with the
joint Rotation property."""

import math

from . import _solids
from .base import JointShape, JointSize


def _dims(size, params):
    c = params['clearance']
    z_h = 0.5 * size.depth       # pivot height above the seam
    r_k = z_h                    # knuckle radius = envelope radius
    # Tongue thickness along Y. Thicker = stronger, but it widens the
    # V-slot; retention holds up to ~0.9 at 45 degrees ROM.
    n_y = params['tongue'] * z_h
    return z_h, r_k, n_y, c


class HingeShape(JointShape):
    id = 'HINGE'
    label = "Hinge"
    description = ("Full-width barrel hinge: single-axis bend with a hard "
                   "stop at the range-of-motion limit, slide-in assembly")
    movable = True
    fast_ok = False
    assembly = 'SLIDE'

    def needs_trim(self, params):
        return True  # knuckle + tongue are overlong, clip to the surface

    def auto_size(self, section, scale, clearance, avail_male,
                  avail_female, params):
        base = min(section.extent_t, section.extent_b)
        depth = min(0.5 * base * scale, 0.8 * avail_female)
        embed = min(0.5 * depth, avail_male * 0.8)
        if depth <= clearance * 8.0 or embed <= 0.0:
            return None
        params['_hinge_ymax'] = section.extent_b * 0.75
        return JointSize(width=section.extent_t * 3.0, depth=depth,
                         thickness=0.9 * depth, embed=embed,
                         channel=section.extent_t * 3.0)

    def build_male(self, size, params):
        z_h, r_k, n_y, _c = _dims(size, params)
        seg = params['segments']
        half_x = size.channel / 2.0

        # Full-width knuckle barrel about the pivot axis.
        bm = _solids.x_cylinder(r_k, r_k, -half_x, half_x, 0.0, z_h, seg)
        # Tongue from inside the male half up into the barrel.
        tongue = _solids.box(-half_x, half_x, -n_y / 2.0, n_y / 2.0,
                             -size.embed, z_h)
        return _solids.merge(bm, tongue)

    def build_cutter(self, size, params, clearance):
        z_h, r_k, n_y, c = _dims(size, params)
        seg = params['segments']
        theta = params['hinge_rom']
        delta = 0.05 * r_k
        half_x = size.channel / 2.0

        # 1. Groove: envelope relief AND the bearing bore (facet-
        #    compensated so the polygonal barrel turns at any angle).
        fs = _solids.facet_scale(seg)
        bm = _solids.x_cylinder((r_k + c) * fs, (r_k + c) * fs,
                                -half_x, half_x, 0.0, z_h, seg)
        # 2. V-slot for the tongue's swing: wide at the seam, narrowing
        #    to the tongue width at the pivot — the knuckle (diameter
        #    2*z_h) can never pass it, which is the retention.
        y_top = n_y / 2.0 + c
        y_bot = z_h * math.tan(theta) + y_top
        slot = _solids.profile_prism(
            [(-y_bot, -delta), (y_bot, -delta),
             (y_top, z_h + 0.3 * r_k), (-y_top, z_h + 0.3 * r_k)],
            -half_x, half_x)
        _solids.merge(bm, slot)
        # 3. Optional range-of-motion wedges on the seam face: the male's
        #    rotated face line is z(y) = |y|*tan(theta) - z_h*(1/cos(theta)
        #    - 1); cut the region between the seam and that line as one
        #    triangular prism per side. Off by default — it guarantees
        #    full ROM on wide flat cuts but removes a lot of the model;
        #    at a narrow cut section the surroundings clear by themselves.
        if not params.get('hinge_relief', False):
            return bm
        y_max = params.get('_hinge_ymax', size.thickness * 3.0)
        z_apex = -z_h * (1.0 / math.cos(theta) - 1.0)
        tan_t = math.tan(theta)
        y0 = (-z_apex - delta) / tan_t if tan_t > 1e-9 else y_max
        z_edge = y_max * tan_t + z_apex
        if z_edge > delta and y0 < y_max:
            right = _solids.profile_prism(
                [(y0, -delta), (y_max, -delta), (y_max, z_edge)],
                -half_x, half_x)
            _solids.merge(bm, right)
            left = _solids.profile_prism(
                [(-y_max, -delta), (-y0, -delta), (-y_max, z_edge)],
                -half_x, half_x)
            _solids.merge(bm, left)
        return bm

    def draw(self, layout, op):
        layout.prop(op, "hinge_rom")
        layout.prop(op, "hinge_tongue")
        layout.prop(op, "hinge_relief")
        layout.prop(op, "segments")
