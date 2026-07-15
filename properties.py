# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-level settings and the persistent cut/joint history stack."""

import bpy


class PS_HistoryEntry(bpy.types.PropertyGroup):
    cut_id: bpy.props.IntProperty()
    kind: bpy.props.EnumProperty(
        items=[
            ('CUT', "Cut", "A mesh split"),
            ('JOINT', "Joint", "A generated joint"),
        ],
    )
    original_name: bpy.props.StringProperty()
    # Semicolon-joined lists; kept simple on purpose.
    backup_mesh_names: bpy.props.StringProperty()
    result_object_names: bpy.props.StringProperty()
    matrix_world: bpy.props.FloatVectorProperty(size=16)
    collection_names: bpy.props.StringProperty()
    # Standalone objects created with the entry (e.g. a connector) that
    # an undo must also remove.
    extra_object_names: bpy.props.StringProperty()


class PS_PreviewState(bpy.types.PropertyGroup):
    """A pending (unapplied) joint preview: boolean modifiers live on the
    targets; the operands are wireframe helper objects."""

    active: bpy.props.BoolProperty(default=False)
    # Parallel semicolon-joined lists, one entry per boolean operation.
    target_names: bpy.props.StringProperty()
    operand_names: bpy.props.StringProperty()
    modifier_names: bpy.props.StringProperty()
    connector_name: bpy.props.StringProperty()
    cut_id: bpy.props.IntProperty()


class PS_SceneSettings(bpy.types.PropertyGroup):
    cut_mode: bpy.props.EnumProperty(
        name="Cut Mode",
        items=[
            ('STRAIGHT', "Straight", "Cut along a straight line"),
            ('FREEHAND', "Freehand", "Cut along a freehand stroke"),
        ],
        default='STRAIGHT',
    )
    next_cut_id: bpy.props.IntProperty(default=1)


_CLASSES = (PS_HistoryEntry, PS_PreviewState, PS_SceneSettings)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.printsplit = bpy.props.PointerProperty(type=PS_SceneSettings)
    bpy.types.Scene.printsplit_history = bpy.props.CollectionProperty(
        type=PS_HistoryEntry
    )
    bpy.types.Scene.printsplit_preview = bpy.props.PointerProperty(
        type=PS_PreviewState
    )


def unregister():
    del bpy.types.Scene.printsplit_preview
    del bpy.types.Scene.printsplit_history
    del bpy.types.Scene.printsplit
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
