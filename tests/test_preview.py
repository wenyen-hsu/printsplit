# SPDX-License-Identifier: GPL-3.0-or-later
"""Joint preview lifecycle: preview leaves the source meshes untouched
and blocks other operations; confirm applies and records history;
cancel restores the scene exactly."""

import math

import bpy

from printsplit.utils.mesh_utils import mesh_volume

from test_cutting import make_cube
from test_joints import _select_pair
from test_movable_joints import _cut_in_half


def _setup():
    obj = make_cube(size=2.0, subdivisions=2, name="Body")
    obj_a, obj_b = _cut_in_half(obj)
    _select_pair(obj_a, obj_b)
    return obj_a, obj_b


def _preview_objects():
    return [o for o in bpy.data.objects if o.name.startswith("_PS_Preview")]


def test_preview_is_non_destructive_and_blocks():
    obj_a, obj_b = _setup()
    va, vb = mesh_volume(obj_a.data), mesh_volume(obj_b.data)

    assert bpy.ops.printsplit.preview_joint(
        shape='DOVETAIL', solver='EXACT') == {'FINISHED'}

    assert bpy.context.scene.printsplit_preview.active
    assert mesh_volume(obj_a.data) == va, "preview must not touch meshes"
    assert mesh_volume(obj_b.data) == vb
    assert len(_preview_objects()) >= 2
    mods_a = [m for m in obj_a.modifiers if m.name.startswith("PrintSplit")]
    mods_b = [m for m in obj_b.modifiers if m.name.startswith("PrintSplit")]
    assert mods_a and mods_b, "preview modifiers missing"

    # Other operations are blocked while the preview is pending.
    assert not bpy.ops.printsplit.generate_joint.poll()
    assert not bpy.ops.printsplit.draw_cut.poll()

    bpy.ops.printsplit.cancel_joint()


def test_confirm_applies_and_records_history():
    obj_a, obj_b = _setup()
    va, vb = mesh_volume(obj_a.data), mesh_volume(obj_b.data)
    history_len = len(bpy.context.scene.printsplit_history)

    assert bpy.ops.printsplit.preview_joint(
        shape='CYLINDER', clearance_mm=0.3,
        solver='EXACT') == {'FINISHED'}
    assert bpy.ops.printsplit.confirm_joint() == {'FINISHED'}

    assert not bpy.context.scene.printsplit_preview.active
    assert not _preview_objects(), "operands must be cleaned up"
    assert not [m for m in obj_a.modifiers], "modifiers must be removed"
    assert mesh_volume(obj_a.data) > va, "peg missing after confirm"
    assert mesh_volume(obj_b.data) < vb, "socket missing after confirm"
    assert len(bpy.context.scene.printsplit_history) == history_len + 1

    # The confirmed joint undoes like a directly generated one.
    assert bpy.ops.printsplit.undo_last() == {'FINISHED'}
    assert math.isclose(mesh_volume(obj_a.data), va, rel_tol=1e-9)
    assert math.isclose(mesh_volume(obj_b.data), vb, rel_tol=1e-9)


def test_cancel_restores_everything():
    obj_a, obj_b = _setup()
    va, vb = mesh_volume(obj_a.data), mesh_volume(obj_b.data)
    object_count = len(bpy.data.objects)

    assert bpy.ops.printsplit.preview_joint(
        shape='BALL_SOCKET', solver='EXACT') == {'FINISHED'}
    assert bpy.ops.printsplit.cancel_joint() == {'FINISHED'}

    assert not bpy.context.scene.printsplit_preview.active
    assert len(bpy.data.objects) == object_count
    assert mesh_volume(obj_a.data) == va
    assert mesh_volume(obj_b.data) == vb
    assert not [m for m in obj_a.modifiers]
    assert not [m for m in obj_b.modifiers]


def test_preview_double_ball_creates_connector_on_confirm():
    obj_a, obj_b = _setup()
    assert bpy.ops.printsplit.preview_joint(
        shape='DOUBLE_BALL', solver='EXACT') == {'FINISHED'}
    connector = bpy.data.objects.get(f"{obj_a.name}.connector")
    assert connector is not None, "connector should appear in preview"

    assert bpy.ops.printsplit.confirm_joint() == {'FINISHED'}
    assert bpy.data.objects.get(f"{obj_a.name}.connector") is not None

    # Undo removes the connector too.
    assert bpy.ops.printsplit.undo_last() == {'FINISHED'}
    assert bpy.data.objects.get(f"{obj_a.name}.connector") is None
