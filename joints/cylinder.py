# SPDX-License-Identifier: GPL-3.0-or-later
"""Cylindrical pin: a tapered peg pressed straight into a matching pocket
along the joint axis. By default a snap ring near the tip clicks into a
matching groove so the parts hold without glue; the taper keeps insertion
easy until the ring seats."""

import math

import bmesh
from mathutils import Matrix, Vector

from . import _solids
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


def _snap_ring(radius_at, z_ring, bulge, half_height, segments):
    """Annular triangular ridge sitting on a cone surface: rooted a hair
    inside the peg, peaking ``bulge`` above the surface."""
    return _solids.lathe(
        [(radius_at * 0.9, z_ring - half_height),
         (radius_at + bulge, z_ring),
         (radius_at * 0.9, z_ring + half_height)],
        segments)


class CylinderShape(JointShape):
    id = 'CYLINDER'
    label = "Cylinder Pin"
    description = ("Round pin with a press-fit taper and an optional "
                   "click-lock snap ring")
    # Snap-ring operands are multiple overlapping shells: EXACT-only.
    fast_ok = False
    assembly = 'PUSH'

    def _radii(self, size, params, grow=0.0):
        tan_t = math.tan(params['taper'])
        r_seam = size.width / 2.0 + grow
        r_bottom = r_seam + size.embed * tan_t
        r_top = max(r_seam - size.depth * tan_t, r_seam * 0.2)
        return r_bottom, r_top

    def _ring_dims(self, size, params):
        c = params['clearance']
        unit_mm = params['unit_mm']
        tan_t = math.tan(params['taper'])
        z_ring = 0.6 * size.depth
        r_at = size.width / 2.0 - z_ring * tan_t
        # Net engagement: proportional floor so large pins grip like the
        # ball joint instead of holding a fixed fraction of a millimetre.
        bulge = c + max(params['snap_mm'] * unit_mm, 0.08 * r_at)
        half_h = max(1.0 * unit_mm, 0.2 * r_at)
        return z_ring, r_at, bulge, half_h, c

    def build_male(self, size, params):
        r_bottom, r_top = self._radii(size, params)
        seg = params['segments']
        bm = _build_cone(r_bottom, r_top, -size.embed, size.depth, seg)
        if params.get('snap'):
            z_ring, r_at, bulge, half_h, _c = self._ring_dims(size, params)
            ring = _snap_ring(r_at, z_ring, bulge, half_h, seg)
            _solids.merge(bm, ring)
        return bm

    def build_cutter(self, size, params, clearance):
        r_bottom, r_top = self._radii(size, params, grow=clearance)
        # Extend the tip by the clearance and keep the same taper slope so
        # the pocket is a uniform offset of the peg.
        tan_t = math.tan(params['taper'])
        z_top = size.depth + clearance
        r_top = max(r_top - clearance * tan_t, (size.width / 2.0) * 0.2)
        seg = params['segments']
        bm = _build_cone(r_bottom, r_top, -size.embed, z_top, seg)
        if params.get('snap'):
            z_ring, r_at, bulge, half_h, c = self._ring_dims(size, params)
            # Groove: same ridge, offset outward and slightly taller so
            # the male ring seats with the normal clearance.
            groove = _snap_ring(r_at + c, z_ring, bulge, half_h + c, seg)
            _solids.merge(bm, groove)
        return bm

    def draw(self, layout, op):
        layout.prop(op, "cyl_taper")
        layout.prop(op, "cyl_snap")
        if op.cyl_snap:
            layout.prop(op, "cyl_snap_mm")
        layout.prop(op, "segments")
