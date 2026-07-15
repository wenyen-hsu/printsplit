# SPDX-License-Identifier: GPL-3.0-or-later
"""Cylindrical pin: a tapered peg pressed straight into a matching pocket
along the joint axis. Aligns the parts and gives a friction fit, but does
not mechanically lock like a dovetail — pair with glue for permanence."""

import math

import bmesh
from mathutils import Matrix, Vector

from .base import JointShape


def _build_cone(radius_bottom, radius_top, z_bottom, z_top, segments):
    bm = bmesh.new()
    depth = z_top - z_bottom
    center_z = (z_top + z_bottom) / 2.0
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius_bottom,
        radius2=radius_top,
        depth=depth,
        matrix=Matrix.Translation(Vector((0.0, 0.0, center_z))),
    )
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


class CylinderShape(JointShape):
    id = 'CYLINDER'
    label = "Cylinder Pin"
    description = "Round alignment pin with a press-fit taper"
    assembly = 'PUSH'

    def _radii(self, size, params, grow=0.0):
        tan_t = math.tan(params['taper'])
        r_seam = size.width / 2.0 + grow
        r_bottom = r_seam + size.embed * tan_t
        r_top = max(r_seam - size.depth * tan_t, r_seam * 0.2)
        return r_bottom, r_top

    def build_male(self, size, params):
        r_bottom, r_top = self._radii(size, params)
        return _build_cone(
            r_bottom, r_top, -size.embed, size.depth,
            params['segments'],
        )

    def build_cutter(self, size, params, clearance):
        r_bottom, r_top = self._radii(size, params, grow=clearance)
        # Extend the tip by the clearance and keep the same taper slope so
        # the pocket is a uniform offset of the peg.
        tan_t = math.tan(params['taper'])
        z_top = size.depth + clearance
        r_top = max(r_top - clearance * tan_t, (size.width / 2.0) * 0.2)
        return _build_cone(
            r_bottom, r_top, -size.embed, z_top,
            params['segments'],
        )

    def draw(self, layout, op):
        layout.prop(op, "cyl_taper")
        layout.prop(op, "segments")
