# SPDX-License-Identifier: GPL-3.0-or-later
"""Mesh inspection helpers used across cutting, joints and tests."""

import bmesh


def is_manifold(bm):
    """True when every edge links exactly two faces."""
    return all(e.is_manifold for e in bm.edges)


def is_watertight_mesh(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    try:
        return is_manifold(bm)
    finally:
        bm.free()


def mesh_volume(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    try:
        return bm.calc_volume(signed=True)
    finally:
        bm.free()


def boundary_loops(edges):
    """Group boundary edges into ordered vertex loops.

    edges: iterable of BMEdge that are boundary (each vert has exactly two
    of these edges in a closed loop). Returns a list of vertex lists, each
    ordered around its loop. Open chains are returned in walk order too.
    """
    edge_set = set(edges)
    # vert -> connected boundary edges in the set
    vert_edges = {}
    for e in edge_set:
        for v in e.verts:
            vert_edges.setdefault(v, []).append(e)

    loops = []
    remaining = set(edge_set)
    while remaining:
        start_edge = next(iter(remaining))
        remaining.discard(start_edge)
        loop_verts = [start_edge.verts[0], start_edge.verts[1]]
        # Walk forward until we close the loop or run out of edges.
        while True:
            tail = loop_verts[-1]
            next_edge = None
            for e in vert_edges.get(tail, ()):
                if e in remaining:
                    next_edge = e
                    break
            if next_edge is None:
                break
            remaining.discard(next_edge)
            nxt = next_edge.other_vert(tail)
            if nxt is loop_verts[0]:
                break
            loop_verts.append(nxt)
        loops.append(loop_verts)
    return loops


def loop_is_planar(verts, tolerance):
    """Check whether loop vertices lie within `tolerance` of a common plane
    (plane fit via Newell's method)."""
    n = len(verts)
    if n <= 3:
        return True
    # Newell normal
    nx = ny = nz = 0.0
    cx = cy = cz = 0.0
    for i in range(n):
        a = verts[i].co
        b = verts[(i + 1) % n].co
        nx += (a.y - b.y) * (a.z + b.z)
        ny += (a.z - b.z) * (a.x + b.x)
        nz += (a.x - b.x) * (a.y + b.y)
        cx += a.x
        cy += a.y
        cz += a.z
    length = (nx * nx + ny * ny + nz * nz) ** 0.5
    if length < 1e-12:
        return False
    nx, ny, nz = nx / length, ny / length, nz / length
    cx, cy, cz = cx / n, cy / n, cz / n
    for v in verts:
        d = abs((v.co.x - cx) * nx + (v.co.y - cy) * ny + (v.co.z - cz) * nz)
        if d > tolerance:
            return False
    return True
