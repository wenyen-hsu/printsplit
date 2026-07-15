# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared joint parameters and plan building.

``JointParamsMixin`` holds every joint operator property and turns the
current selection + parameters into a ``JointPlan`` — an ordered list of
boolean operations plus an optional connector object recipe. Both the
generate and preview operators inherit it, so the geometry path is
identical whether the user commits directly or previews first.
"""

import math

import bpy

from ..core import cross_section
from ..core.booleans import intersect_with_object
from ..joints import get_shape, shape_enum_items
from ..preferences import get_prefs, solver_items
from ..utils.math_utils import mm_to_blender_units

_MAX_NORMAL_SPREAD = math.radians(30.0)

# Reentrancy guard for the shape→clearance default sync.
_updating_clearance = False


class JointError(Exception):
    """User-reportable plan failure; the scene is untouched."""


class PlanOp:
    __slots__ = ("target", "bm", "matrix", "operation")

    def __init__(self, target, bm, matrix, operation):
        self.target = target
        self.bm = bm
        self.matrix = matrix
        self.operation = operation


class JointPlan:
    __slots__ = ("ops", "connector_bms", "connector_matrix", "cut_id",
                 "shape", "size", "male", "female", "frame_local",
                 "section", "warnings", "solver")

    def free(self):
        for op in self.ops:
            if op.bm is not None:
                op.bm.free()
        for bm in self.connector_bms or ():
            bm.free()
        self.ops = []
        self.connector_bms = []


def _joint_shape_items(_self, _context):
    return shape_enum_items()


def _solver_prop_items(_self, _context):
    return solver_items()


def _on_clearance_edit(self, _context):
    if not _updating_clearance:
        self.clearance_user_set = True


def _on_shape_change(self, context):
    """Seed the clearance from the shape's default until the user edits
    the slider themselves — then their value wins across shape switches."""
    global _updating_clearance
    if self.clearance_user_set:
        return
    _updating_clearance = True
    try:
        self.clearance_mm = get_shape(self.shape).default_clearance(
            get_prefs(context))
    finally:
        _updating_clearance = False


class JointParamsMixin:
    shape: bpy.props.EnumProperty(
        name="Shape", items=_joint_shape_items, update=_on_shape_change)
    flip: bpy.props.BoolProperty(
        name="Flip",
        description="Swap which half gets the peg and which the socket",
        default=False,
    )
    auto_size: bpy.props.BoolProperty(
        name="Auto Size",
        description="Size the joint from the cut cross-section",
        default=True,
    )
    scale: bpy.props.FloatProperty(
        name="Scale",
        description="Scale factor applied to the auto size",
        default=1.0, min=0.1, max=3.0,
    )
    width: bpy.props.FloatProperty(
        name="Width", subtype='DISTANCE',
        description="Joint width (manual mode)",
        default=0.1, min=1e-5,
    )
    depth: bpy.props.FloatProperty(
        name="Depth", subtype='DISTANCE',
        description="How far the peg reaches into the other half (manual)",
        default=0.06, min=1e-5,
    )
    thickness: bpy.props.FloatProperty(
        name="Thickness", subtype='DISTANCE',
        description="Joint thickness along the slide axis (manual)",
        default=0.06, min=1e-5,
    )
    rotation: bpy.props.FloatProperty(
        name="Rotation", subtype='ANGLE',
        description="Spin the joint around the cut normal",
        default=0.0,
    )
    clearance_mm: bpy.props.FloatProperty(
        name="Clearance (mm)",
        description="Printing tolerance between the mating parts",
        default=0.15, min=0.0, max=2.0, precision=3,
        update=_on_clearance_edit,
    )
    clearance_user_set: bpy.props.BoolProperty(
        options={'HIDDEN', 'SKIP_SAVE'}, default=False)
    solver: bpy.props.EnumProperty(name="Solver", items=_solver_prop_items)
    segments: bpy.props.IntProperty(
        name="Segments",
        description="Segment count for round joint geometry",
        default=32, min=8, max=128,
    )

    # --- Shape-specific extras (drawn by the active shape only) ---
    dovetail_style: bpy.props.EnumProperty(
        name="Style",
        items=[
            ('RAIL', "Rail (full width)",
             "The dovetail runs across the whole cut and ends flush with "
             "the surface — assembled parts have no voids"),
            ('KEY', "Key (local)",
             "A short local key; the slide channel remains open on both "
             "sides after assembly"),
        ],
        default='RAIL',
    )
    dovetail_flare: bpy.props.FloatProperty(
        name="Flare", subtype='ANGLE',
        description="Dovetail side angle; wider tip locks the halves",
        default=math.radians(12.0),
        min=0.0, max=math.radians(30.0),
    )
    dovetail_draft: bpy.props.FloatProperty(
        name="Draft", subtype='ANGLE',
        description="Taper along the slide direction so the fit snugs up",
        default=math.radians(1.5),
        min=0.0, max=math.radians(10.0),
    )
    cyl_taper: bpy.props.FloatProperty(
        name="Taper", subtype='ANGLE',
        description="Pin taper for easier insertion and press fit",
        default=math.radians(2.0),
        min=0.0, max=math.radians(15.0),
    )
    cross_taper: bpy.props.FloatProperty(
        name="Taper", subtype='ANGLE',
        description="Key taper for easier insertion and press fit",
        default=math.radians(2.0),
        min=0.0, max=math.radians(15.0),
    )
    ball_opening_ratio: bpy.props.FloatProperty(
        name="Opening Ratio",
        description="Socket opening diameter as a fraction of the ball "
        "diameter — smaller means stronger snap retention",
        default=0.80, min=0.6, max=0.92,
    )
    ball_rom: bpy.props.FloatProperty(
        name="Range of Motion", subtype='ANGLE',
        description="Extra neck relief so the joint can swing this far "
        "off axis",
        default=math.radians(25.0),
        min=0.0, max=math.radians(60.0),
    )
    ball_neck_ratio: bpy.props.FloatProperty(
        name="Neck Ratio",
        description="Stem diameter as a fraction of the ball diameter",
        default=0.45, min=0.3, max=0.7,
    )
    hinge_rom: bpy.props.FloatProperty(
        name="Range of Motion", subtype='ANGLE',
        description="Symmetric bend limit of the hinge (± this angle)",
        default=math.radians(45.0),
        min=math.radians(5.0), max=math.radians(80.0),
    )
    hinge_tongue: bpy.props.FloatProperty(
        name="Tongue Thickness",
        description="Tongue (neck) thickness as a fraction of the pivot "
        "height — thicker is stronger but widens the swing slot",
        default=0.7, min=0.3, max=0.9,
    )
    swivel_undercut_mm: bpy.props.FloatProperty(
        name="Undercut (mm)",
        description="Net retention lip of the mushroom cap (survives "
        "clearance by construction)",
        default=0.4, min=0.1, max=1.5, precision=2,
    )
    swivel_slits: bpy.props.BoolProperty(
        name="Elastic Slits",
        description="Cross-slit the mushroom cap so it compresses during "
        "snap-in (applied when the cap is large enough)",
        default=True,
    )

    def seed_defaults(self, context):
        """Call from invoke(): pull solver + clearance defaults."""
        prefs = get_prefs(context)
        if prefs is not None:
            self.solver = prefs.default_solver
        self.clearance_user_set = False
        _on_shape_change(self, context)

    def _shape_params(self, context, obj_scale):
        return {
            'style': self.dovetail_style,
            'flare': self.dovetail_flare,
            'draft': self.dovetail_draft,
            'taper': self.cyl_taper,
            'cross_taper': self.cross_taper,
            'opening_ratio': self.ball_opening_ratio,
            'rom': self.ball_rom,
            'neck_ratio': self.ball_neck_ratio,
            'hinge_rom': self.hinge_rom,
            'tongue': self.hinge_tongue,
            'undercut_mm': self.swivel_undercut_mm,
            'slits': self.swivel_slits,
            'segments': self.segments,
            'unit_mm': mm_to_blender_units(1.0, context.scene) / obj_scale,
            'warnings': [],
        }

    # ------------------------------------------------------------------
    def build_plan(self, context):
        """Turn selection + parameters into a JointPlan.
        Raises JointError with a user-readable message on failure."""
        halves = [o for o in context.selected_objects if o.type == 'MESH']
        if len(halves) != 2:
            raise JointError("Select exactly the two cut halves")
        if context.active_object in halves:
            male = context.active_object
            female = next(o for o in halves if o is not male)
        else:
            male, female = halves
        if self.flip:
            male, female = female, male

        cut_id = cross_section.find_common_cut_id(male, female)
        if cut_id is None:
            raise JointError(
                "The selected objects do not share a PrintSplit cut")

        section = cross_section.compute_cross_section(male, cut_id)
        if section is None:
            raise JointError("Could not analyze the cut cross-section")

        warnings = []
        if section.normal_spread > _MAX_NORMAL_SPREAD:
            warnings.append(
                "The cut surface is strongly curved; the joint may not "
                "seat well — consider a straight cut")

        obj_scale = male.matrix_world.median_scale or 1.0
        clearance = mm_to_blender_units(
            self.clearance_mm, context.scene) / obj_scale

        shape = get_shape(self.shape)
        solver = self.solver
        if solver != 'EXACT' and not shape.fast_ok:
            warnings.append(
                f"{shape.label} joints need the Exact solver; overriding")
            solver = 'EXACT'

        params = self._shape_params(context, obj_scale)
        # Movable shapes size their undercuts net of clearance, so the
        # male builder needs it too (cutters receive it as an argument).
        params['clearance'] = clearance

        context.view_layer.update()  # ray_cast needs a fresh depsgraph
        max_probe = min(section.extent_t, section.extent_b) * 10.0
        avail_female = cross_section.material_depth(
            female, section.center, section.normal, max_probe)
        avail_male = cross_section.material_depth(
            male, section.center, -section.normal, max_probe)

        size = self._compute_size(shape, section, clearance,
                                  avail_male, avail_female, params,
                                  obj_scale)
        if size is None:
            raise JointError("Not enough material for a joint here")
        warnings.extend(params['warnings'])

        frame = section.matrix(self.rotation)
        male_matrix = male.matrix_world @ frame
        female_matrix = female.matrix_world @ frame

        plan = JointPlan()
        plan.ops = []
        plan.connector_bms = []
        plan.connector_matrix = male_matrix
        plan.cut_id = cut_id
        plan.shape = shape
        plan.size = size
        plan.male = male
        plan.female = female
        plan.frame_local = frame
        plan.section = section
        plan.warnings = warnings
        plan.solver = solver

        try:
            male_bm = shape.build_male(size, params)
            if male_bm is not None and shape.needs_trim(params):
                male_bm = self._trim_male(
                    context, male, female, cut_id, male_bm, male_matrix,
                    use_self=not shape.fast_ok)
                if male_bm is None:
                    raise JointError(
                        "Could not trim the rail to the model surface")
            if male_bm is not None:
                plan.ops.append(PlanOp(male, male_bm, male_matrix, 'UNION'))

            male_cutter = shape.build_male_cutter(size, params, clearance)
            if male_cutter is not None:
                plan.ops.append(
                    PlanOp(male, male_cutter, male_matrix, 'DIFFERENCE'))

            cutter = shape.build_cutter(size, params, clearance)
            plan.ops.append(
                PlanOp(female, cutter, female_matrix, 'DIFFERENCE'))

            connector = shape.build_connector(size, params, clearance)
            if connector:
                plan.connector_bms = list(connector)
        except JointError:
            plan.free()
            raise
        except Exception:
            plan.free()
            raise
        return plan

    def _compute_size(self, shape, section, clearance,
                      avail_male, avail_female, params, obj_scale):
        base = min(section.extent_t, section.extent_b)
        if base <= clearance * 8.0:
            return None

        if self.auto_size:
            sized = shape.auto_size(section, self.scale, clearance,
                                    avail_male, avail_female, params)
            if sized is not None:
                return sized
            width = 0.45 * base * self.scale
            thickness = 0.6 * width
            depth = 0.75 * width
        else:
            # Manual dims are entered in scene units -> mesh-local.
            width = self.width / obj_scale
            thickness = self.thickness / obj_scale
            depth = self.depth / obj_scale

        from ..joints import JointSize

        depth = min(depth, avail_female * 0.8)
        embed = min(0.5 * width, avail_male * 0.8)
        if depth <= clearance * 4.0 or embed <= 0.0:
            return None
        channel = section.extent_b * 3.0
        return JointSize(width=width, depth=depth, thickness=thickness,
                         embed=embed, channel=channel)

    def _trim_male(self, context, male, female, cut_id, male_bm, matrix,
                   use_self=False):
        """Clip an overlong rail peg against the model's original volume
        so it ends flush with the outer surface. Prefers the pre-cut
        backup mesh from history; falls back to boolean-unioning the two
        halves in their shared local space."""
        trim_mesh = None
        owned_mesh = None
        for entry in reversed(context.scene.printsplit_history):
            if entry.kind == 'CUT' and entry.cut_id == cut_id:
                trim_mesh = bpy.data.meshes.get(entry.backup_mesh_names)
                break
        if trim_mesh is None:
            tmp_female = bpy.data.objects.new("_ps_trim_b", female.data)
            tmp_female.matrix_world = male.matrix_world
            context.scene.collection.objects.link(tmp_female)
            tmp_male = bpy.data.objects.new("_ps_trim_a", male.data)
            tmp_male.matrix_world = male.matrix_world
            context.scene.collection.objects.link(tmp_male)
            mod = tmp_male.modifiers.new(name="u", type='BOOLEAN')
            mod.object = tmp_female
            mod.operation = 'UNION'
            mod.solver = 'EXACT'
            try:
                deps = context.evaluated_depsgraph_get()
                eval_obj = tmp_male.evaluated_get(deps)
                trim_mesh = owned_mesh = bpy.data.meshes.new_from_object(
                    eval_obj, preserve_all_data_layers=False, depsgraph=deps)
            finally:
                bpy.data.objects.remove(tmp_male)
                bpy.data.objects.remove(tmp_female)

        # Shrink the trim volume a hair so the trimmed rail walls never
        # coincide exactly with the model surface — coplanar face contact
        # breaks boolean unions (FAST always, EXACT sometimes).
        shrunk = trim_mesh.copy()
        eps = max(o.dimensions.length for o in (male, female)) * 2e-4
        eps /= male.matrix_world.median_scale or 1.0
        normals = [v.normal.copy() for v in shrunk.vertices]
        for v, n in zip(shrunk.vertices, normals):
            v.co -= n * eps
        if owned_mesh is not None:
            bpy.data.meshes.remove(owned_mesh)

        trim_obj = bpy.data.objects.new("_ps_trim_volume", shrunk)
        trim_obj.matrix_world = male.matrix_world
        context.scene.collection.objects.link(trim_obj)
        try:
            trimmed = intersect_with_object(
                context, male_bm, matrix, trim_obj, use_self=use_self)
        finally:
            bpy.data.objects.remove(trim_obj)
            bpy.data.meshes.remove(shrunk)
        male_bm.free()
        if not len(trimmed.verts):
            trimmed.free()
            return None
        return trimmed

    def draw_joint_props(self, layout):
        layout.use_property_split = True
        layout.prop(self, "shape")
        layout.prop(self, "flip")
        layout.prop(self, "auto_size")
        if self.auto_size:
            layout.prop(self, "scale")
        else:
            layout.prop(self, "width")
            layout.prop(self, "depth")
            layout.prop(self, "thickness")
        layout.prop(self, "rotation")
        shape = get_shape(self.shape)
        label = ("Articulation Clearance (mm)" if shape.movable
                 else "Fit Clearance (mm)")
        layout.prop(self, "clearance_mm", text=label)
        layout.prop(self, "solver")
        shape.draw(layout, self)
