# SPDX-License-Identifier: GPL-3.0-or-later
"""PrintSplit — split meshes and generate interlocking joints for 3D printing.

Draw a line across a mesh in the viewport to cut it into two watertight
pieces, then generate a male/female joint (dovetail, pin, ...) across the
cut so the printed parts snap together without glue.
"""

from . import preferences, properties
from .operators import draw_cut, generate_joint, history_ops, preview_joint
from .ui import panel

_MODULES = (
    preferences,
    properties,
    draw_cut,
    generate_joint,
    history_ops,
    preview_joint,
    panel,
)


def register():
    for mod in _MODULES:
        mod.register()


def unregister():
    for mod in reversed(_MODULES):
        mod.unregister()
