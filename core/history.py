# SPDX-License-Identifier: GPL-3.0-or-later
"""Non-destructive history: every cut and joint keeps the previous mesh
datablock(s) alive (fake user, unlinked) so the operation can be reverted
even after saving and reopening the file."""

import bpy
from mathutils import Matrix

_SEP = ";"


def _flatten_matrix(m):
    return [m[i][j] for i in range(4) for j in range(4)]


def _unflatten_matrix(values):
    return Matrix([values[i * 4:i * 4 + 4] for i in range(4)])


def snapshot_cut(scene, cut_id, obj):
    """Record a cut BEFORE it happens; returns the entry to be completed
    with result names after the cut succeeds."""
    entry = scene.printsplit_history.add()
    entry.kind = 'CUT'
    entry.cut_id = cut_id
    entry.original_name = obj.name
    mesh = obj.data
    mesh.use_fake_user = True
    entry.backup_mesh_names = mesh.name
    entry.matrix_world = _flatten_matrix(obj.matrix_world)
    entry.collection_names = _SEP.join(c.name for c in obj.users_collection)
    return entry


def complete_cut(scene, entry, result_objects):
    entry.result_object_names = _SEP.join(o.name for o in result_objects)
    _enforce_depth(scene)


def discard_entry(scene, entry):
    for i, e in enumerate(scene.printsplit_history):
        if e == entry:
            scene.printsplit_history.remove(i)
            break


def push_joint(scene, cut_id, objects, old_meshes, extra_objects=()):
    """Record a joint: ``old_meshes[i]`` is the mesh ``objects[i]`` had
    before the boolean was applied. ``extra_objects`` are standalone
    objects created alongside (connectors) that undo must delete."""
    for mesh in old_meshes:
        mesh.use_fake_user = True
    entry = scene.printsplit_history.add()
    entry.kind = 'JOINT'
    entry.cut_id = cut_id
    entry.backup_mesh_names = _SEP.join(m.name for m in old_meshes)
    entry.result_object_names = _SEP.join(o.name for o in objects)
    entry.extra_object_names = _SEP.join(o.name for o in extra_objects)
    _enforce_depth(scene)


def undo_last(scene):
    """Revert the newest history entry. Returns a human-readable message.
    Raises RuntimeError when the entry can no longer be applied."""
    history = scene.printsplit_history
    if not history:
        raise RuntimeError("Nothing to undo")
    entry = history[len(history) - 1]

    if entry.kind == 'JOINT':
        _undo_joint(entry)
        msg = "Removed joint"
    else:
        _undo_cut(scene, entry)
        msg = f"Undid cut, restored '{entry.original_name}'"
    history.remove(len(history) - 1)
    return msg


def undo_all(scene):
    count = 0
    while len(scene.printsplit_history):
        undo_last(scene)
        count += 1
    return f"Reverted {count} operation(s)"


def _undo_joint(entry):
    for name in entry.extra_object_names.split(_SEP):
        obj = bpy.data.objects.get(name) if name else None
        if obj is not None:
            mesh = obj.data
            bpy.data.objects.remove(obj)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)

    names = entry.result_object_names.split(_SEP)
    backups = entry.backup_mesh_names.split(_SEP)
    for obj_name, mesh_name in zip(names, backups):
        obj = bpy.data.objects.get(obj_name)
        backup = bpy.data.meshes.get(mesh_name)
        if obj is None or backup is None:
            raise RuntimeError(
                f"Cannot undo joint: '{obj_name}' or its backup is gone")
        current = obj.data
        obj.data = backup
        backup.use_fake_user = False
        if current.users == 0:
            bpy.data.meshes.remove(current)


def _undo_cut(scene, entry):
    backup = bpy.data.meshes.get(entry.backup_mesh_names)
    if backup is None:
        raise RuntimeError("Cannot undo cut: the backup mesh is gone")

    for name in entry.result_object_names.split(_SEP):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            mesh = obj.data
            bpy.data.objects.remove(obj)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)

    restored = bpy.data.objects.new(entry.original_name, backup)
    backup.use_fake_user = False
    restored.matrix_world = _unflatten_matrix(list(entry.matrix_world))
    linked = False
    for coll_name in entry.collection_names.split(_SEP):
        coll = bpy.data.collections.get(coll_name) if coll_name else None
        if coll is not None:
            coll.objects.link(restored)
            linked = True
    if not linked:
        scene.collection.objects.link(restored)


def _enforce_depth(scene):
    from ..preferences import get_prefs

    prefs = get_prefs(bpy.context)
    depth = prefs.history_depth if prefs else 5
    history = scene.printsplit_history
    while len(history) > depth:
        entry = history[0]
        for mesh_name in entry.backup_mesh_names.split(_SEP):
            mesh = bpy.data.meshes.get(mesh_name)
            if mesh is not None:
                mesh.use_fake_user = False
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
        history.remove(0)
