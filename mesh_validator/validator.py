"""只读网格校验器。

设计约束：
- 零拷贝：直接引用调用方的 positions/triangles/属性序列，绝不复制或修改。
- 顺序无关：所有诊断按规范化位置（排序后的顶点索引）生成，
  同一网格改变三角形声明顺序后，report.signature() 完全一致。
- 单次建边表：O(F) 建立边 -> 面邻接，之后所有拓扑检查共用。
"""

import operator
from collections import Counter, defaultdict
from typing import List, Optional, Tuple

from .mesh import Mesh
from .report import (
    Diagnostic,
    REPAIR_AUTO,
    REPAIR_INFO,
    REPAIR_MANUAL,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    ValidationReport,
)


def _as_index(value) -> Optional[int]:
    try:
        return int(operator.index(value))
    except TypeError:
        return None


def _cross_norm2(pa, pb, pc) -> float:
    abx, aby, abz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
    acx, acy, acz = pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]
    cx = aby * acz - abz * acy
    cy = abz * acx - abx * acz
    cz = abx * acy - aby * acx
    return cx * cx + cy * cy + cz * cz


def validate(
    mesh: Mesh,
    *,
    area_epsilon: float = 1e-12,
    weight_tolerance: float = 1e-3,
) -> ValidationReport:
    """对 mesh 做只读校验，返回 ValidationReport。不修改 mesh 的任何数据。"""
    diagnostics: List[Diagnostic] = []
    positions = mesh.positions
    triangles = mesh.triangles
    n_verts = len(positions)
    n_tris = len(triangles)

    def add(code, severity, message, location, repair, details=None):
        diagnostics.append(
            Diagnostic(code, severity, message, location, repair, details or {})
        )

    # ---- 1. 属性长度 ------------------------------------------------
    for name, attr in (("normals", mesh.normals), ("uvs", mesh.uvs), ("weights", mesh.weights)):
        if attr is not None and len(attr) != n_verts:
            add(
                "ATTRIBUTE_LENGTH", SEVERITY_ERROR,
                f"attribute '{name}' has {len(attr)} entries, expected {n_verts} (one per vertex)",
                ("attribute", name), REPAIR_MANUAL,
                {"expected": n_verts, "actual": len(attr)},
            )
    if mesh.materials is not None and len(mesh.materials) != n_tris:
        add(
            "ATTRIBUTE_LENGTH", SEVERITY_ERROR,
            f"attribute 'materials' has {len(mesh.materials)} entries, expected {n_tris} (one per triangle)",
            ("attribute", "materials"), REPAIR_MANUAL,
            {"expected": n_tris, "actual": len(mesh.materials)},
        )

    # ---- 2. 面级检查：索引合法性 / 退化 / 重复 ----------------------
    canonical_faces: List[Tuple[Tuple[int, int, int], int]] = []
    topo_faces: List[Tuple[int, Tuple[int, int, int]]] = []
    for fi in range(n_tris):
        tri = triangles[fi]
        if len(tri) != 3:
            add(
                "INVALID_FACE", SEVERITY_ERROR,
                f"face {fi} declares {len(tri)} vertices, expected 3",
                ("face",) + tuple(sorted(tri)), REPAIR_MANUAL,
                {"faces": [fi]},
            )
            continue
        idx = [_as_index(v) for v in tri]
        if any(i is None for i in idx):
            add(
                "INDEX_OUT_OF_RANGE", SEVERITY_ERROR,
                f"face {fi} contains non-integer vertex indices",
                ("face",) + tuple(sorted(tri)), REPAIR_MANUAL,
                {"faces": [fi]},
            )
            continue
        a, b, c = idx
        canon = tuple(sorted(idx))
        bad = sorted({i for i in idx if not 0 <= i < n_verts})
        if bad:
            add(
                "INDEX_OUT_OF_RANGE", SEVERITY_ERROR,
                f"face references vertex indices out of range [0, {n_verts}): {bad}",
                ("face",) + canon, REPAIR_MANUAL,
                {"faces": [fi], "indices": bad},
            )
            continue
        canonical_faces.append((canon, fi))
        if len({a, b, c}) != 3:
            add(
                "DEGENERATE_FACE", SEVERITY_ERROR,
                "face repeats a vertex index (zero-area by construction)",
                ("face",) + canon, REPAIR_AUTO,
                {"faces": [fi], "reason": "repeated_index"},
            )
            continue
        if _cross_norm2(positions[a], positions[b], positions[c]) <= area_epsilon:
            add(
                "DEGENERATE_FACE", SEVERITY_ERROR,
                "face has near-zero geometric area (collinear/coincident vertices)",
                ("face",) + canon, REPAIR_AUTO,
                {"faces": [fi], "reason": "zero_area"},
            )
            continue
        topo_faces.append((fi, (a, b, c)))

    counts = Counter(canon for canon, _ in canonical_faces)
    for canon in sorted(counts):
        if counts[canon] > 1:
            faces = sorted(fi for c2, fi in canonical_faces if c2 == canon)
            add(
                "DUPLICATE_FACE", SEVERITY_WARNING,
                f"{counts[canon]} faces reference the same vertex triple",
                ("face",) + canon, REPAIR_AUTO,
                {"faces": faces, "count": counts[canon]},
            )

    # ---- 3. 边拓扑：开放边界 / 非流形 / 绕序 ------------------------
    # edge (u, v), u < v -> [(face_index, direction)]，direction=+1 表示面沿 u->v 经过
    edges = defaultdict(list)
    for fi, (a, b, c) in topo_faces:
        for x, y in ((a, b), (b, c), (c, a)):
            key = (x, y) if x < y else (y, x)
            edges[key].append((fi, 1 if x < y else -1))

    for u, v in sorted(edges):
        lst = edges[(u, v)]
        loc = ("edge", u, v)
        if len(lst) == 1:
            add(
                "OPEN_BOUNDARY", SEVERITY_WARNING,
                "edge is used by exactly one triangle (mesh boundary/hole)",
                loc, REPAIR_MANUAL,
                {"faces": [lst[0][0]]},
            )
        elif len(lst) > 2:
            add(
                "NON_MANIFOLD_EDGE", SEVERITY_ERROR,
                f"edge is shared by {len(lst)} triangles (> 2)",
                loc, REPAIR_MANUAL,
                {"faces": sorted(f for f, _ in lst)},
            )
        elif lst[0][1] == lst[1][1]:
            add(
                "INCONSISTENT_WINDING", SEVERITY_WARNING,
                "adjacent triangles traverse this edge in the same direction",
                loc, REPAIR_AUTO,
                {"faces": sorted(f for f, _ in lst)},
            )

    # ---- 4. 骨骼权重 ------------------------------------------------
    if mesh.weights is not None and len(mesh.weights) == n_verts:
        for vi, wlist in enumerate(mesh.weights):
            entries = list(wlist) if wlist else []
            if not entries:
                add(
                    "MISSING_WEIGHTS", SEVERITY_WARNING,
                    f"vertex {vi} has no bone weights (will break skinning)",
                    ("vertex", vi), REPAIR_MANUAL,
                )
                continue
            total = 0.0
            negative = False
            for _bone, w in entries:
                total += w
                if w < 0:
                    negative = True
            if negative:
                add(
                    "NEGATIVE_WEIGHT", SEVERITY_ERROR,
                    f"vertex {vi} has a negative bone weight",
                    ("vertex", vi), REPAIR_MANUAL,
                )
            if abs(total - 1.0) > weight_tolerance:
                add(
                    "WEIGHT_SUM", SEVERITY_WARNING,
                    f"vertex {vi} weights sum to {total:.6f}, expected 1.0",
                    ("vertex", vi), REPAIR_AUTO,
                    {"sum": total},
                )

    # ---- 5. UV 岛（信息） -------------------------------------------
    # 顶点级 UV 下，共享边即 UV 连续，因此 UV 岛 == 有效网格的连通分量。
    if mesh.uvs is not None and len(mesh.uvs) == n_verts and topo_faces:
        slot = {fi: k for k, (fi, _tri) in enumerate(topo_faces)}
        parent = list(range(len(topo_faces)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        for lst in edges.values():
            first = slot[lst[0][0]]
            for f, _dir in lst[1:]:
                union(first, slot[f])
        islands = len({find(i) for i in range(len(topo_faces))})
        add(
            "UV_ISLANDS", SEVERITY_INFO,
            f"mesh contains {islands} UV island(s)",
            ("mesh",), REPAIR_INFO,
            {"islands": islands},
        )

    return ValidationReport(mesh.name, diagnostics)
