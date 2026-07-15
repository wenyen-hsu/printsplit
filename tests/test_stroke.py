# SPDX-License-Identifier: GPL-3.0-or-later
"""stroke_to_planes: the screen-stroke → cutting-plane math, exercised
through duck-typed region/rv3d stand-ins (bpy_extras.view3d_utils is pure
Python, so orthographic and perspective projections both work headless)."""

import math

import bpy
from mathutils import Matrix, Vector

from printsplit.core.cutting import CutPlane, cut_object
from printsplit.operators.draw_cut import stroke_to_planes
from printsplit.utils.mesh_utils import is_watertight_mesh, mesh_volume

from test_cutting import make_cube


class _FakeRegion:
    width = 1000
    height = 1000


class _FakeRV3D:
    """Orthographic view down -Y (Blender's Front view)."""

    is_perspective = False
    view_perspective = 'ORTHO'

    def __init__(self, ortho_scale=4.0, depth=10.0):
        # view_matrix maps world -> view space (camera looks down -Z of
        # view space). Front view: world +X -> view +X, world +Z -> view
        # +Y, world -Y -> view -Z. Camera sits at world (0, -depth, 0).
        rot = Matrix((
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, -1.0, 0.0, -depth),
            (0.0, 0.0, 0.0, 1.0),
        ))
        self.view_matrix = rot
        near, far = -100.0, 100.0
        s = 2.0 / ortho_scale
        proj = Matrix((
            (s, 0.0, 0.0, 0.0),
            (0.0, s, 0.0, 0.0),
            (0.0, 0.0, -2.0 / (far - near), -(far + near) / (far - near)),
            (0.0, 0.0, 0.0, 1.0),
        ))
        self.window_matrix = proj
        self.perspective_matrix = proj @ rot


def _screen(x_world, z_world, ortho_scale=4.0):
    """World (x, z) on the y=0 plane -> region pixels for _FakeRV3D."""
    u = (x_world / (ortho_scale / 2.0) + 1.0) * 0.5 * _FakeRegion.width
    v = (z_world / (ortho_scale / 2.0) + 1.0) * 0.5 * _FakeRegion.height
    return (u, v)


def test_straight_stroke_cuts_cube():
    obj = make_cube(size=2.0, subdivisions=3)
    bpy.context.view_layer.update()
    original_volume = mesh_volume(obj.data)

    region, rv3d = _FakeRegion(), _FakeRV3D()
    # Horizontal stroke across the cube at world z = 0.25.
    points = [_screen(-1.8, 0.25), _screen(1.8, 0.25)]
    planes = stroke_to_planes(
        region, rv3d, points,
        focus_world=Vector((0, 0, 0)), extend=7.0)
    assert len(planes) == 1

    obj_a, obj_b = cut_object(obj, planes, cut_id=1)
    assert is_watertight_mesh(obj_a.data)
    assert is_watertight_mesh(obj_b.data)
    va, vb = mesh_volume(obj_a.data), mesh_volume(obj_b.data)
    assert math.isclose(va + vb, original_volume, rel_tol=1e-4)
    # Cut at z=0.25 on a 2x2x2 cube: the parts are 0.75/2 and 1.25/2 of
    # the volume (which one is A depends on the stroke direction).
    expected = sorted([original_volume * 0.375, original_volume * 0.625])
    got = sorted([va, vb])
    for e, g in zip(expected, got):
        assert math.isclose(e, g, rel_tol=1e-3), f"expected {e}, got {g}"


def test_freehand_stroke_cuts_cube():
    obj = make_cube(size=2.0, subdivisions=4)
    bpy.context.view_layer.update()
    original_volume = mesh_volume(obj.data)

    region, rv3d = _FakeRegion(), _FakeRV3D()
    # V-shaped stroke: down then up, crossing the whole cube.
    points = [_screen(-1.8, 0.6), _screen(0.0, -0.4), _screen(1.8, 0.6)]
    planes = stroke_to_planes(
        region, rv3d, points,
        focus_world=Vector((0, 0, 0)), extend=7.0)
    assert len(planes) == 2
    # The two slabs must share the junction miter plane.
    assert planes[0].end_co is not None and planes[1].start_co is not None

    obj_a, obj_b = cut_object(obj, planes, cut_id=1)
    assert is_watertight_mesh(obj_a.data)
    assert is_watertight_mesh(obj_b.data)
    va, vb = mesh_volume(obj_a.data), mesh_volume(obj_b.data)
    assert math.isclose(va + vb, original_volume, rel_tol=1e-4)
    assert va > 0.1 and vb > 0.1


def test_stroke_missing_mesh_errors():
    from printsplit.core.cutting import CutError

    obj = make_cube(size=2.0)
    bpy.context.view_layer.update()
    region, rv3d = _FakeRegion(), _FakeRV3D()
    points = [_screen(-1.8, 1.9), _screen(1.8, 1.9)]  # above the cube
    planes = stroke_to_planes(
        region, rv3d, points,
        focus_world=Vector((0, 0, 0)), extend=7.0)
    try:
        cut_object(obj, planes, cut_id=1)
    except CutError:
        pass
    else:
        raise AssertionError("expected CutError for a stroke off the mesh")
