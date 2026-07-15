# SPDX-License-Identifier: GPL-3.0-or-later
"""Cutting core: watertightness, volume conservation, tagging, errors."""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from printsplit.core.cutting import (
    CUT_ID_FACE_ATTR,
    CutError,
    CutPlane,
    cut_object,
)
from printsplit.utils.mesh_utils import is_watertight_mesh, mesh_volume


def make_cube(size=2.0, subdivisions=0, name="Cube"):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    if subdivisions:
        bmesh.ops.subdivide_edges(
            bm, edges=bm.edges, cuts=subdivisions, use_grid_fill=True)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def make_sphere(radius=1.0, name="Sphere"):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(
        bm, u_segments=32, v_segments=16, radius=radius)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def cap_face_count(mesh, cut_id):
    attr = mesh.attributes.get(CUT_ID_FACE_ATTR)
    assert attr is not None, "cap attribute missing"
    return sum(1 for d in attr.data if d.value == cut_id)


def test_straight_cut_cube():
    obj = make_cube(size=2.0, subdivisions=3)
    original_volume = mesh_volume(obj.data)

    plane = CutPlane(Vector((0, 0, 0.3)), Vector((0, 0, 1)))
    obj_a, obj_b = cut_object(obj, [plane], cut_id=1)

    assert is_watertight_mesh(obj_a.data), "half A is not watertight"
    assert is_watertight_mesh(obj_b.data), "half B is not watertight"

    va = mesh_volume(obj_a.data)
    vb = mesh_volume(obj_b.data)
    assert va > 0 and vb > 0, f"negative volumes: {va}, {vb}"
    assert math.isclose(va + vb, original_volume, rel_tol=1e-4), (
        f"volume not conserved: {va} + {vb} != {original_volume}")

    # Side A is the positive side of the plane (z > 0.3, the smaller part).
    assert va < vb, "side assignment looks wrong"

    assert cap_face_count(obj_a.data, 1) >= 1
    assert cap_face_count(obj_b.data, 1) >= 1


def test_straight_cut_sphere():
    obj = make_sphere()
    original_volume = mesh_volume(obj.data)
    plane = CutPlane(Vector((0, 0, 0)), Vector((0, 0, 1)))
    obj_a, obj_b = cut_object(obj, [plane], cut_id=7)

    assert is_watertight_mesh(obj_a.data)
    assert is_watertight_mesh(obj_b.data)
    va, vb = mesh_volume(obj_a.data), mesh_volume(obj_b.data)
    assert math.isclose(va + vb, original_volume, rel_tol=1e-4)
    assert math.isclose(va, vb, rel_tol=1e-3), "hemispheres should match"
    assert cap_face_count(obj_a.data, 7) >= 1


def test_polyline_cut_cube():
    """Zig-zag two-segment cut, as if drawn while looking along -Y."""
    obj = make_cube(size=2.0, subdivisions=4)
    original_volume = mesh_volume(obj.data)

    p0 = Vector((-2.0, 0.0, 0.5))
    p1 = Vector((0.0, 0.0, -0.5))
    p2 = Vector((2.0, 0.0, 0.5))
    y_axis = Vector((0, 1, 0))

    def seg_plane(a, b):
        no = (b - a).cross(y_axis).normalized()
        return a, no

    co0, no0 = seg_plane(p0, p1)
    co1, no1 = seg_plane(p1, p2)
    if no0.dot(no1) < 0:
        no1 = -no1

    # Miter at p1 bisects the two advance directions (projected off Y).
    a_prev = (p1 - p0).normalized()
    a_next = (p2 - p1).normalized()
    miter = (a_prev + a_next).normalized()

    planes = [
        CutPlane(co0, no0, end_co=p1, end_no=-miter),
        CutPlane(co1, no1, start_co=p1, start_no=miter),
    ]
    obj_a, obj_b = cut_object(obj, planes, cut_id=2)

    assert is_watertight_mesh(obj_a.data), "half A is not watertight"
    assert is_watertight_mesh(obj_b.data), "half B is not watertight"
    va, vb = mesh_volume(obj_a.data), mesh_volume(obj_b.data)
    assert va > 0 and vb > 0
    assert math.isclose(va + vb, original_volume, rel_tol=1e-4), (
        f"volume not conserved: {va} + {vb} != {original_volume}")


def test_miss_raises_and_leaves_mesh_untouched():
    obj = make_cube(size=2.0)
    vert_count = len(obj.data.vertices)
    plane = CutPlane(Vector((0, 0, 5.0)), Vector((0, 0, 1)))
    try:
        cut_object(obj, [plane], cut_id=1)
    except CutError:
        pass
    else:
        raise AssertionError("expected CutError for a plane that misses")
    assert bpy.data.objects.get("Cube") is obj
    assert len(obj.data.vertices) == vert_count


def test_cut_with_object_transform():
    obj = make_cube(size=2.0, subdivisions=2)
    obj.matrix_world = (Matrix.Translation(Vector((5, 3, -2)))
                        @ Matrix.Rotation(0.7, 4, 'Y'))
    bpy.context.view_layer.update()
    original_volume = mesh_volume(obj.data)

    # World-space horizontal plane through the object's center.
    plane = CutPlane(Vector((5, 3, -2)), Vector((0, 0, 1)))
    obj_a, obj_b = cut_object(obj, [plane], cut_id=3)

    assert is_watertight_mesh(obj_a.data)
    assert is_watertight_mesh(obj_b.data)
    va, vb = mesh_volume(obj_a.data), mesh_volume(obj_b.data)
    assert math.isclose(va + vb, original_volume, rel_tol=1e-4)
