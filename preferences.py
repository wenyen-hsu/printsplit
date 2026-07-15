# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on preferences: persistent defaults for clearance, solver, history."""

import bpy


def solver_items(_self=None, _context=None):
    # EXACT first: with a dynamic items callback the first entry is the
    # default, and FAST fails on the coplanar contacts joints produce.
    items = [
        ('EXACT', "Exact", "Robust boolean solver; slower on dense meshes"),
    ]
    if bpy.app.version >= (4, 5, 0):
        items.append((
            'MANIFOLD', "Manifold",
            "Fast and watertight-guaranteed solver (requires manifold input)",
        ))
    items.append(
        ('FAST', "Fast",
         "Fast boolean solver; may fail on coplanar geometry"))
    return items


class PrintSplitPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    default_clearance: bpy.props.FloatProperty(
        name="Default Clearance (mm)",
        description="Gap between male and female parts. "
        "0.15 mm suits most FDM printers; use 0.05-0.10 mm for resin",
        default=0.15,
        min=0.0,
        max=2.0,
        precision=3,
    )
    default_clearance_movable: bpy.props.FloatProperty(
        name="Articulation Clearance (mm)",
        description="Gap for movable joints (ball, hinge, swivel...). "
        "0.3 mm suits FDM; tighter for resin",
        default=0.3,
        min=0.0,
        max=2.0,
        precision=3,
    )
    default_solver: bpy.props.EnumProperty(
        name="Default Boolean Solver",
        items=solver_items,
    )
    history_depth: bpy.props.IntProperty(
        name="History Depth",
        description="Maximum number of cut/joint backups kept per file. "
        "Older backups are purged to save memory on heavy sculpts",
        default=5,
        min=1,
        max=50,
    )

    def draw(self, _context):
        col = self.layout.column()
        col.prop(self, "default_clearance")
        col.prop(self, "default_solver")
        col.prop(self, "history_depth")


def get_prefs(context):
    """Return the add-on preferences, or None when running unregistered
    (e.g. headless tests importing core modules directly)."""
    try:
        return context.preferences.addons[__package__].preferences
    except KeyError:
        return None


def register():
    bpy.utils.register_class(PrintSplitPreferences)


def unregister():
    bpy.utils.unregister_class(PrintSplitPreferences)
