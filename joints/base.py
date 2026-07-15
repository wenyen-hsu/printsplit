# SPDX-License-Identifier: GPL-3.0-or-later
"""Joint shape contract.

A shape builds closed, manifold solids in *joint local space*:
+Z is the joint axis (0 at the cut seam, positive into the female half),
X is the cross-section major axis (width), Y is the slide/thickness axis.

Outputs and their boolean roles:
- ``build_male``        → UNION into the male half (may return None);
- ``build_male_cutter`` → optional DIFFERENCE from the male half (elastic
  slits, mirrored sockets, ...);
- ``build_cutter``      → DIFFERENCE from the female half;
- ``build_connector``   → optional standalone third object: a list of
  bmeshes, the first being the base solid and the rest UNIONed onto it
  through the boolean pipeline, so the printed connector is a genuinely
  watertight single solid (never overlapping shells).

Operand bmeshes fed to UNION/DIFFERENCE may contain several overlapping
closed shells in one bmesh (stem + sphere...). The EXACT solver resolves
them by winding number — shapes relying on this must set ``fast_ok =
False``. Clearance is applied in *parameter space* (the shape rebuilds
itself larger), never as a mesh offset.

``params`` always carries two generic entries besides shape-specific
ones: ``unit_mm`` (local units per millimetre, for absolute-size minimums
like walls and undercuts) and ``segments``.
"""


class JointSize:
    """Joint dimensions in mesh-local units (already unit-converted)."""

    __slots__ = ("width", "depth", "thickness", "embed", "channel")

    def __init__(self, width, depth, thickness, embed, channel=0.0):
        self.width = width          # extent along X
        self.depth = depth          # protrusion along +Z beyond the seam
        self.thickness = thickness  # extent along Y
        self.embed = embed          # root embedding along -Z into the male half
        self.channel = channel      # cutter length along Y; 0 = closed pocket


class JointShape:
    id = ""
    label = ""
    description = ""
    #: True for articulated joints: articulation clearance default,
    #: undercut retention, EXACT solver required.
    movable = False
    #: False when operands use overlapping shells (EXACT-only); the
    #: operator warns and overrides FAST.
    fast_ok = True
    #: 'SLIDE' assembles along Y through an open channel; 'PUSH' presses
    #: together along the joint axis Z (pocket or snap-fit).
    assembly = 'PUSH'

    def needs_trim(self, params):
        """True when the male peg is built overlong and must be clipped
        to the model volume (e.g. a full-width rail)."""
        return False

    def default_clearance(self, prefs):
        """Preferred clearance in mm for this shape."""
        if prefs is not None:
            return (prefs.default_clearance_movable if self.movable
                    else prefs.default_clearance)
        return 0.3 if self.movable else 0.15

    def auto_size(self, section, scale, clearance, avail_male,
                  avail_female, params):
        """Optional shape-specific sizing from the cut cross-section.
        Return a JointSize, or None to use the operator's generic ratios.
        May stash warnings in params['warnings'] (a list)."""
        return None

    def build_male(self, size, params):
        """Peg solid UNIONed into the male half, or None."""
        raise NotImplementedError

    def build_male_cutter(self, size, params, clearance):
        """Optional solid DIFFERENCEd from the male half."""
        return None

    def build_cutter(self, size, params, clearance):
        """Socket solid DIFFERENCEd from the female half."""
        raise NotImplementedError

    def build_connector(self, size, params, clearance):
        """Optional standalone connector: list of bmeshes (base first)."""
        return None

    def draw(self, layout, op):
        """Draw shape-specific operator properties."""
