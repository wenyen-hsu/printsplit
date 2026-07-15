# SPDX-License-Identifier: GPL-3.0-or-later
"""Dovetail key: a trapezoidal prism, wider at the tip than at the seam,
so the halves lock against pulling apart along the joint axis. Assembly
slides along Y through a channel that opens at the model surface; a small
draft angle along Y makes the fit tighten as the parts slide home."""

import math

import bmesh

from .base import JointShape


def _build_prism(width, depth, thickness, embed, flare, draft,
                 y_min, y_max, draft_anchor):
    """Trapezoid profile in the XZ plane extruded along Y.

    half-width(z, y) = width/2 + z*tan(flare) - (y - draft_anchor)*tan(draft)

    ``draft_anchor`` is the Y where the profile has its nominal size, so a
    cutter that spans a longer Y range than the male stays a perfect
    (clearance-offset) superset of it.
    """
    tan_f = math.tan(flare)
    tan_d = math.tan(draft)

    def half_width(z, y):
        hw = width / 2.0 + z * tan_f - (y - draft_anchor) * tan_d
        return max(hw, width * 0.05)

    bm = bmesh.new()
    z_bot, z_top = -embed, depth
    rings = []
    for y in (y_min, y_max):
        corners = [
            (-half_width(z_bot, y), y, z_bot),
            (half_width(z_bot, y), y, z_bot),
            (half_width(z_top, y), y, z_top),
            (-half_width(z_top, y), y, z_top),
        ]
        rings.append([bm.verts.new(c) for c in corners])

    r0, r1 = rings
    bm.faces.new(r0)
    bm.faces.new(list(reversed(r1)))
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


class DovetailShape(JointShape):
    id = 'DOVETAIL'
    label = "Dovetail"
    description = "Tapered trapezoid key that locks the halves together"
    assembly = 'SLIDE'

    def _dims(self, size, params):
        if params.get('style', 'RAIL') == 'RAIL':
            # Full-width rail: spans the whole cut, later trimmed to the
            # model surface. Anchor the draft at the rail's wide end.
            half = max(size.channel, size.thickness) / 2.0
            return half, half
        return size.thickness / 2.0, max(size.channel, size.thickness) / 2.0

    def needs_trim(self, params):
        """RAIL pegs are built overlong and must be clipped to the model
        volume so they end flush with the outer surface."""
        return params.get('style', 'RAIL') == 'RAIL'

    def build_male(self, size, params):
        half_t, half_c = self._dims(size, params)
        y_half = half_c if self.needs_trim(params) else half_t
        return _build_prism(
            size.width, size.depth, size.thickness, size.embed,
            params['flare'], params['draft'],
            y_min=-y_half, y_max=y_half,
            draft_anchor=-half_t,
        )

    def build_cutter(self, size, params, clearance):
        half_t, half_c = self._dims(size, params)
        return _build_prism(
            size.width + 2.0 * clearance,
            size.depth + clearance,
            size.thickness,
            size.embed,
            params['flare'], params['draft'],
            y_min=-half_c, y_max=half_c,
            draft_anchor=-half_t,
        )

    def draw(self, layout, op):
        layout.prop(op, "dovetail_style")
        layout.prop(op, "dovetail_flare")
        layout.prop(op, "dovetail_draft")
