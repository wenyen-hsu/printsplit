# SPDX-License-Identifier: GPL-3.0-or-later
"""Boolean application for the joint step. The cut itself never uses
booleans; only UNIONing the peg and DIFFERENCEing the socket do."""

import bpy


def apply_boolean(context, target_obj, operand_bm, matrix_world,
                  operation, solver, use_self=False):
    """Apply ``operand_bm`` (in joint local space, placed by
    ``matrix_world``) onto ``target_obj`` with a boolean modifier evaluated
    through the depsgraph — no bpy.ops, works headless.

    Returns the target's PREVIOUS mesh datablock (for history); the target
    ends up with a new mesh containing the boolean result.
    """
    operand_mesh = bpy.data.meshes.new("_ps_operand")
    operand_bm.to_mesh(operand_mesh)
    operand_obj = bpy.data.objects.new("_ps_operand", operand_mesh)
    operand_obj.matrix_world = matrix_world
    context.scene.collection.objects.link(operand_obj)

    mod = target_obj.modifiers.new(name="PrintSplit Joint", type='BOOLEAN')
    mod.object = operand_obj
    mod.operation = operation
    mod.solver = solver
    if use_self and solver == 'EXACT':
        # Movable-joint operands are several overlapping closed shells in
        # one mesh (stem+sphere, box+cylinders); EXACT only resolves that
        # winding correctly with self-intersection handling on. Left off
        # for single-shell operands, where it can degrade the result.
        mod.use_self = True

    try:
        old_mesh = swap_evaluated_mesh(context, target_obj)
    finally:
        target_obj.modifiers.remove(mod)
        bpy.data.objects.remove(operand_obj)
        bpy.data.meshes.remove(operand_mesh)
    return old_mesh


def swap_evaluated_mesh(context, target_obj):
    """Capture the target's fully evaluated mesh (modifiers applied),
    swap it in as the object data, and return the PREVIOUS mesh
    datablock (for history). The caller removes the modifiers."""
    deps = context.evaluated_depsgraph_get()
    eval_obj = target_obj.evaluated_get(deps)
    new_mesh = bpy.data.meshes.new_from_object(
        eval_obj, preserve_all_data_layers=True, depsgraph=deps)
    old_mesh = target_obj.data
    new_mesh.name = old_mesh.name + ".joint"
    target_obj.data = new_mesh
    return old_mesh


def intersect_with_object(context, operand_bm, matrix_world, trim_obj,
                          use_self=False):
    """Return ``operand_bm ∩ trim_obj`` as a NEW bmesh, still in the
    operand's local (joint) space. Used to clip an overlong rail peg flush
    with the model's outer surface. The input bmesh is left untouched."""
    import bmesh

    operand_mesh = bpy.data.meshes.new("_ps_trim_operand")
    operand_bm.to_mesh(operand_mesh)
    operand_obj = bpy.data.objects.new("_ps_trim_operand", operand_mesh)
    operand_obj.matrix_world = matrix_world
    context.scene.collection.objects.link(operand_obj)

    mod = operand_obj.modifiers.new(name="trim", type='BOOLEAN')
    mod.object = trim_obj
    mod.operation = 'INTERSECT'
    mod.solver = 'EXACT'
    if use_self:
        mod.use_self = True  # multi-shell operands (e.g. hinge barrel)

    try:
        deps = context.evaluated_depsgraph_get()
        eval_obj = operand_obj.evaluated_get(deps)
        new_mesh = bpy.data.meshes.new_from_object(
            eval_obj, preserve_all_data_layers=False, depsgraph=deps)
    finally:
        bpy.data.objects.remove(operand_obj)
        bpy.data.meshes.remove(operand_mesh)

    bm = bmesh.new()
    bm.from_mesh(new_mesh)
    bpy.data.meshes.remove(new_mesh)
    return bm
