# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross key: a plus-section tapered prism pressed into a matching
pocket. Aligns like the cylinder pin but resists rotation."""

import math

import bmesh

from .base import JointShape


def _build_key(width, arm, z_bottom, z_top, taper, embed_anchor=0.0):
    """Plus-section prism along Z. The section shrinks with +Z by
    ``tan(taper)`` per unit (anchored at z=0/seam) so the pocket rebuilt
    with inflated dimensions stays a uniform offset."""
    w = width / 2.0
    a = arm / 2.0
    profile = [
        (a, a), (a, w), (-a, w), (-a, a), (-w, a), (-w, -a),
        (-a, -a), (-a, -w), (a, -w), (a, -a), (w, -a), (w, a),
    ]
    tan_t = math.tan(taper)

    def ring_scale(z):
        return max((w - z * tan_t) / w, 0.05)

    bm = bmesh.new()
    rings = []
    for z in (z_bottom, z_top):
        s = ring_scale(z)
        rings.append([bm.verts.new((x * s, y * s, z)) for x, y in profile])
    r0, r1 = rings
    cap0 = bm.faces.new(list(reversed(r0)))
    cap1 = bm.faces.new(r1)
    n = len(profile)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    bmesh.ops.triangulate(bm, faces=[cap0, cap1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


class CrossKeyShape(JointShape):
    id = 'CROSS'
    label = "Cross Key"
    description = "Plus-section key: alignment pin that resists rotation"
    assembly = 'PUSH'

    def build_male(self, size, params):
        return _build_key(size.width, size.width / 3.0,
                          -size.embed, size.depth, params['cross_taper'])

    def build_cutter(self, size, params, clearance):
        return _build_key(size.width + 2.0 * clearance,
                          size.width / 3.0 + 2.0 * clearance,
                          -size.embed, size.depth + clearance,
                          params['cross_taper'])

    def draw(self, layout, op):
        layout.prop(op, "cross_taper")
