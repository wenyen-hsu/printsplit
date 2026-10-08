# SPDX-License-Identifier: GPL-3.0-or-later
"""Trapezoid key: an internal isosceles-trapezoid prism extruded from the
male face and pressed into a closed matching pocket in the female half.
The section narrows toward the tip so the key self-centres on insertion
and wedges snug as it seats; the flat sides resist rotation. Unlike the
dovetail it never reaches the model surface — nothing shows once
assembled."""

import math

import bmesh

from .base import JointShape


def _build_prism(half_seam, tan_side, half_y, z_bottom, z_top):
    """Isosceles trapezoid in the XZ plane extruded along Y.

    half-width(z) = half_seam - z * tan_side — widest at the root, linear
    everywhere, so the pocket rebuilt with an offset ``half_seam`` stays
    a uniform clearance offset of the key.
    """
    def hw(z):
        return half_seam - z * tan_side

    bm = bmesh.new()
    rings = []
    for y in (-half_y, half_y):
        corners = [
            (-hw(z_bottom), y, z_bottom),
            (hw(z_bottom), y, z_bottom),
            (hw(z_top), y, z_top),
            (-hw(z_top), y, z_top),
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


class TrapezoidShape(JointShape):
    id = 'TRAPEZOID'
    label = "Trapezoid Key"
    description = ("Internal tapered trapezoid key pressed into a hidden "
                   "pocket: self-centring, resists rotation")
    assembly = 'PUSH'

    def _tan_side(self, size, params):
        """Side slope, limited so the tip keeps >= 30% of the seam width
        (keeps the key linear — a clamped tip would break the uniform
        clearance offset)."""
        tan_s = math.tan(params['trap_angle'])
        max_tan = 0.7 * (size.width / 2.0) / size.depth
        return min(tan_s, max_tan)

    def build_male(self, size, params):
        return _build_prism(
            size.width / 2.0, self._tan_side(size, params),
            size.thickness / 2.0, -size.embed, size.depth)

    def build_cutter(self, size, params, clearance):
        tan_s = self._tan_side(size, params)
        # Offset each slanted side by `clearance` along its normal:
        # horizontally that is clearance / cos(side angle).
        grow = clearance * math.sqrt(1.0 + tan_s * tan_s)
        return _build_prism(
            size.width / 2.0 + grow, tan_s,
            size.thickness / 2.0 + clearance,
            -size.embed, size.depth + clearance)

    def draw(self, layout, op):
        layout.prop(op, "trap_angle")
