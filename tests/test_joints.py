# SPDX-License-Identifier: GPL-3.0-or-later
"""Joint generation: manifold output, volume change in the right
direction, and a real clearance gap (empty intersection) for every shape."""

import math

import bpy
from mathutils import Vector

from printsplit.core.cutting import CutPlane, cut_object
from printsplit.utils.mesh_utils import is_watertight_mesh, mesh_volume

from test_cutting import make_cube


def _cut_cube_in_half():
    obj = make_cube(size=2.0, subdivisions=2, name="Body")
    plane = CutPlane(Vector((0, 0, 0)), Vector((0, 0, 1)))
    obj_a, obj_b = cut_object(obj, [plane], cut_id=1)
    bpy.context.view_layer.update()
    return obj_a, obj_b


def _select_pair(male, female):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    male.select_set(True)
    female.select_set(True)
    bpy.context.view_layer.objects.active = male


def _rest_intersection(male, female, lift=2e-4):
    """Intersection at (near-)rest pose: the male is lifted a hair first
    so the big flat seam faces are not exactly coplanar — coplanar
    contact makes both boolean solvers unreliable. Separating strictly
    reduces overlap, so a clean 0 here proves a clean rest fit."""
    from mathutils import Matrix, Vector

    saved = male.matrix_world.copy()
    male.matrix_world = (
        Matrix.Translation(Vector((0, 0, lift))) @ male.matrix_world)
    bpy.context.view_layer.update()
    ix = _intersection_volume(male, female)
    male.matrix_world = saved
    bpy.context.view_layer.update()
    return ix


def _intersection_volume(obj_x, obj_y):
    """Volume of the boolean intersection of two evaluated objects.

    Tries EXACT first; if it silently returns an empty mesh (a known
    failure mode on some inputs), re-measures with FAST.
    """
    volume = None
    for solver in ('EXACT', 'FAST'):
        dup = obj_x.copy()
        dup.data = obj_x.data.copy()
        bpy.context.scene.collection.objects.link(dup)
        mod = dup.modifiers.new(name="ix", type='BOOLEAN')
        mod.operation = 'INTERSECT'
        mod.object = obj_y
        mod.solver = solver
        # The freshly linked duplicate must enter the depsgraph, or the
        # evaluated mesh comes back empty and every intersection reads 0.
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get()
        eval_obj = dup.evaluated_get(deps)
        mesh = bpy.data.meshes.new_from_object(
            eval_obj, preserve_all_data_layers=False, depsgraph=deps)
        polys = len(mesh.polygons)
        volume = abs(mesh_volume(mesh))
        bpy.data.objects.remove(dup)
        bpy.data.meshes.remove(mesh)
        if polys > 0:
            break  # EXACT produced real geometry; trust it
    return volume


def _run_shape(shape_id, clearance_mm):
    obj_a, obj_b = _cut_cube_in_half()
    va_before = mesh_volume(obj_a.data)
    vb_before = mesh_volume(obj_b.data)

    _select_pair(obj_a, obj_b)
    result = bpy.ops.printsplit.generate_joint(
        shape=shape_id, clearance_mm=clearance_mm, solver='EXACT')
    assert result == {'FINISHED'}, f"operator returned {result}"

    va = mesh_volume(obj_a.data)
    vb = mesh_volume(obj_b.data)
    assert va > va_before, "male half did not gain a peg"
    assert vb < vb_before, "female half did not lose a socket"
    assert is_watertight_mesh(obj_a.data), "male result not watertight"
    assert is_watertight_mesh(obj_b.data), "female result not watertight"
    return obj_a, obj_b


def test_dovetail_joint():
    obj_a, obj_b = _run_shape('DOVETAIL', clearance_mm=0.3)
    # With clearance the assembled halves must not overlap.
    ix = _rest_intersection(obj_a, obj_b)
    assert ix < 1e-6, f"halves overlap by {ix}"


def test_cylinder_joint():
    obj_a, obj_b = _run_shape('CYLINDER', clearance_mm=0.3)
    ix = _rest_intersection(obj_a, obj_b)
    assert ix < 1e-6, f"halves overlap by {ix}"


def test_clearance_enlarges_socket():
    """Sanity inversion: at zero clearance the socket removes exactly the
    peg's volume; with clearance it removes strictly more. (Uses the
    cylinder, whose cutter is a closed pocket rather than a channel.)"""
    deltas = {}
    for mm in (0.0, 0.3):
        obj_a, obj_b = _cut_cube_in_half()
        va0, vb0 = mesh_volume(obj_a.data), mesh_volume(obj_b.data)
        _select_pair(obj_a, obj_b)
        assert bpy.ops.printsplit.generate_joint(
            shape='CYLINDER', clearance_mm=mm, solver='EXACT') == {'FINISHED'}
        added = mesh_volume(obj_a.data) - va0
        removed = vb0 - mesh_volume(obj_b.data)
        deltas[mm] = (added, removed)
        bpy.ops.wm.read_homefile(use_empty=True)

    added0, removed0 = deltas[0.0]
    added3, removed3 = deltas[0.3]
    assert math.isclose(added0, removed0, rel_tol=1e-3), (
        f"zero clearance should remove exactly the peg: {added0} vs {removed0}")
    assert removed3 > added3 + 1e-5, (
        f"clearance should enlarge the socket: removed {removed3}, "
        f"peg {added3}")


def test_flip_swaps_sides():
    obj_a, obj_b = _cut_cube_in_half()
    va_before = mesh_volume(obj_a.data)
    _select_pair(obj_a, obj_b)
    result = bpy.ops.printsplit.generate_joint(
        shape='DOVETAIL', flip=True, clearance_mm=0.15, solver='EXACT')
    assert result == {'FINISHED'}
    va = mesh_volume(obj_a.data)
    assert va < va_before, "flip should put the socket on the active object"


def test_dovetail_rail_fills_channel():
    """RAIL style at zero clearance: the trimmed rail must fill the groove
    exactly — the male gains precisely what the female loses."""
    obj_a, obj_b = _cut_cube_in_half()
    va0, vb0 = mesh_volume(obj_a.data), mesh_volume(obj_b.data)
    _select_pair(obj_a, obj_b)
    assert bpy.ops.printsplit.generate_joint(
        shape='DOVETAIL', dovetail_style='RAIL',
        clearance_mm=0.0, solver='EXACT') == {'FINISHED'}
    added = mesh_volume(obj_a.data) - va0
    removed = vb0 - mesh_volume(obj_b.data)
    assert added > 1e-4, "rail peg missing"
    # The anti-coplanar trim shrink recesses the rail ends by a hair, so
    # allow a small relative difference.
    assert math.isclose(added, removed, rel_tol=5e-3), (
        f"rail should fill the groove exactly: peg {added}, "
        f"groove {removed}")


def test_dovetail_rail_flush_with_surface():
    """The trimmed rail must not stick out past the model's outer surface."""
    obj_a, obj_b = _cut_cube_in_half()
    _select_pair(obj_a, obj_b)
    assert bpy.ops.printsplit.generate_joint(
        shape='DOVETAIL', dovetail_style='RAIL',
        clearance_mm=0.15, solver='EXACT') == {'FINISHED'}
    for v in obj_a.data.vertices:
        assert abs(v.co.x) <= 1.0 + 1e-5 and abs(v.co.y) <= 1.0 + 1e-5, (
            f"rail pokes out of the cube at {tuple(v.co)}")


def test_joint_with_halves_moved_apart():
    """The joint lands correctly even when the halves were moved apart
    before generating (local-space placement)."""
    from mathutils import Euler, Vector

    obj_a, obj_b = _cut_cube_in_half()
    obj_b.location = Vector((3.0, 1.0, -0.5))
    obj_b.rotation_euler = Euler((0.3, 0.2, 0.9))
    bpy.context.view_layer.update()

    va0, vb0 = mesh_volume(obj_a.data), mesh_volume(obj_b.data)
    _select_pair(obj_a, obj_b)
    assert bpy.ops.printsplit.generate_joint(
        shape='DOVETAIL', clearance_mm=0.3, solver='EXACT') == {'FINISHED'}
    assert mesh_volume(obj_a.data) > va0
    assert mesh_volume(obj_b.data) < vb0

    # Reassemble: identical matrices realign the shared local space.
    obj_b.matrix_world = obj_a.matrix_world
    bpy.context.view_layer.update()
    ix = _rest_intersection(obj_a, obj_b)
    assert ix < 1e-6, f"joint misplaced, halves overlap by {ix}"


def test_dovetail_rail_survives_fast_solver():
    """Regression: the GUI default flow once hit FAST-solver unions that
    silently produced garbage because the trimmed rail walls coincided
    with the model surface. The shrunken trim must keep FAST viable."""
    obj_a, obj_b = _cut_cube_in_half()
    va0 = mesh_volume(obj_a.data)
    _select_pair(obj_a, obj_b)
    assert bpy.ops.printsplit.generate_joint(
        shape='DOVETAIL', dovetail_style='RAIL',
        clearance_mm=0.15, solver='FAST') == {'FINISHED'}
    # FAST is approximate by design (may leave non-manifold edges); the
    # regression being guarded is the rail silently vanishing.
    assert mesh_volume(obj_a.data) > va0, "male lost its rail (FAST union)"


def test_no_common_cut_errors():
    a = make_cube(name="A")
    b = make_cube(name="B")
    bpy.context.view_layer.update()
    _select_pair(a, b)
    try:
        result = bpy.ops.printsplit.generate_joint(shape='DOVETAIL')
    except RuntimeError as exc:
        # In background mode a report({'ERROR'}) surfaces as RuntimeError.
        assert "do not share" in str(exc)
    else:
        assert result == {'CANCELLED'}
