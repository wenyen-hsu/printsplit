# SPDX-License-Identifier: GPL-3.0-or-later
"""Polyline mesh cutting.

The cut is a sequence of planes (one per stroke segment), each bounded
along the stroke direction by two miter planes forming a slab. Cutting is
pure bmesh (``bisect_plane``), never boolean, so it is deterministic,
kerf-free and stable on dense sculpts.

Everything here is context-free: functions take explicit meshes/planes so
they run headless in ``blender --background``.
"""

import bmesh
from mathutils import Vector

CUT_ID_FACE_ATTR = "printsplit_cut_id"
_SIDE_LAYER = "_ps_side"
_SEAM_LAYER = "_ps_seam"


class CutError(Exception):
    """Raised when a cut cannot be performed; the input mesh is untouched."""


class CutPlane:
    """A cutting plane bounded by two miter planes (a slab).

    All vectors are in the space of the mesh being cut. Miter normals point
    INTO the slab. ``start``/``end`` may be None for an unbounded side.
    """

    __slots__ = ("co", "no", "start_co", "start_no", "end_co", "end_no")

    def __init__(self, co, no, start_co=None, start_no=None,
                 end_co=None, end_no=None):
        self.co = Vector(co)
        self.no = Vector(no).normalized()
        self.start_co = Vector(start_co) if start_co is not None else None
        self.start_no = Vector(start_no).normalized() if start_no is not None else None
        self.end_co = Vector(end_co) if end_co is not None else None
        self.end_no = Vector(end_no).normalized() if end_no is not None else None

    def distance(self, point):
        return (point - self.co).dot(self.no)

    def in_slab(self, point, tol):
        if self.start_co is not None:
            if (point - self.start_co).dot(self.start_no) < -tol:
                return False
        if self.end_co is not None:
            if (point - self.end_co).dot(self.end_no) < -tol:
                return False
        return True

    def face_touches_slab(self, face, tol):
        """Conservative test: the face has at least one vertex on the slab
        side of each miter plane."""
        if self.start_co is not None:
            if all((v.co - self.start_co).dot(self.start_no) < -tol
                   for v in face.verts):
                return False
        if self.end_co is not None:
            if all((v.co - self.end_co).dot(self.end_no) < -tol
                   for v in face.verts):
                return False
        return True

    def face_straddles(self, face, dist):
        pos = neg = False
        for v in face.verts:
            d = self.distance(v.co)
            if d > dist:
                pos = True
            elif d < -dist:
                neg = True
            if pos and neg:
                return True
        return False


def candidate_face_indices(mesh, planes, dist, tol):
    """NumPy prefilter over an (unmodified) Mesh: polygon indices that
    straddle any cutting plane inside its slab. Keeps the per-segment
    Python work proportional to the cut band, not the whole mesh."""
    import numpy as np

    vcount = len(mesh.vertices)
    lcount = len(mesh.loops)
    pcount = len(mesh.polygons)
    if not (vcount and lcount and pcount):
        return set()

    coords = np.empty(vcount * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3).astype(np.float64)

    loop_verts = np.empty(lcount, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_verts)
    loop_start = np.empty(pcount, dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", loop_start)

    def per_face_minmax(plane_co, plane_no):
        with np.errstate(all='ignore'):  # BLAS quirk on near-zero columns
            d = coords @ np.asarray(plane_no, dtype=np.float64)
        d -= float(Vector(plane_co).dot(Vector(plane_no)))
        dl = d[loop_verts]
        return (np.minimum.reduceat(dl, loop_start),
                np.maximum.reduceat(dl, loop_start))

    mask = np.zeros(pcount, dtype=bool)
    for pl in planes:
        fmin, fmax = per_face_minmax(pl.co, pl.no)
        # Superset: faces strictly straddling the plane AND faces merely
        # touching it (a cut may run along existing edges, e.g. a sphere
        # equator loop).
        m = (fmin < tol) & (fmax > -tol)
        if pl.start_co is not None:
            _, smax = per_face_minmax(pl.start_co, pl.start_no)
            m &= smax >= -tol
        if pl.end_co is not None:
            _, emax = per_face_minmax(pl.end_co, pl.end_no)
            m &= emax >= -tol
        mask |= m
    return set(np.nonzero(mask)[0].tolist())


def _slab_index_for_point(planes, point, tol):
    best = 0
    best_dist = None
    for i, pl in enumerate(planes):
        if pl.in_slab(point, tol):
            return i
        d = abs(pl.distance(point))
        if best_dist is None or d < best_dist:
            best_dist = d
            best = i
    return best


def cut_bmesh(bm, planes, cut_id, *, dist=1e-6, candidates=None):
    """Cut ``bm`` by the plane sequence and return two NEW bmeshes
    (side A: positive plane side, side B: negative), each watertight-capped
    along the seam and with cap faces tagged ``printsplit_cut_id=cut_id``.

    ``bm`` is consumed as scratch space (mutated); the caller frees it.
    ``candidates``: optional set of original face indices near the cut
    (from :func:`candidate_face_indices`) to avoid scanning every face.
    Raises :class:`CutError` when the planes do not sever the mesh.
    """
    tol = dist * 4.0

    # Create ALL custom-data layers up front: adding a layer reallocates
    # element data and invalidates every existing BMElem reference.
    seam_layer = bm.edges.layers.int.get(_SEAM_LAYER)
    if seam_layer is None:
        seam_layer = bm.edges.layers.int.new(_SEAM_LAYER)
    side_layer = bm.faces.layers.int.get(_SIDE_LAYER)
    if side_layer is None:
        side_layer = bm.faces.layers.int.new(_SIDE_LAYER)
    if bm.faces.layers.int.get(CUT_ID_FACE_ATTR) is None:
        bm.faces.layers.int.new(CUT_ID_FACE_ATTR)

    bm.faces.ensure_lookup_table()
    if candidates is None:
        pool = set(bm.faces)
    else:
        pool = {bm.faces[i] for i in candidates}

    # Bisect segment by segment. Seam identification happens AFTER all
    # bisects, purely geometrically: custom-data tags do not reliably
    # survive later bisects splitting earlier cut edges at slab junctions.
    for plane in planes:
        faces = [
            f for f in pool
            if f.is_valid
            and plane.face_touches_slab(f, tol)
            and plane.face_straddles(f, dist)
        ]
        if not faces:
            continue
        geom = set(faces)
        for f in faces:
            geom.update(f.verts)
            geom.update(f.edges)
        ret = bmesh.ops.bisect_plane(
            bm,
            geom=list(geom),
            plane_co=plane.co,
            plane_no=plane.no,
            dist=dist,
            use_snap_center=False,
            clear_inner=False,
            clear_outer=False,
        )
        for ele in ret["geom"]:
            if isinstance(ele, bmesh.types.BMFace):
                pool.add(ele)

    # Successive bisects snap vertices onto their planes (`dist`), which
    # can leave zero-length edges where two segments meet. Weld coincident
    # vertices near the cut before identifying the seam, or the seam graph
    # degenerates and capping fails.
    weld_verts = []
    seen_verts = set()
    for f in pool:
        if not f.is_valid:
            continue
        for v in f.verts:
            if v in seen_verts:
                continue
            seen_verts.add(v)
            if any(abs(pl.distance(v.co)) <= tol for pl in planes):
                weld_verts.append(v)
    if weld_verts:
        bmesh.ops.remove_doubles(bm, verts=weld_verts, dist=tol)

    # An edge is part of the seam iff it lies ON some segment's plane
    # (both endpoints within tolerance) inside that segment's slab. This
    # covers bisect-created edges, halves of edges re-split at slab
    # junctions, and pre-existing edges the cut runs along (e.g. a sphere
    # equator loop).
    cut_edges = []
    seen = set()
    for f in pool:
        if not f.is_valid:
            continue
        for e in f.edges:
            if e in seen:
                continue
            seen.add(e)
            if e.is_boundary:
                continue
            a = e.verts[0].co
            b = e.verts[1].co
            mid = (a + b) * 0.5
            for pl in planes:
                if (abs(pl.distance(a)) <= tol
                        and abs(pl.distance(b)) <= tol
                        and pl.in_slab(mid, tol)):
                    e[seam_layer] = 1
                    cut_edges.append(e)
                    break

    if not cut_edges:
        raise CutError("The stroke does not intersect the mesh")
    bmesh.ops.split_edges(bm, edges=cut_edges)

    side_a, side_b = _classify_sides(bm, planes, seam_layer, tol)
    if not side_a or not side_b:
        raise CutError("The cut did not separate the mesh into two parts")

    for f in side_a:
        f[side_layer] = 0
    for f in side_b:
        f[side_layer] = 1

    bm_a = _extract_side(bm, 0, cut_id, tol)
    bm_b = _extract_side(bm, 1, cut_id, tol)
    return bm_a, bm_b


def cut_object(obj, planes_world, cut_id, *, dist=None):
    """Cut a mesh object by world-space planes into two new objects
    ``<name>_A`` / ``<name>_B`` linked to the same collections, and remove
    the original object (the caller is responsible for backing up its mesh
    first — see core.history). Returns ``(obj_a, obj_b)``.

    Raises :class:`CutError` without touching the scene on failure.
    """
    import bpy

    from ..utils.math_utils import transform_plane

    if obj.type != 'MESH':
        raise CutError("Active object is not a mesh")
    mesh = obj.data

    if dist is None:
        # Scale the snap epsilon to the object so tiny and huge meshes
        # both behave.
        diag = max(obj.dimensions.length, 1e-3)
        dist = diag * 1e-7

    matrix_inv = obj.matrix_world.inverted_safe()

    def to_local(co, no):
        if co is None:
            return None, None
        return transform_plane(matrix_inv, co, no)

    planes = []
    for pw in planes_world:
        co, no = to_local(pw.co, pw.no)
        s_co, s_no = to_local(pw.start_co, pw.start_no)
        e_co, e_no = to_local(pw.end_co, pw.end_no)
        planes.append(CutPlane(co, no, s_co, s_no, e_co, e_no))

    tol = dist * 4.0
    candidates = candidate_face_indices(mesh, planes, dist, tol)
    if not candidates:
        raise CutError("The stroke does not intersect the mesh")

    bm = bmesh.new()
    bm.from_mesh(mesh)
    try:
        bm_a, bm_b = cut_bmesh(bm, planes, cut_id,
                               dist=dist, candidates=candidates)
    finally:
        bm.free()

    collections = list(obj.users_collection)
    matrix = obj.matrix_world.copy()
    base_name = obj.name

    results = []
    for suffix, bm_side in (("_A", bm_a), ("_B", bm_b)):
        new_mesh = mesh.copy()  # keeps materials and mesh settings
        bm_side.to_mesh(new_mesh)
        bm_side.free()
        new_mesh.name = base_name + suffix
        new_obj = bpy.data.objects.new(base_name + suffix, new_mesh)
        new_obj.matrix_world = matrix
        for coll in collections:
            coll.objects.link(new_obj)
        results.append(new_obj)

    bpy.data.objects.remove(obj)
    return tuple(results)


def _classify_sides(bm, planes, seam_layer, tol):
    """Group faces into two sides via flood fill that never crosses the
    (already split) seam. Each connected component is assigned by the sign
    of its faces' distance to the local slab's cutting plane."""
    side_a = []
    side_b = []
    visited = set()
    for start in bm.faces:
        if start in visited:
            continue
        component = []
        stack = [start]
        visited.add(start)
        while stack:
            f = stack.pop()
            component.append(f)
            for e in f.edges:
                if e[seam_layer] == 1:
                    continue
                for nf in e.link_faces:
                    if nf not in visited:
                        visited.add(nf)
                        stack.append(nf)

        sign = 0.0
        # Sample a handful of faces; near-plane faces are ambiguous.
        for f in component[: 50]:
            center = f.calc_center_median()
            plane = planes[_slab_index_for_point(planes, center, tol)]
            d = plane.distance(center)
            if abs(d) > abs(sign):
                sign = d
        if sign >= 0.0:
            side_a.extend(component)
        else:
            side_b.extend(component)
    return side_a, side_b


def _extract_side(bm_src, keep_side, cut_id, tol):
    """Copy ``bm_src`` keeping one side, cap the seam holes, tag cap faces,
    fix normals, and strip scratch layers."""
    bm = bm_src.copy()
    side_layer = bm.faces.layers.int.get(_SIDE_LAYER)
    seam_layer = bm.edges.layers.int.get(_SEAM_LAYER)

    doomed = [f for f in bm.faces if f[side_layer] != keep_side]
    if doomed:
        bmesh.ops.delete(bm, geom=doomed, context='FACES')
    loose_edges = [e for e in bm.edges if not e.link_faces]
    if loose_edges:
        bmesh.ops.delete(bm, geom=loose_edges, context='EDGES')
    loose_verts = [v for v in bm.verts if not v.link_edges]
    if loose_verts:
        bmesh.ops.delete(bm, geom=loose_verts, context='VERTS')

    _cap_seam_holes(bm, seam_layer, cut_id, tol)

    bm.faces.layers.int.remove(bm.faces.layers.int.get(_SIDE_LAYER))
    bm.edges.layers.int.remove(bm.edges.layers.int.get(_SEAM_LAYER))

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def _cap_seam_holes(bm, seam_layer, cut_id, tol):
    from ..utils.mesh_utils import boundary_loops, loop_is_planar

    # Guaranteed to exist: cut_bmesh creates it before any side copies.
    cut_layer = bm.faces.layers.int.get(CUT_ID_FACE_ATTR)

    seam_boundary = [
        e for e in bm.edges if e.is_boundary and e[seam_layer] == 1
    ]
    cap_faces = []
    for verts in boundary_loops(seam_boundary):
        if len(verts) < 3:
            continue
        try:
            face = bm.faces.new(verts)
        except ValueError:
            continue  # degenerate/duplicate loop
        if loop_is_planar(verts, max(tol, 1e-5)):
            cap_faces.append(face)
        else:
            ret = bmesh.ops.triangulate(bm, faces=[face])
            cap_faces.extend(ret["faces"])

    for f in cap_faces:
        if f.is_valid:
            f[cut_layer] = cut_id
            # Sharp seam so smooth shading keeps a crisp edge at the cut;
            # only the seam-loop edges, not interior triangulation edges.
            for e in f.edges:
                if e[seam_layer] == 1:
                    e.smooth = False
