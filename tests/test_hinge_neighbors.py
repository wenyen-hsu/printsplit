# SPDX-License-Identifier: GPL-3.0-or-later
"""Full-width joints (hinge barrel, dovetail rail) must stay on the limb
they join: a cut at a knee also lies in line with the other leg, and the
overlong barrel/groove used to reach into it."""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from printsplit.core import cross_section
from printsplit.core.cutting import CutPlane, cut_object

LEG_X = 0.4
LEG_R = 0.3


def _select_pair(male, female):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    male.select_set(True)
    female.select_set(True)
    bpy.context.view_layer.objects.active = male


def _make_legs():
    """Two parallel vertical cylinders (legs) in one mesh, 0.2 apart."""
    bm = bmesh.new()
    for x in (-LEG_X, LEG_X):
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=32,
            radius1=LEG_R, radius2=LEG_R, depth=2.0,
            matrix=Matrix.Translation(Vector((x, 0.0, 0.0))))
    mesh = bpy.data.meshes.new("Legs")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("Legs", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _cut_knees():
    legs = _make_legs()
    a, b = cut_object(
        legs, [CutPlane(Vector((0, 0, 0)), Vector((0, 0, 1)))], cut_id=1)
    bpy.context.view_layer.update()
    return a, b


def _aim_at_other_leg(male, female):
    """Rotation that points the joint X axis at the other leg (+-X)."""
    faces, _n = cross_section.shared_seam(male, female, 1)
    sec = cross_section.compute_cross_section(male, 1, faces)
    return sec, math.atan2(sec.tangent.cross(Vector((1, 0, 0))).dot(
        sec.normal), sec.tangent.dot(Vector((1, 0, 0))))


def _leg_b_signature(obj, leg_x):
    """Rounded vertex set of the leg not carrying the joint."""
    return {tuple(round(c, 4) for c in v.co) for v in obj.data.vertices
            if abs(v.co.x - leg_x) < LEG_R + 0.09}


def _run(shape, **kw):
    male, female = _cut_knees()
    sec, rot = _aim_at_other_leg(male, female)
    other_x = -LEG_X if sec.center.x > 0 else LEG_X
    before = (_leg_b_signature(male, other_x),
              _leg_b_signature(female, other_x))
    _select_pair(male, female)
    assert bpy.ops.printsplit.generate_joint(
        shape=shape, rotation=rot, solver='EXACT', **kw) == {'FINISHED'}
    after = (_leg_b_signature(male, other_x),
             _leg_b_signature(female, other_x))
    assert after[0] == before[0], "joint geometry leaked into the other leg (male)"
    assert after[1] == before[1], "joint geometry leaked into the other leg (female)"


def test_hinge_stays_on_its_leg():
    _run('HINGE')


def test_dovetail_rail_stays_on_its_leg():
    # The rail runs along the joint Y axis: aim that at the other leg.
    male, female = _cut_knees()
    sec, rot = _aim_at_other_leg(male, female)
    bpy.ops.wm.read_homefile(use_empty=True)
    _run_rail(rot + math.pi / 2.0)


def _run_rail(rot):
    male, female = _cut_knees()
    sec, _r = _aim_at_other_leg(male, female)
    other_x = -LEG_X if sec.center.x > 0 else LEG_X
    before = (_leg_b_signature(male, other_x),
              _leg_b_signature(female, other_x))
    _select_pair(male, female)
    assert bpy.ops.printsplit.generate_joint(
        shape='DOVETAIL', dovetail_style='RAIL', rotation=rot,
        solver='EXACT') == {'FINISHED'}
    after = (_leg_b_signature(male, other_x),
             _leg_b_signature(female, other_x))
    assert after[0] == before[0], "rail leaked into the other leg (male)"
    assert after[1] == before[1], "groove leaked into the other leg (female)"
