# SPDX-License-Identifier: GPL-3.0-or-later
"""The draw-to-cut modal operator: capture a viewport stroke, turn each
stroke segment + the view direction into an exact cutting plane, and split
the active mesh into two watertight halves."""

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

from ..core import history
from ..core.cutting import CutError, CutPlane, cut_object
from ..ui.overlay import draw_stroke
from ..utils.math_utils import plane_from_rays, rdp_simplify

_MIN_PIXEL_STEP = 4.0
_RDP_EPSILON = 3.0
_MAX_SEGMENTS = 60


def stroke_to_planes(region, rv3d, points_2d, focus_world, extend):
    """Build world-space CutPlanes from a 2D stroke.

    focus_world: a point near the object (used to place ray far-points and
    miter plane anchors at a meaningful depth).
    extend: how far past the stroke ends to push the end miter planes so a
    stroke that visually crosses the model always severs it.
    """
    rays = []
    for p in points_2d:
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, p)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, p)
        rays.append((origin, direction.normalized()))

    # Far points at the depth of the object, so miter anchors are stable.
    far = []
    for origin, direction in rays:
        depth = max((focus_world - origin).dot(direction), 1.0)
        far.append(origin + direction * depth)

    # Cutting plane per segment, consistently oriented.
    seg_planes = []
    prev_no = None
    for i in range(len(rays) - 1):
        (oa, da), (ob, db) = rays[i], rays[i + 1]
        plane = plane_from_rays(oa, da, ob, db)
        if plane is None:
            continue
        co, no = plane
        if prev_no is not None and prev_no.dot(no) < 0.0:
            no = -no
        prev_no = no
        seg_planes.append((i, co, no))

    if not seg_planes:
        return []

    # Miter direction at each stroke vertex: the in-plane advance
    # direction(s), orthogonalized against the vertex's view ray so the
    # miter plane contains the ray.
    def advance(i, j):
        return far[j] - far[i]

    n_pts = len(rays)
    miters = []
    for j in range(n_pts):
        d_ray = rays[j][1]
        acc = Vector((0.0, 0.0, 0.0))
        if j > 0:
            a = advance(j - 1, j)
            acc += (a - d_ray * a.dot(d_ray)).normalized()
        if j < n_pts - 1:
            a = advance(j, j + 1)
            acc += (a - d_ray * a.dot(d_ray)).normalized()
        if acc.length < 1e-9:
            miters.append(None)
        else:
            miters.append(acc.normalized())

    planes = []
    for idx, (i, co, no) in enumerate(seg_planes):
        m_start = miters[i]
        m_end = miters[i + 1]
        start_co = far[i]
        end_co = far[i + 1]
        first = idx == 0
        last = idx == len(seg_planes) - 1
        if first and m_start is not None:
            start_co = start_co - m_start * extend
        if last and m_end is not None:
            end_co = end_co + m_end * extend
        planes.append(CutPlane(
            co, no,
            start_co=start_co if m_start is not None else None,
            start_no=m_start,
            end_co=end_co if m_end is not None else None,
            end_no=-m_end if m_end is not None else None,
        ))
    return planes


class PRINTSPLIT_OT_draw_cut(bpy.types.Operator):
    bl_idname = "printsplit.draw_cut"
    bl_label = "Draw Cut"
    bl_description = ("Drag a line across the mesh to cut it into two "
                      "watertight parts (S toggles straight/freehand)")
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[
            ('STRAIGHT', "Straight", ""),
            ('FREEHAND', "Freehand", ""),
        ],
        default='STRAIGHT',
    )

    @classmethod
    def poll(cls, context):
        from .preview_joint import preview_active

        obj = context.active_object
        return (obj is not None and obj.type == 'MESH'
                and context.mode == 'OBJECT'
                and not preview_active(context))

    def invoke(self, context, event):
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "Run from a 3D viewport")
            return {'CANCELLED'}
        self.mode = context.scene.printsplit.cut_mode
        self._obj_name = context.active_object.name
        self._stroke = []
        self._drawing = False
        self._handler = bpy.types.SpaceView3D.draw_handler_add(
            self._draw_callback, (context,), 'WINDOW', 'POST_PIXEL')
        context.window.cursor_modal_set('CROSSHAIR')
        self._update_status(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _draw_callback(self, _context):
        draw_stroke(self._stroke)

    def _update_status(self, context):
        mode = "Straight" if self.mode == 'STRAIGHT' else "Freehand"
        context.workspace.status_text_set(
            f"Cut: drag across the mesh  |  Mode: {mode} (S to toggle)  |  "
            "Esc/RMB: cancel")

    def modal(self, context, event):
        context.area.tag_redraw()

        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}

        if event.type == 'MOUSEMOVE' and self._drawing:
            self._append_point(event)
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                self._drawing = True
                self._stroke = [(event.mouse_region_x, event.mouse_region_y)]
                return {'RUNNING_MODAL'}
            if event.value == 'RELEASE' and self._drawing:
                self._append_point(event, force=True)
                return self._finish(context)

        if event.type == 'S' and event.value == 'PRESS':
            self.mode = ('FREEHAND' if self.mode == 'STRAIGHT'
                         else 'STRAIGHT')
            context.scene.printsplit.cut_mode = self.mode
            self._update_status(context)
            return {'RUNNING_MODAL'}

        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._cleanup(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def _append_point(self, event, force=False):
        p = (float(event.mouse_region_x), float(event.mouse_region_y))
        if self.mode == 'STRAIGHT':
            if len(self._stroke) < 2:
                self._stroke.append(p)
            else:
                self._stroke[1] = p
            return
        if not self._stroke:
            self._stroke.append(p)
            return
        last = self._stroke[-1]
        dist2 = (p[0] - last[0]) ** 2 + (p[1] - last[1]) ** 2
        if force or dist2 >= _MIN_PIXEL_STEP ** 2:
            self._stroke.append(p)

    def _cleanup(self, context):
        if self._handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handler, 'WINDOW')
            self._handler = None
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        context.area.tag_redraw()

    def _finish(self, context):
        self._cleanup(context)

        obj = bpy.data.objects.get(self._obj_name)
        if obj is None:
            return {'CANCELLED'}

        points = self._stroke
        if len(points) < 2:
            self.report({'WARNING'}, "Stroke too short")
            return {'CANCELLED'}
        if self.mode == 'FREEHAND':
            points = rdp_simplify(points, _RDP_EPSILON)
            if len(points) - 1 > _MAX_SEGMENTS:
                step = (len(points) - 1) / _MAX_SEGMENTS
                points = ([points[int(i * step)] for i in range(_MAX_SEGMENTS)]
                          + [points[-1]])
        else:
            points = [points[0], points[-1]]
        if (Vector(points[0]) - Vector(points[-1])).length < _MIN_PIXEL_STEP:
            self.report({'WARNING'}, "Stroke too short")
            return {'CANCELLED'}

        corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        focus = sum(corners, Vector((0.0, 0.0, 0.0))) / 8.0
        bbox_diag = obj.dimensions.length or 1.0
        planes = stroke_to_planes(
            context.region, context.region_data, points,
            focus_world=focus, extend=bbox_diag * 2.0)
        if not planes:
            self.report({'WARNING'}, "Degenerate stroke")
            return {'CANCELLED'}

        scene = context.scene
        settings = scene.printsplit
        cut_id = settings.next_cut_id

        if obj.data.users > 1:
            obj.data = obj.data.copy()

        entry = history.snapshot_cut(scene, cut_id, obj)
        try:
            obj_a, obj_b = cut_object(obj, planes, cut_id)
        except CutError as exc:
            history.discard_entry(scene, entry)
            obj.data.use_fake_user = False
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        history.complete_cut(scene, entry, (obj_a, obj_b))
        settings.next_cut_id = cut_id + 1

        for o in context.selected_objects:
            o.select_set(False)
        obj_a.select_set(True)
        obj_b.select_set(True)
        context.view_layer.objects.active = obj_a
        self.report({'INFO'},
                    f"Cut into '{obj_a.name}' and '{obj_b.name}'")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(PRINTSPLIT_OT_draw_cut)


def unregister():
    bpy.utils.unregister_class(PRINTSPLIT_OT_draw_cut)
