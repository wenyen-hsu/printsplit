# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-section analysis: find the cap faces a cut left behind, and derive
the joint placement frame (centroid, axis, in-plane axes) plus auto-sizing
information from them.

Everything is computed in the MESH LOCAL space of the half that owns the
caps. The two halves of a cut share identical local coordinates at the
seam (they were split from one object), so a local frame places the joint
correctly on BOTH halves even after the user moves them apart — each
target just applies its own ``matrix_world @ frame``.
"""

import math

from mathutils import Matrix, Vector

from ..utils.math_utils import make_frame_matrix, pca_axis_2d
from .cutting import CUT_ID_FACE_ATTR


class CrossSection:
    """Joint placement frame in mesh-local space.

    ``normal`` points out of the half the caps belong to (i.e. toward the
    mating half). ``extent_t`` / ``extent_b`` are the cap's oriented
    bounding-box extents along ``tangent`` / ``bitangent``.
    """

    __slots__ = ("center", "normal", "tangent", "bitangent",
                 "extent_t", "extent_b", "normal_spread")

    def __init__(self, center, normal, tangent, bitangent,
                 extent_t, extent_b, normal_spread):
        self.center = center
        self.normal = normal
        self.tangent = tangent
        self.bitangent = bitangent
        self.extent_t = extent_t
        self.extent_b = extent_b
        self.normal_spread = normal_spread

    def matrix(self, rotation=0.0):
        """Local-space frame matrix (columns: tangent, bitangent, normal)."""
        t, b = self.tangent, self.bitangent
        if rotation:
            rot = Matrix.Rotation(rotation, 3, self.normal)
            t = rot @ t
            b = rot @ b
        return make_frame_matrix(self.center, t, b, self.normal)


def cut_ids_in_object(obj):
    """All cut ids present on the object's cap faces."""
    attr = obj.data.attributes.get(CUT_ID_FACE_ATTR)
    if attr is None or attr.domain != 'FACE':
        return set()
    return {d.value for d in attr.data if d.value != 0}


def find_common_cut_id(obj_a, obj_b):
    """Latest cut id shared by both halves, or None."""
    common = cut_ids_in_object(obj_a) & cut_ids_in_object(obj_b)
    return max(common) if common else None


def compute_cross_section(obj, cut_id):
    """Analyze the cap faces of ``cut_id`` on ``obj``. Returns a
    CrossSection in the object's mesh-local space, or None when the object
    has no such caps."""
    mesh = obj.data
    attr = mesh.attributes.get(CUT_ID_FACE_ATTR)
    if attr is None or attr.domain != 'FACE':
        return None
    face_indices = [i for i, d in enumerate(attr.data) if d.value == cut_id]
    if not face_indices:
        return None

    total_area = 0.0
    center = Vector((0.0, 0.0, 0.0))
    normal = Vector((0.0, 0.0, 0.0))
    face_normals = []
    for i in face_indices:
        poly = mesh.polygons[i]
        area = poly.area
        total_area += area
        center += poly.center * area
        n = poly.normal.normalized()
        face_normals.append(n)
        normal += n * area
    if total_area < 1e-12 or normal.length < 1e-9:
        return None
    center /= total_area
    normal.normalize()

    spread = 0.0
    for n in face_normals:
        angle = normal.angle(n, 0.0)
        spread = max(spread, angle)

    # In-plane frame: PCA of cap vertices projected onto the plane.
    u = normal.orthogonal().normalized()
    v = normal.cross(u)
    verts = set()
    for i in face_indices:
        verts.update(mesh.polygons[i].vertices)
    points_2d = []
    for vi in verts:
        rel = mesh.vertices[vi].co - center
        points_2d.append((rel.dot(u), rel.dot(v)))
    axis2d = pca_axis_2d(points_2d)
    tangent = (u * axis2d.x + v * axis2d.y).normalized()
    bitangent = normal.cross(tangent)

    min_t = min_b = math.inf
    max_t = max_b = -math.inf
    for pu, pv in points_2d:
        # Re-express the (u, v) coords in the (tangent, bitangent) basis.
        pt = pu * axis2d.x + pv * axis2d.y
        pb = -pu * axis2d.y + pv * axis2d.x
        min_t, max_t = min(min_t, pt), max(max_t, pt)
        min_b, max_b = min(min_b, pb), max(max_b, pb)

    return CrossSection(
        center=center,
        normal=normal,
        tangent=tangent,
        bitangent=bitangent,
        extent_t=max_t - min_t,
        extent_b=max_b - min_b,
        normal_spread=spread,
    )


def material_depth(obj, origin_local, direction_local, max_dist):
    """Distance (in mesh-local units) from a point on the surface to the
    far side of ``obj``'s material along ``direction_local`` (ray cast
    slightly inset from the origin). Returns ``max_dist`` on no hit."""
    direction = direction_local.normalized()
    eps = max_dist * 1e-4
    hit, location, _normal, _index = obj.ray_cast(
        origin_local + direction * eps, direction, distance=max_dist)
    if not hit:
        return max_dist
    return (location - origin_local).length
