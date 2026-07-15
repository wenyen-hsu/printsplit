# SPDX-License-Identifier: GPL-3.0-or-later
"""Undo Last / Delete All Cuts operators backed by core.history."""

import bpy

from ..core import history


class PRINTSPLIT_OT_undo_last(bpy.types.Operator):
    bl_idname = "printsplit.undo_last"
    bl_label = "Undo Last"
    bl_description = "Revert the most recent PrintSplit cut or joint"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from .preview_joint import preview_active

        return (len(context.scene.printsplit_history) > 0
                and not preview_active(context))

    def execute(self, context):
        try:
            msg = history.undo_last(context.scene)
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class PRINTSPLIT_OT_delete_all_cuts(bpy.types.Operator):
    bl_idname = "printsplit.delete_all_cuts"
    bl_label = "Delete All Cuts"
    bl_description = "Revert every PrintSplit cut and joint in this file"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from .preview_joint import preview_active

        return (len(context.scene.printsplit_history) > 0
                and not preview_active(context))

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            msg = history.undo_all(context.scene)
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, msg)
        return {'FINISHED'}


_CLASSES = (PRINTSPLIT_OT_undo_last, PRINTSPLIT_OT_delete_all_cuts)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
