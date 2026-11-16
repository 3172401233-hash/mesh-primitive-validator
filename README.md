# mesh-primitive-validator

Python 游戏网格资产校验库，在导入引擎前拦截非流形边、反向面、断裂 UV、
骨骼权重不一致等问题，避免到运行时才以阴影像素或蒙皮异常的形式暴露。

## 用法

```python
from mesh_validator import Mesh, validate

mesh = Mesh(
    positions=[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
    triangles=[(0, 1, 2), (0, 2, 3)],
    normals=[(0, 0, 1)] * 4,          # 可选，每顶点
    uvs=[(0, 0), (1, 0), (1, 1), (0, 1)],  # 可选，每顶点
    materials=[0, 0],                 # 可选，每三角形
    weights=[[(0, 1.0)]] * 4,         # 可选，每顶点 [(骨骼, 权重)]
)
report = validate(mesh)
print(report.summary())
```

运行测试：`python -m unittest`

## 设计约束

- **只读零拷贝**：`validate()` 直接引用输入序列，绝不复制或修改网格数据，
  大网格可以反复校验而不产生额外内存拷贝。
- **顺序无关**：所有诊断以规范化位置定位（边用排序后的顶点对、面用排序后的
  顶点三元组），同一网格改变三角形声明顺序后 `report.signature()` 完全一致。
- **不修改原网格**：校验器只输出诊断，修复由调用方决定。

## 检查项与修复方式

| 诊断码 | 级别 | 含义 | 修复 |
| --- | --- | --- | --- |
| `DEGENERATE_FACE` | error | 重复顶点索引或零面积面 | 自动（删除该面） |
| `DUPLICATE_FACE` | warning | 多个面引用同一顶点三元组 | 自动（去重） |
| `INCONSISTENT_WINDING` | warning | 相邻面沿共享边同向，法线会打架 | 自动（翻转其中一面绕序） |
| `WEIGHT_SUM` | warning | 顶点骨骼权重和不为 1 | 自动（归一化） |
| `OPEN_BOUNDARY` | warning | 边只属于一个三角形（孔洞/裂缝） | 人工（补孔涉及造型意图） |
| `NON_MANIFOLD_EDGE` | error | 边被 3 个以上面共享 | 人工（拆分/重建拓扑） |
| `ATTRIBUTE_LENGTH` | error | 法线/UV/权重/材质数量与网格不符 | 人工（导出线数据错误） |
| `INDEX_OUT_OF_RANGE` | error | 面引用越界顶点索引 | 人工（导出线数据错误） |
| `MISSING_WEIGHTS` | warning | 顶点没有任何骨骼权重 | 人工（需重新蒙皮/权重传递） |
| `NEGATIVE_WEIGHT` | error | 存在负权重 | 人工 |
| `UV_ISLANDS` | info | UV 岛数量（连通分量） | 仅信息 |
