"""诊断与校验报告。

每个 Diagnostic 的 location 是规范化的稳定元组（与三角形声明顺序无关）：
  ("edge", u, v)      u < v，顶点索引对
  ("face", a, b, c)   a < b < c，排序后的顶点索引三元组
  ("vertex", i)       顶点索引
  ("attribute", name) 属性名
  ("mesh",)           整体信息
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

REPAIR_AUTO = "auto"      # 工具可安全自动修复
REPAIR_MANUAL = "manual"  # 需要美术/TA 人工处理
REPAIR_INFO = "info"      # 仅信息，无需修复

REPAIR_LABELS = {
    REPAIR_AUTO: "可自动修复",
    REPAIR_MANUAL: "需人工处理",
    REPAIR_INFO: "信息",
}


@dataclass(eq=False)
class Diagnostic:
    code: str
    severity: str
    message: str
    location: Tuple
    repair: str = REPAIR_MANUAL
    details: Dict = field(default_factory=dict)

    def key(self) -> Tuple:
        return (self.code, self.location)

    def __repr__(self) -> str:
        return f"[{self.severity}] {self.code} @ {self.location}: {self.message}"


class ValidationReport:
    def __init__(self, mesh_name: str, diagnostics: List[Diagnostic]):
        self.mesh_name = mesh_name
        self.diagnostics = sorted(diagnostics, key=lambda d: (d.code, d.location))

    def by_code(self, code: str) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.code == code]

    def by_severity(self, severity: str) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == severity]

    @property
    def errors(self) -> List[Diagnostic]:
        return self.by_severity(SEVERITY_ERROR)

    @property
    def warnings(self) -> List[Diagnostic]:
        return self.by_severity(SEVERITY_WARNING)

    @property
    def infos(self) -> List[Diagnostic]:
        return self.by_severity(SEVERITY_INFO)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.warnings

    def signature(self) -> Tuple:
        """稳定签名：同一网格任意三角形声明顺序下结果一致。"""
        return tuple(d.key() for d in self.diagnostics)

    def auto_fixable_codes(self) -> List[str]:
        return sorted({d.code for d in self.diagnostics if d.repair == REPAIR_AUTO})

    def manual_only_codes(self) -> List[str]:
        return sorted({d.code for d in self.diagnostics if d.repair == REPAIR_MANUAL})

    def summary(self) -> str:
        lines = [
            f"mesh '{self.mesh_name}': "
            f"{len(self.errors)} error(s), "
            f"{len(self.warnings)} warning(s), "
            f"{len(self.infos)} info"
        ]
        counts: Dict[str, int] = {}
        for d in self.diagnostics:
            counts[d.code] = counts.get(d.code, 0) + 1
        for code in sorted(counts):
            lines.append(f"  {code}: {counts[code]}")
        auto = self.auto_fixable_codes()
        manual = self.manual_only_codes()
        if auto:
            lines.append(f"  可自动修复: {', '.join(auto)}")
        if manual:
            lines.append(f"  需人工处理: {', '.join(manual)}")
        return "\n".join(lines)
