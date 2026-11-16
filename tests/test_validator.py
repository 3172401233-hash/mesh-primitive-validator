import copy
import random
import unittest

from mesh_validator import Mesh, validate


def tetrahedron():
    positions = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    ]
    # 四个面均为外向绕序，封闭无边界
    triangles = [(1, 2, 3), (0, 3, 2), (0, 1, 3), (0, 2, 1)]
    return positions, triangles


def quad():
    positions = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    triangles = [(0, 1, 2), (0, 2, 3)]
    return positions, triangles


def grid_with_hole():
    # 4x4 顶点、3x3 单元格，去掉中心单元格形成方孔
    positions = [(float(x), float(y), 0.0) for y in range(4) for x in range(4)]

    def vid(x, y):
        return y * 4 + x

    triangles = []
    for y in range(3):
        for x in range(3):
            if x == 1 and y == 1:
                continue
            a, b, c, d = vid(x, y), vid(x + 1, y), vid(x + 1, y + 1), vid(x, y + 1)
            triangles.append((a, b, c))
            triangles.append((a, c, d))
    return positions, triangles


def messy_mesh():
    positions = [
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0),  # 0-3 quad
        (0.0, 5.0, 0.0), (1.0, 5.0, 0.0), (2.0, 5.0, 0.0),                  # 4-6 共线
        (0.0, 9.0, 0.0), (1.0, 9.0, 0.0),                                   # 7-8 非流形公共边
        (0.5, 10.0, 0.0), (0.5, 8.0, 1.0), (0.5, 8.0, -1.0),                # 9-11
        (5.0, 0.0, 0.0), (6.0, 0.0, 0.0), (5.5, 1.0, 0.0), (5.5, -1.0, 0.0),  # 12-15 绕序
    ]
    triangles = [
        (0, 1, 2), (0, 2, 3),      # 正常 quad
        (2, 1, 0),                 # 与 (0,1,2) 重复（顶点集相同）
        (2, 2, 3),                 # 索引退化
        (4, 5, 6),                 # 几何退化（共线）
        (7, 8, 9), (7, 8, 10), (8, 7, 11),  # 边 (7,8) 被 3 个面共享 -> 非流形
        (12, 13, 14), (12, 13, 15),         # 边 (12,13) 同向 -> 绕序不一致
    ]
    weights = [[(0, 1.0)]] * 15 + [[]]  # 顶点 15 缺失权重
    weights[14] = [(0, 0.4), (1, 0.4)]  # 权重和 0.8
    return Mesh(positions=positions, triangles=triangles, weights=weights, name="messy")


def rotations(tri):
    a, b, c = tri
    return [(a, b, c), (b, c, a), (c, a, b)]


def shuffled(mesh, seed):
    rng = random.Random(seed)
    tris = list(mesh.triangles)
    rng.shuffle(tris)
    tris = [rng.choice(rotations(tuple(t))) for t in tris]
    return Mesh(
        positions=mesh.positions,
        triangles=tris,
        normals=mesh.normals,
        uvs=mesh.uvs,
        materials=mesh.materials,
        weights=mesh.weights,
        name=mesh.name,
    )


class TestClosedSolid(unittest.TestCase):
    def test_clean_tetrahedron(self):
        positions, triangles = tetrahedron()
        mesh = Mesh(
            positions=positions,
            triangles=triangles,
            normals=[(0.0, 0.0, 1.0)] * 4,
            uvs=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
            materials=[0, 0, 1, 1],
            weights=[[(0, 1.0)]] * 4,
            name="tetra",
        )
        report = validate(mesh)
        self.assertTrue(report.ok, report.summary())
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])
        islands = report.by_code("UV_ISLANDS")
        self.assertEqual(len(islands), 1)
        self.assertEqual(islands[0].details["islands"], 1)


class TestOpenSurface(unittest.TestCase):
    def test_grid_with_hole_boundaries(self):
        positions, triangles = grid_with_hole()
        report = validate(Mesh(positions=positions, triangles=triangles))
        self.assertFalse(report.errors)
        openings = report.by_code("OPEN_BOUNDARY")
        # 外圈 12 条 + 内孔 4 条
        self.assertEqual(len(openings), 16)
        self.assertFalse(report.by_code("NON_MANIFOLD_EDGE"))
        self.assertFalse(report.by_code("INCONSISTENT_WINDING"))
        # 内孔角点 (1,1) -> 顶点 5，孔边 (5,6) 必须被定位到
        self.assertIn(("edge", 5, 6), [d.location for d in openings])

    def test_single_quad_boundary(self):
        positions, triangles = quad()
        report = validate(Mesh(positions=positions, triangles=triangles))
        self.assertEqual(len(report.by_code("OPEN_BOUNDARY")), 4)
        self.assertFalse(report.errors)


class TestUVIslands(unittest.TestCase):
    def test_multiple_uv_islands(self):
        p1, t1 = quad()
        p2 = [(x + 5.0, y, z) for x, y, z in p1]
        t2 = [(a + 4, b + 4, c + 4) for a, b, c in t1]
        mesh = Mesh(
            positions=p1 + p2,
            triangles=t1 + t2,
            uvs=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)] * 2,
        )
        report = validate(mesh)
        islands = report.by_code("UV_ISLANDS")
        self.assertEqual(len(islands), 1)
        self.assertEqual(islands[0].details["islands"], 2)


class TestWeights(unittest.TestCase):
    def test_missing_and_unnormalized_weights(self):
        positions, triangles = quad()
        mesh = Mesh(
            positions=positions,
            triangles=triangles,
            weights=[[(0, 1.0)], [], [(0, 0.5), (1, 0.4)], [(0, 1.0)]],
        )
        report = validate(mesh)
        missing = report.by_code("MISSING_WEIGHTS")
        self.assertEqual([d.location for d in missing], [("vertex", 1)])
        sums = report.by_code("WEIGHT_SUM")
        self.assertEqual([d.location for d in sums], [("vertex", 2)])

    def test_negative_weight(self):
        positions, triangles = quad()
        mesh = Mesh(
            positions=positions,
            triangles=triangles,
            weights=[[(0, 1.0)]] * 3 + [[(0, 1.5), (1, -0.5)]],
        )
        report = validate(mesh)
        self.assertEqual(len(report.by_code("NEGATIVE_WEIGHT")), 1)


class TestTopologyProblems(unittest.TestCase):
    def test_degenerate_faces(self):
        positions, triangles = quad()
        positions = positions + [(2.0, 0.0, 0.0), (3.0, 0.0, 0.0), (4.0, 0.0, 0.0)]
        triangles = triangles + [(0, 0, 1), (4, 5, 6)]  # 索引退化 + 共线退化
        report = validate(Mesh(positions=positions, triangles=triangles))
        degen = report.by_code("DEGENERATE_FACE")
        self.assertEqual(len(degen), 2)
        self.assertIn(("face", 0, 0, 1), [d.location for d in degen])
        self.assertIn(("face", 4, 5, 6), [d.location for d in degen])

    def test_duplicate_faces(self):
        positions, triangles = quad()
        triangles = triangles + [(2, 1, 0), (0, 1, 2)]  # 与 (0,1,2) 顶点集相同
        report = validate(Mesh(positions=positions, triangles=triangles))
        dup = report.by_code("DUPLICATE_FACE")
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0].location, ("face", 0, 1, 2))
        self.assertEqual(dup[0].details["count"], 3)

    def test_non_manifold_edge(self):
        positions = [
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
            (0.5, 1.0, 0.0), (0.5, 0.0, 1.0), (0.5, 0.0, -1.0),
        ]
        triangles = [(0, 1, 2), (0, 1, 3), (1, 0, 4)]
        report = validate(Mesh(positions=positions, triangles=triangles))
        nm = report.by_code("NON_MANIFOLD_EDGE")
        self.assertEqual(len(nm), 1)
        self.assertEqual(nm[0].location, ("edge", 0, 1))

    def test_inconsistent_winding(self):
        positions = [
            (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.5, 1.0, 0.0), (0.5, -1.0, 0.0),
        ]
        triangles = [(0, 1, 2), (0, 1, 3)]  # 共享边 (0,1) 同向
        report = validate(Mesh(positions=positions, triangles=triangles))
        wind = report.by_code("INCONSISTENT_WINDING")
        self.assertEqual(len(wind), 1)
        self.assertEqual(wind[0].location, ("edge", 0, 1))


class TestAttributeErrors(unittest.TestCase):
    def test_length_mismatch(self):
        positions, triangles = quad()
        mesh = Mesh(
            positions=positions,
            triangles=triangles,
            normals=[(0.0, 0.0, 1.0)] * 3,   # 应为 4
            uvs=[(0.0, 0.0)] * 5,            # 应为 4
            materials=[0],                   # 应为 2
        )
        report = validate(mesh)
        attrs = {d.location[1] for d in report.by_code("ATTRIBUTE_LENGTH")}
        self.assertEqual(attrs, {"normals", "uvs", "materials"})

    def test_index_out_of_range(self):
        positions, triangles = quad()
        triangles = triangles + [(0, 1, 9)]
        report = validate(Mesh(positions=positions, triangles=triangles))
        oor = report.by_code("INDEX_OUT_OF_RANGE")
        self.assertEqual(len(oor), 1)
        self.assertEqual(oor[0].details["indices"], [9])


class TestOrderInvariance(unittest.TestCase):
    def test_problem_set_stable_under_shuffle(self):
        base = messy_mesh()
        expected = validate(base).signature()
        for seed in (1, 7, 42, 2024):
            report = validate(shuffled(base, seed))
            self.assertEqual(report.signature(), expected, f"seed={seed}\n{report.summary()}")

    def test_messy_mesh_finds_all_problem_kinds(self):
        report = validate(messy_mesh())
        codes = {d.code for d in report.diagnostics}
        self.assertTrue(
            {
                "DEGENERATE_FACE",
                "DUPLICATE_FACE",
                "OPEN_BOUNDARY",
                "NON_MANIFOLD_EDGE",
                "INCONSISTENT_WINDING",
                "MISSING_WEIGHTS",
                "WEIGHT_SUM",
            }.issubset(codes)
        )


class TestReadOnly(unittest.TestCase):
    def test_input_not_modified(self):
        mesh = messy_mesh()
        snapshot = copy.deepcopy(
            (mesh.positions, mesh.triangles, mesh.weights)
        )
        validate(mesh)
        self.assertEqual((mesh.positions, mesh.triangles, mesh.weights), snapshot)


if __name__ == "__main__":
    unittest.main()
