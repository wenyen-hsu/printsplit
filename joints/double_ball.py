# SPDX-License-Identifier: GPL-3.0-or-later
"""Double-ball connector: BOTH halves get snap-in ball sockets, and a
separate dumbbell connector (ball-rod-ball) is generated as a third
object. Maximum articulation — each end rotates and twists like a ball
joint. The connector is parked beside the seam; its mating pose is kept
in the object's ``ps_mating_matrix`` custom property."""

from . import _solids
from .ball_socket import BallSocketShape, ball_dims, socket_cutter


class DoubleBallShape(BallSocketShape):
    id = 'DOUBLE_BALL'
    label = "Double Ball"
    description = ("Both halves get ball sockets joined by a separate "
                   "dumbbell connector — maximum articulation")
    movable = True
    fast_ok = False
    assembly = 'PUSH'

    def auto_size(self, section, scale, clearance, avail_male,
                  avail_female, params):
        # Both halves host a full socket, so both depths constrain.
        avail = min(avail_male, avail_female)
        return super().auto_size(section, scale, clearance,
                                 avail, avail, params)

    def build_male(self, size, params):
        return None  # the male half only receives a socket too

    def build_male_cutter(self, size, params, clearance):
        # Mirrored socket below the seam, carved out of the male half.
        return socket_cutter(size, params, clearance,
                             params['segments'], sign=-1.0)

    def build_cutter(self, size, params, clearance):
        return socket_cutter(size, params, clearance, params['segments'])

    def build_connector(self, size, params, clearance):
        radius, z_c, _rho, _c = ball_dims(size, params)
        seg = params['segments']
        rod = _solids.cone(0.5 * radius, 0.5 * radius, -z_c, z_c, seg)
        top = _solids.uv_sphere(radius, z_c, seg)
        bottom = _solids.uv_sphere(radius, -z_c, seg)
        return [rod, top, bottom]

    def draw(self, layout, op):
        layout.prop(op, "ball_opening_ratio")
        layout.prop(op, "ball_rom")
        layout.prop(op, "segments")
