# SPDX-License-Identifier: GPL-3.0-or-later
"""Joint shape registry. Add a new shape by subclassing JointShape and
calling register_shape() here (or from your own module at import time)."""

from .ball_socket import BallSocketShape
from .base import JointShape, JointSize  # noqa: F401 - public API
from .cross_key import CrossKeyShape
from .cylinder import CylinderShape
from .double_ball import DoubleBallShape
from .dovetail import DovetailShape
from .hinge import HingeShape
from .swivel import SwivelShape

_registry = {}
# EnumProperty item tuples must stay referenced from Python (Blender
# gotcha: dynamic callbacks may return garbage-collected strings).
_enum_items = []


def register_shape(cls):
    shape = cls()
    _registry[shape.id] = shape
    _enum_items.append((shape.id, shape.label, shape.description))


def get_shape(shape_id):
    return _registry[shape_id]


def shape_enum_items():
    return list(_enum_items)


register_shape(DovetailShape)
register_shape(CylinderShape)
register_shape(CrossKeyShape)
register_shape(BallSocketShape)
register_shape(HingeShape)
register_shape(SwivelShape)
register_shape(DoubleBallShape)
