# SPDX-License-Identifier: GPL-3.0-or-later
"""N-panel in the 3D viewport sidebar."""

import bpy


class VIEW3D_PT_printsplit(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PrintSplit"
    bl_label = "PrintSplit"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.printsplit

        box = layout.box()
        box.label(text="Cut", icon='MOD_LINEART')
        row = box.row(align=True)
        row.prop(settings, "cut_mode", expand=True)
        box.operator("printsplit.draw_cut", icon='GREASEPENCIL')

        box = layout.box()
        box.label(text="Joint", icon='SNAP_ON')
        preview = context.scene.printsplit_preview
        if preview.active:
            row = box.row(align=True)
            row.alert = True
            row.operator("printsplit.confirm_joint", icon='CHECKMARK')
            row.operator("printsplit.cancel_joint", icon='X')
            box.label(text="Preview pending — confirm or cancel",
                      icon='INFO')
        else:
            col = box.column()
            col.enabled = _two_meshes_selected(context)
            col.operator("printsplit.generate_joint", icon='MOD_BOOLEAN')
            col.operator("printsplit.preview_joint", icon='HIDE_OFF')
            if not _two_meshes_selected(context):
                box.label(text="Select both cut halves", icon='INFO')

        history = context.scene.printsplit_history
        box = layout.box()
        box.label(text=f"History ({len(history)})", icon='RECOVER_LAST')
        if history:
            col = box.column(align=True)
            for entry in reversed(list(history)[-5:]):
                if entry.kind == 'CUT':
                    col.label(
                        text=f"Cut {entry.cut_id} — {entry.original_name}",
                        icon='MOD_LINEART')
                else:
                    col.label(text=f"Joint on cut {entry.cut_id}",
                              icon='SNAP_ON')
            row = box.row(align=True)
            row.operator("printsplit.undo_last", icon='LOOP_BACK')
            row.operator("printsplit.delete_all_cuts", icon='TRASH')


def _two_meshes_selected(context):
    return len([o for o in context.selected_objects
                if o.type == 'MESH']) == 2


def register():
    bpy.utils.register_class(VIEW3D_PT_printsplit)


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_printsplit)
