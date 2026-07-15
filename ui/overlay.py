# SPDX-License-Identifier: GPL-3.0-or-later
"""GPU overlay for the cut stroke (drawn in region pixel space)."""

import gpu
from gpu_extras.batch import batch_for_shader

_STROKE_COLOR = (1.0, 0.6, 0.1, 1.0)
_LINE_WIDTH = 2.5


def draw_stroke(points_2d):
    """POST_PIXEL draw callback body: draw the current stroke polyline."""
    if len(points_2d) < 2:
        return
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": points_2d})
    shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
    shader.uniform_float("lineWidth", _LINE_WIDTH)
    shader.uniform_float("color", _STROKE_COLOR)
    batch.draw(shader)
