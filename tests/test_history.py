# SPDX-License-Identifier: GPL-3.0-or-later
"""History: undo restores objects and meshes exactly; delete-all rewinds."""

import math

import bpy
from mathutils import Vector

from printsplit.core import history
from printsplit.core.cutting import CutPlane, cut_object
from printsplit.utils.mesh_utils import mesh_volume

from test_cutting import make_cube


def _cut_with_history(obj, z, cut_id):
    scene = bpy.context.scene
    entry = history.snapshot_cut(scene, cut_id, obj)
    obj_a, obj_b = cut_object(
        obj, [CutPlane(Vector((0, 0, z)), Vector((0, 0, 1)))], cut_id)
    history.complete_cut(scene, entry, (obj_a, obj_b))
    return obj_a, obj_b


def test_undo_cut_restores_original():
    obj = make_cube(size=2.0, subdivisions=1, name="Widget")
    vcount = len(obj.data.vertices)
    volume = mesh_volume(obj.data)

    obj_a, obj_b = _cut_with_history(obj, 0.2, cut_id=1)
    assert bpy.data.objects.get("Widget") is None
    assert len(bpy.context.scene.printsplit_history) == 1

    result = bpy.ops.printsplit.undo_last()
    assert result == {'FINISHED'}

    restored = bpy.data.objects.get("Widget")
    assert restored is not None, "original object not restored"
    assert len(restored.data.vertices) == vcount
    assert math.isclose(mesh_volume(restored.data), volume, rel_tol=1e-9)
    assert bpy.data.objects.get("Widget_A") is None
    assert bpy.data.objects.get("Widget_B") is None
    assert len(bpy.context.scene.printsplit_history) == 0


def test_undo_joint_restores_halves():
    obj = make_cube(size=2.0, subdivisions=2, name="Body")
    obj_a, obj_b = _cut_with_history(obj, 0.0, cut_id=1)
    bpy.context.view_layer.update()
    va = mesh_volume(obj_a.data)
    vb = mesh_volume(obj_b.data)

    for o in bpy.context.scene.objects:
        o.select_set(False)
    obj_a.select_set(True)
    obj_b.select_set(True)
    bpy.context.view_layer.objects.active = obj_a
    assert bpy.ops.printsplit.generate_joint(shape='DOVETAIL') == {'FINISHED'}
    assert len(bpy.context.scene.printsplit_history) == 2
    assert mesh_volume(obj_a.data) != va

    assert bpy.ops.printsplit.undo_last() == {'FINISHED'}
    assert math.isclose(mesh_volume(obj_a.data), va, rel_tol=1e-9)
    assert math.isclose(mesh_volume(obj_b.data), vb, rel_tol=1e-9)
    assert len(bpy.context.scene.printsplit_history) == 1


def test_delete_all_rewinds_everything():
    obj = make_cube(size=2.0, subdivisions=2, name="Widget")
    volume = mesh_volume(obj.data)

    obj_a, obj_b = _cut_with_history(obj, 0.3, cut_id=1)
    # Cut the upper half (z in [0.3, 1]) again.
    _cut_with_history(obj_a, 0.6, cut_id=2)
    assert len(bpy.context.scene.printsplit_history) == 2

    assert bpy.ops.printsplit.delete_all_cuts() == {'FINISHED'}
    restored = bpy.data.objects.get("Widget")
    assert restored is not None
    assert math.isclose(mesh_volume(restored.data), volume, rel_tol=1e-9)
    assert len(bpy.context.scene.printsplit_history) == 0
    # Only the restored object remains.
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    assert len(meshes) == 1
