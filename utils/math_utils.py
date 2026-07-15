# SPDX-License-Identifier: GPL-3.0-or-later
"""Plane construction from viewport strokes, RDP simplification, PCA frames,
and unit conversion. Pure math — no bpy.context access."""

import math

from mathutils import Matrix, Vector


def rdp_simplify(points, epsilon):
    """Ramer-Douglas-Peucker simplification of a 2D polyline.

    points: list of (x, y) tuples. Returns a simplified list keeping
    endpoints. epsilon is the max perpendicular deviation in pixels.
    """
    if len(points) < 3:
        return list(points)

    a = Vector(points[0])
    b = Vector(points[-1])
    ab = b - a
    ab_len = ab.length

    max_dist = -1.0
    max_i = 0
    for i in range(1, len(points) - 1):
        p = Vector(points[i])
        if ab_len < 1e-9:
            d = (p - a).length
        else:
            # Perpendicular distance from p to segment line ab.
            d = abs(ab.x * (a.y - p.y) - (a.x - p.x) * ab.y) / ab_len
        if d > max_dist:
            max_dist = d
            max_i = i

    if max_dist <= epsilon:
        return [points[0], points[-1]]
    left = rdp_simplify(points[: max_i + 1], epsilon)
    right = rdp_simplify(points[max_i:], epsilon)
    return left[:-1] + right


def plane_from_rays(origin_a, dir_a, origin_b, dir_b):
    """Plane containing two coplanar view rays (perspective rays share the
    eye; orthographic rays are parallel). Returns (co, normal) or None if
    the rays are degenerate (identical)."""
    normal = dir_a.cross(origin_b + dir_b - origin_a)
    if normal.length < 1e-12:
        return None
    return origin_a.copy(), normal.normalized()


def signed_distance(point, plane_co, plane_no):
    return (point - plane_co).dot(plane_no)


def transform_plane(matrix_inv, plane_co, plane_no):
    """Transform a world-space plane (co, no) into object space given the
    inverse of the object's world matrix. Points transform by M^-1; plane
    normals transform by M^T (the inverse-transpose of M^-1)."""
    co = matrix_inv @ plane_co
    m = matrix_inv.inverted_safe().to_3x3()
    no = (m.transposed() @ plane_no).normalized()
    return co, no


def pca_axis_2d(points_2d):
    """Major axis of a set of 2D points (list of (u, v)). Returns a unit
    Vector((u, v)). Falls back to (1, 0) for degenerate input."""
    n = len(points_2d)
    if n < 2:
        return Vector((1.0, 0.0))
    mu = sum(p[0] for p in points_2d) / n
    mv = sum(p[1] for p in points_2d) / n
    suu = svv = suv = 0.0
    for u, v in points_2d:
        du, dv = u - mu, v - mv
        suu += du * du
        svv += dv * dv
        suv += du * dv
    # Eigenvector of [[suu, suv], [suv, svv]] with the larger eigenvalue.
    trace = suu + svv
    det = suu * svv - suv * suv
    disc = max(0.0, (trace * trace) / 4.0 - det)
    lam = trace / 2.0 + math.sqrt(disc)
    if abs(suv) > 1e-12:
        axis = Vector((lam - svv, suv))
    elif suu >= svv:
        axis = Vector((1.0, 0.0))
    else:
        axis = Vector((0.0, 1.0))
    if axis.length < 1e-12:
        return Vector((1.0, 0.0))
    return axis.normalized()


def make_frame_matrix(origin, x_axis, y_axis, z_axis):
    """World matrix whose columns are the frame axes at `origin`."""
    m = Matrix((
        (x_axis.x, y_axis.x, z_axis.x, origin.x),
        (x_axis.y, y_axis.y, z_axis.y, origin.y),
        (x_axis.z, y_axis.z, z_axis.z, origin.z),
        (0.0, 0.0, 0.0, 1.0),
    ))
    return m


def mm_to_blender_units(mm, scene):
    """Convert millimetres to Blender units honoring the scene unit scale."""
    scale = scene.unit_settings.scale_length or 1.0
    return mm * 0.001 / scale
