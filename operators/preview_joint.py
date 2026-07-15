# SPDX-License-Identifier: GPL-3.0-or-later
"""Live joint preview: the boolean modifiers are attached UNAPPLIED, so
the viewport shows the true result while parameters are tweaked in the
F9 panel. Confirm captures the evaluated meshes (no rebuild); Cancel
removes everything. While a preview is pending, cutting/generating/undo
are blocked."""

import bpy

from ..core import history
from ..core.booleans import swap_evaluated_mesh
from .generate_joint import make_connector_object
from .joint_params import JointError, JointParamsMixin

_SEP = ";"


def preview_active(context):
    state = getattr(context.scene, "printsplit_preview", None)
    return bool(state and state.active)


def _teardown(scene):
    """Remove preview modifiers, operand objects and any connector."""
    state = scene.printsplit_preview
    targets = state.target_names.split(_SEP)
    modifiers = state.modifier_names.split(_SEP)
    for target_name, mod_name in zip(targets, modifiers):
        obj = bpy.data.objects.get(target_name)
        if obj is not None:
            mod = obj.modifiers.get(mod_name)
            if mod is not None:
                obj.modifiers.remove(mod)
    for name in state.operand_names.split(_SEP):
        obj = bpy.data.objects.get(name) if name else None
        if obj is not None:
            mesh = obj.data
            bpy.data.objects.remove(obj)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
    if state.connector_name:
        obj = bpy.data.objects.get(state.connector_name)
        if obj is not None:
            mesh = obj.data
            bpy.data.objects.remove(obj)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
    state.active = False
    state.target_names = ""
    state.operand_names = ""
    state.modifier_names = ""
    state.connector_name = ""


class PRINTSPLIT_OT_preview_joint(JointParamsMixin, bpy.types.Operator):
    bl_idname = "printsplit.preview_joint"
    bl_label = "Preview Joint"
    bl_description = ("Show the joint as live boolean modifiers; Confirm "
                      "applies them, Cancel discards")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        return len(meshes) == 2 and context.mode == 'OBJECT'

    def invoke(self, context, event):
        self.seed_defaults(context)
        return self.execute(context)

    def execute(self, context):
        scene = context.scene
        if scene.printsplit_preview.active:
            _teardown(scene)  # F9 re-run rebuilds cleanly

        try:
            plan = self.build_plan(context)
        except JointError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        for msg in plan.warnings:
            self.report({'WARNING'}, msg)

        use_self = not plan.shape.fast_ok
        targets, operands, modifiers = [], [], []
        for i, op in enumerate(plan.ops):
            mesh = bpy.data.meshes.new(f"_PS_Preview_{i}")
            op.bm.to_mesh(mesh)
            op.bm.free()
            op.bm = None
            operand = bpy.data.objects.new(f"_PS_Preview_{i}", mesh)
            operand.display_type = 'WIRE'
            operand.hide_render = True
            for coll in (op.target.users_collection
                         or [scene.collection]):
                coll.objects.link(operand)
            operand.parent = op.target
            operand.matrix_parent_inverse = \
                op.target.matrix_world.inverted_safe()
            operand.matrix_world = op.matrix
            operand.select_set(False)

            mod = op.target.modifiers.new(
                name=f"PrintSplit Preview {i}", type='BOOLEAN')
            mod.object = operand
            mod.operation = op.operation
            mod.solver = plan.solver
            if use_self and plan.solver == 'EXACT':
                mod.use_self = True

            targets.append(op.target.name)
            operands.append(operand.name)
            modifiers.append(mod.name)

        connector_name = ""
        if plan.connector_bms:
            connector = make_connector_object(context, plan)
            plan.connector_bms = []
            connector_name = connector.name

        state = scene.printsplit_preview
        state.active = True
        state.target_names = _SEP.join(targets)
        state.operand_names = _SEP.join(operands)
        state.modifier_names = _SEP.join(modifiers)
        state.connector_name = connector_name
        state.cut_id = plan.cut_id
        return {'FINISHED'}

    def draw(self, context):
        self.draw_joint_props(self.layout)


class PRINTSPLIT_OT_confirm_joint(bpy.types.Operator):
    bl_idname = "printsplit.confirm_joint"
    bl_label = "Confirm"
    bl_description = "Apply the previewed joint"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return preview_active(context)

    def execute(self, context):
        scene = context.scene
        state = scene.printsplit_preview
        target_names = state.target_names.split(_SEP)

        objects = []
        backups = []
        for name in target_names:
            if any(o.name == name for o in objects):
                continue
            obj = bpy.data.objects.get(name)
            if obj is None:
                self.report({'ERROR'}, f"Preview target '{name}' is gone")
                _teardown(scene)
                return {'CANCELLED'}
            backups.append(swap_evaluated_mesh(context, obj))
            objects.append(obj)

        connector = (bpy.data.objects.get(state.connector_name)
                     if state.connector_name else None)
        cut_id = state.cut_id
        # Keep the connector: detach it from the teardown state first.
        state.connector_name = ""
        _teardown(scene)

        extra = [connector] if connector is not None else []
        history.push_joint(scene, cut_id, objects, backups,
                           extra_objects=extra)
        self.report({'INFO'}, "Joint applied")
        return {'FINISHED'}


class PRINTSPLIT_OT_cancel_joint(bpy.types.Operator):
    bl_idname = "printsplit.cancel_joint"
    bl_label = "Cancel"
    bl_description = "Discard the previewed joint"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return preview_active(context)

    def execute(self, context):
        _teardown(context.scene)
        return {'FINISHED'}


_CLASSES = (
    PRINTSPLIT_OT_preview_joint,
    PRINTSPLIT_OT_confirm_joint,
    PRINTSPLIT_OT_cancel_joint,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
