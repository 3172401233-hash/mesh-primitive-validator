"""网格数据结构。

校验器对输入只读：不复制顶点/索引缓冲，不做任何就地修改。
所有序列字段仅要求支持 len() 和下标访问（list、tuple、array 等均可）。
"""

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]
Vec2 = Tuple[float, float]
Triangle = Sequence[int]
# 每顶点骨骼权重: [(骨骼索引, 权重), ...]
VertexWeights = Sequence[Tuple[int, float]]


@dataclass
class Mesh:
    positions: Sequence[Vec3]
    triangles: Sequence[Triangle]
    normals: Optional[Sequence[Vec3]] = None
    uvs: Optional[Sequence[Vec2]] = None
    # 每三角形一个材质槽索引
    materials: Optional[Sequence[int]] = None
    # 每顶点一组 (骨骼索引, 权重)
    weights: Optional[Sequence[VertexWeights]] = None
    name: str = "mesh"
