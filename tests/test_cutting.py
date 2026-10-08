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


def make_prongs(name="Prongs"):
    """A U shape: a 6x2x1 bar (z in [0, 1]) with a 2x2x2 prong rising from
    each end (x in [-3, -1] and [1, 3], z in [1, 3]). Volume 28."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(6.0, 2.0, 1.0), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0.0, 0.0, 0.5), verts=bm.verts)
    bmesh.ops.subdivide_edges(
        bm, edges=bm.edges, cuts=2, use_grid_fill=True)
    for sx in (-1.0, 1.0):
        bm.normal_update()
        top = [f for f in bm.faces
               if f.normal.z > 0.5 and f.calc_center_median().x * sx > 1.0]
        ret = bmesh.ops.extrude_face_region(bm, geom=top)
        verts = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, vec=(0.0, 0.0, 2.0), verts=verts)
        bmesh.ops.delete(bm, geom=top, context='FACES')
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    assert is_watertight_mesh(mesh)
    assert math.isclose(mesh_volume(mesh), 28.0, rel_tol=1e-6)
    return obj


def slab_x(z, x0, x1):
    """Horizontal plane at height z, bounded to the stroke x0 -> x1."""
    return CutPlane(Vector((0, 0, z)), Vector((0, 0, 1)),
                    start_co=Vector((x0, 0, 0)), start_no=Vector((1, 0, 0)),
                    end_co=Vector((x1, 0, 0)), end_no=Vector((-1, 0, 0)))


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


def test_stroke_spares_parts_it_does_not_touch():
    """A stroke across one prong cuts that prong only, not the other prong
    lying on the same plane past the stroke's end."""
    obj = make_prongs()
    obj_a, obj_b = cut_object(obj, [slab_x(2.0, -3.5, -0.5)], cut_id=1)

    assert is_watertight_mesh(obj_a.data)
    assert is_watertight_mesh(obj_b.data)
    va, vb = mesh_volume(obj_a.data), mesh_volume(obj_b.data)
    assert math.isclose(va + vb, 28.0, rel_tol=1e-4)
    # Side A is the top of the left prong alone (2 x 2 x 1).
    assert math.isclose(va, 4.0, rel_tol=1e-4), f"side A volume {va}"
    # The right prong keeps its original vertices: no bisect ran there.
    assert all(v.co.x < 0.0 for v in obj_a.data.vertices)


def test_short_stroke_severs_the_whole_part():
    """A stroke that stops inside a part's silhouette still severs it."""
    obj = make_prongs()
    obj_a, obj_b = cut_object(obj, [slab_x(2.0, -2.4, -2.1)], cut_id=1)

    assert is_watertight_mesh(obj_a.data)
    assert is_watertight_mesh(obj_b.data)
    va, vb = mesh_volume(obj_a.data), mesh_volume(obj_b.data)
    assert math.isclose(va, 4.0, rel_tol=1e-4), f"side A volume {va}"
    assert math.isclose(vb, 24.0, rel_tol=1e-4), f"side B volume {vb}"


def test_hollow_shell_inner_wall_is_cut():
    """A stroke touching only the outer wall of a hollow cube also cuts
    the inner wall it encloses, so no shell runs through the caps."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=4.0)
    inner = bmesh.ops.create_cube(bm, size=2.0)["verts"]
    inner_faces = {f for v in inner for f in v.link_faces}
    bmesh.ops.reverse_faces(bm, faces=list(inner_faces))
    mesh = bpy.data.meshes.new("Hollow")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("Hollow", mesh)
    bpy.context.scene.collection.objects.link(obj)

    obj_a, obj_b = cut_object(obj, [slab_x(0.25, -2.5, -1.5)], cut_id=4)
    assert is_watertight_mesh(obj_a.data)
    assert is_watertight_mesh(obj_b.data)
    # One cap per contour on each side: outer and inner.
    assert cap_face_count(obj_a.data, 4) == 2
    assert cap_face_count(obj_b.data, 4) == 2


def test_cut_that_does_not_sever_raises():
    """Cutting one side of a ring leaves it connected around the other
    side: an error, and the mesh is untouched."""
    bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.25)
    obj = bpy.context.active_object
    vert_count = len(obj.data.vertices)
    plane = CutPlane(Vector((0, 0, 0)), Vector((0, 1, 0)),
                     start_co=Vector((0.5, 0, 0)), start_no=Vector((1, 0, 0)),
                     end_co=Vector((1.5, 0, 0)), end_no=Vector((-1, 0, 0)))
    try:
        cut_object(obj, [plane], cut_id=1)
    except CutError:
        pass
    else:
        raise AssertionError("expected CutError for a ring cut on one side")
    assert bpy.data.objects.get(obj.name) is obj
    assert len(obj.data.vertices) == vert_count
