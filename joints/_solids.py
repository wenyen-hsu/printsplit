# SPDX-License-Identifier: GPL-3.0-or-later
"""Primitive solid builders shared by joint shapes.

All functions return a NEW closed-manifold bmesh in joint local space
(+Z into the female half, seam at z=0). Operand bmeshes handed to the
boolean pipeline may contain several overlapping shells — the EXACT
solver resolves them by winding number. Shapes that ship as printable
objects (connectors) must pre-union their shells instead.

Convention: any solid that must pierce the seam extends a small delta
past it rather than ending exactly at z=0 — exactly-coincident faces
break boolean solvers.
"""

import bmesh
from mathutils import Matrix, Vector


def merge(target_bm, source_bm, *, free_source=True):
    """Append source_bm's geometry into target_bm as an extra shell."""
    mesh_tmp = None
    # bmesh has no direct append; go through a throwaway mesh.
    import bpy

    mesh_tmp = bpy.data.meshes.new("_ps_solid_tmp")
    source_bm.to_mesh(mesh_tmp)
    if free_source:
        source_bm.free()
    target_bm.from_mesh(mesh_tmp)
    bpy.data.meshes.remove(mesh_tmp)
    return target_bm


def cone(radius_bottom, radius_top, z_bottom, z_top, segments):
    """Z-axis (truncated) cone spanning [z_bottom, z_top]."""
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


def uv_sphere(radius, center_z, segments):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(
        bm,
        u_segments=segments,
        v_segments=max(segments // 2, 8),
        radius=radius,
        matrix=Matrix.Translation(Vector((0.0, 0.0, center_z))),
    )
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def box(x0, x1, y0, y1, z0, z1):
    bm = bmesh.new()
    corners = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    verts = [bm.verts.new(c) for c in corners]
    faces = [
        (0, 3, 2, 1), (4, 5, 6, 7),
        (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    for f in faces:
        bm.faces.new([verts[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def x_cylinder(radius_left, radius_right, x_left, x_right, y, z, segments):
    """(Truncated) cone with its axis along X, centered at (y, z)."""
    bm = bmesh.new()
    depth = x_right - x_left
    center_x = (x_right + x_left) / 2.0
    # create_cone builds along +Z with radius1 at -Z; rotate -Z onto -X
    # (i.e. +Z onto +X) so radius_left lands at x_left.
    mat = (Matrix.Translation(Vector((center_x, y, z)))
           @ Matrix.Rotation(1.5707963267948966, 4, 'Y'))
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius_left,
        radius2=radius_right,
        depth=depth,
        matrix=mat,
    )
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def facet_scale(segments):
    """Circumscribe factor for rotational joints: a female bore whose
    N-gon faces must clear the male N-gon's VERTICES at any rotation
    angle needs its radius divided by cos(pi/N)."""
    import math

    return 1.0 / math.cos(math.pi / max(segments, 3))


def lathe(points_rz, segments):
    """Solid of revolution about Z from a closed (r, z) profile with
    r > 0 everywhere (torus topology)."""
    import math

    bm = bmesh.new()
    verts = [bm.verts.new((r, 0.0, z)) for r, z in points_rz]
    edges = []
    n = len(verts)
    for i in range(n):
        edges.append(bm.edges.new((verts[i], verts[(i + 1) % n])))
    bmesh.ops.spin(
        bm,
        geom=verts + edges,
        cent=(0.0, 0.0, 0.0),
        axis=(0.0, 0.0, 1.0),
        angle=2.0 * math.pi,
        steps=segments,
        use_merge=True,
        use_duplicate=False,
    )
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def profile_prism(points_yz, x0, x1, *, scale_at=None):
    """Closed polygon in the YZ plane extruded along X from x0 to x1.

    points_yz: CCW list of (y, z) tuples. Concave profiles are fine — the
    caps are triangulated. ``scale_at``: optional (s0, s1) per-end uniform
    scale of the profile about its centroid (for tapered keys).
    """
    n = len(points_yz)
    cy = sum(p[0] for p in points_yz) / n
    cz = sum(p[1] for p in points_yz) / n

    def ring(x, s):
        return [(x, cy + (y - cy) * s, cz + (z - cz) * s)
                for y, z in points_yz]

    s0, s1 = scale_at if scale_at else (1.0, 1.0)
    bm = bmesh.new()
    r0 = [bm.verts.new(co) for co in ring(x0, s0)]
    r1 = [bm.verts.new(co) for co in ring(x1, s1)]

    cap0 = bm.faces.new(list(reversed(r0)))
    cap1 = bm.faces.new(r1)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    bmesh.ops.triangulate(bm, faces=[cap0, cap1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm
