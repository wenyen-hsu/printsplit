# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate an interlocking joint across the last cut shared by the two
selected halves. The geometry plan comes from JointParamsMixin (shared
with the preview operator); this operator just applies it and records
history. All parameters live on the operator so the F9 redo panel gives
live adjustment."""

import bpy

from ..core import history
from ..core.booleans import apply_boolean
from .joint_params import JointError, JointParamsMixin


def make_connector_object(context, plan):
    """Create the standalone connector object from a plan: base solid
    first, remaining shells UNIONed on so the result is one watertight
    printable body. Returns the object (parked beside the seam)."""
    base_bm = plan.connector_bms[0]
    mesh = bpy.data.meshes.new(f"{plan.male.name}.connector")
    base_bm.to_mesh(mesh)
    obj = bpy.data.objects.new(f"{plan.male.name}.connector", mesh)
    obj.matrix_world = plan.connector_matrix
    collections = plan.male.users_collection or [context.scene.collection]
    for coll in collections:
        coll.objects.link(obj)

    for bm in plan.connector_bms[1:]:
        apply_boolean(context, obj, bm, plan.connector_matrix,
                      'UNION', 'EXACT')

    # Remember the mating pose, then park the connector beside the seam
    # so it isn't buried inside the sockets.
    obj["ps_mating_matrix"] = [v for row in plan.connector_matrix
                               for v in row]
    x_axis = plan.connector_matrix.to_3x3().col[0].normalized()
    offset = plan.section.extent_t * 0.75 + plan.size.width
    obj.matrix_world.translation += x_axis * offset
    obj.select_set(False)
    return obj


class PRINTSPLIT_OT_generate_joint(JointParamsMixin, bpy.types.Operator):
    bl_idname = "printsplit.generate_joint"
    bl_label = "Generate Joint"
    bl_description = ("Create a male/female joint across the cut shared by "
                      "the two selected halves")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if getattr(context.scene, "printsplit_preview", None) and \
                context.scene.printsplit_preview.active:
            return False
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        return len(meshes) == 2 and context.mode == 'OBJECT'

    def invoke(self, context, event):
        self.seed_defaults(context)
        return self.execute(context)

    def execute(self, context):
        try:
            plan = self.build_plan(context)
        except JointError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        for msg in plan.warnings:
            self.report({'WARNING'}, msg)

        use_self = not plan.shape.fast_ok
        old_meshes = []
        try:
            for op in plan.ops:
                old_meshes.append(apply_boolean(
                    context, op.target, op.bm, op.matrix,
                    op.operation, plan.solver, use_self=use_self))
                op.bm = None  # consumed (apply_boolean does not free)
        finally:
            plan_ops = plan.ops
            for op in plan_ops:
                if op.bm is not None:
                    op.bm.free()
                    op.bm = None

        # apply_boolean returns the PREVIOUS mesh per call; for history we
        # need one backup per OBJECT (the first swap for each target).
        seen = {}
        objects = []
        backups = []
        for op, old in zip(plan_ops, old_meshes):
            if op.target not in seen:
                seen[op.target] = old
                objects.append(op.target)
                backups.append(old)
            else:
                # Intermediate mesh from a multi-op target: not needed.
                if old.users == 0:
                    bpy.data.meshes.remove(old)

        extra_objects = []
        if plan.connector_bms:
            extra_objects.append(make_connector_object(context, plan))
            plan.connector_bms = []

        history.push_joint(context.scene, plan.cut_id, objects, backups,
                           extra_objects=extra_objects)
        self.report(
            {'INFO'},
            f"{plan.shape.label} joint between '{plan.male.name}' and "
            f"'{plan.female.name}'")
        return {'FINISHED'}

    def draw(self, context):
        self.draw_joint_props(self.layout)


def register():
    bpy.utils.register_class(PRINTSPLIT_OT_generate_joint)


def unregister():
    bpy.utils.unregister_class(PRINTSPLIT_OT_generate_joint)
