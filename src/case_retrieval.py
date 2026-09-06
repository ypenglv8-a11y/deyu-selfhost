"""案例检索：标签 + 关键词的轻量检索（第一版无 RAG）。

设计原则（对应《案例底座建设方案.md》）：
- 案例是类比，不是答案：检索输出只给「机制要点 + 适用/不适用条件」的摘要，
  不给原文细节，防止 AI 机械照搬某个案例的处理过程。
- 检索顺序：先精确（problem_types / keywords）→ 后泛化（六维）。
- high_risk 案例仅作理解参考，不输出操作建议。

对外只暴露两个类：
  CaseRetriever      —— 加载案例库、检索、格式化提示词块
  infer_dimensions   —— 从事件文本推断六维（规则表 + 典型信号词）

案例库缺失/损坏时所有入口静默降级（返回空），不影响主分析流程。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_CASES_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "cases"

# 六维中文名 ↔ 目录名（与 six_dimensions.md 保持一致）
DIM_TO_DIR = {
    "同伴关系": "peer_relationship",
    "师生关系": "teacher_student",
    "家庭亲子": "family",
    "自我与情绪": "emotion_self",
    "学业发展": "learning_development",
    "规则与行为": "discipline_behavior",
}

# event_type → 六维（规则表，来自 six_dimensions.md；LLM 仅作补充）
_EVENT_TYPE_DIM = {
    "迟到": ["规则与行为"],
    "课堂纪律": ["规则与行为", "师生关系"],
    "作业": ["学业发展"],
    "情绪": ["自我与情绪"],
    "人际": ["同伴关系"],
    "手机": ["规则与行为"],
    "健康": ["自我与情绪"],  # 生理健康不归类，由调用方过滤
    "其他": [],
}

# 六维典型信号词（来自 six_dimensions.md 典型信号列 + 常用同义词，保持克制）
_DIM_SIGNALS: Dict[str, List[str]] = {
    "同伴关系": ["同伴", "同学", "朋友", "孤立", "排挤", "欺负", "欺凌", "社交",
               "早恋", "恋爱", "异性", "宿舍关系", "被排斥", "无朋友", "冲突反复"],
    "师生关系": ["顶撞", "顶嘴", "对抗", "师生", "回避老师", "课堂对立", "不信任老师"],
    "家庭亲子": ["家长", "父母", "家庭", "离异", "单亲", "留守", "亲子", "家访",
               "经济困难", "亲子冲突"],
    "自我与情绪": ["情绪", "焦虑", "抑郁", "紧张", "自卑", "退缩", "躺平", "厌学",
                 "哭泣", "愤怒", "压力", "失眠", "躯体", "自伤", "危机", "低落",
                 "消极", "内耗", "迷茫"],
    "学业发展": ["学习", "成绩", "作业", "上课", "听课", "考试", "逃课", "退步",
                "分心", "动力", "目标", "学业", "选科", "生涯"],
    "规则与行为": ["违纪", "迟到", "手机", "吸烟", "抽烟", "打架", "旷课", "纪律",
                 "扣分", "破坏", "规则", "屡教不改", "课堂纪律", "看课外书"],
}

_GRADE_ORDER = {"小学": 0, "初中": 1, "高中": 2}


def infer_grade_from_class(class_name: str) -> str:
    """从班级名推断学段：高一/高二/高三→高中；初*→初中；其余按小学。"""
    if not class_name:
        return ""
    if any(k in class_name for k in ("高一", "高二", "高三", "高中")):
        return "高中"
    if any(k in class_name for k in ("初一", "初二", "初三", "七年级", "八年级", "九年级", "初中")):
        return "初中"
    return "小学"


def infer_dimensions(text: str, event_type: str = "") -> Dict[str, float]:
    """从事件文本推断六维及强度（0~1），规则表 + 信号词。"""
    scores: Dict[str, float] = {}
    for dim, words in _DIM_SIGNALS.items():
        hit = sum(1 for w in words if w in text)
        if hit:
            scores[dim] = min(1.0, 0.3 + 0.2 * hit)
    # 规则表：event_type 映射为强信号
    for dim in _EVENT_TYPE_DIM.get(event_type, []):
        scores[dim] = max(scores.get(dim, 0), 0.8)
    return scores


class _Case:
    """单个案例的内存表示。"""

    def __init__(self, meta: dict, body: str):
        self.meta = meta
        self.body = body
        self._sections: Optional[Dict[str, str]] = None

    @property
    def case_id(self) -> str:
        return self.meta.get("case_id", "?")

    @property
    def grade(self) -> str:
        return self.meta.get("grade", "")

    @property
    def high_risk(self) -> bool:
        return bool(self.meta.get("high_risk"))

    def section(self, name: str) -> str:
        """提取正文某节（如 有效机制）下的列表项文本。"""
        if self._sections is None:
            self._sections = self._parse_sections()
        return self._sections.get(name, "")

    def _parse_sections(self) -> Dict[str, str]:
        sections: Dict[str, str] = {}
        cur: Optional[str] = None
        buf: List[str] = []
        for line in self.body.splitlines():
            m = re.match(r"^##\s+(.+)$", line.strip())
            if m:
                if cur and buf:
                    sections[cur] = "\n".join(buf)
                cur = m.group(1).strip()
                buf = []
            elif cur is not None:
                buf.append(line.strip())
        if cur and buf:
            sections[cur] = "\n".join(buf)
        return sections

    def bullets(self, section: str, limit: int = 3) -> List[str]:
        """取某节的前 limit 条列表项（去掉 '-' 前缀）。"""
        raw = self.section(section)
        items = [re.sub(r"^[-*]\s*", "", ln.strip())
                 for ln in raw.splitlines()
                 if ln.strip().startswith(("-", "*"))]
        return [i for i in items if i][:limit]

    def summary(self) -> Dict[str, object]:
        """检索展示用摘要（不含学生原文细节，防机械模仿）。"""
        mech = self.bullets("有效机制", 3) or self.bullets("可迁移策略", 3)
        return {
            "case_id": self.case_id,
            "name": self.meta.get("name", ""),
            "grade": self.grade,
            "problem_types": self.meta.get("problem_types", []),
            "mechanisms": mech,
            "applicable": self.bullets("适用条件", 2),
            "not_applicable": self.bullets("不适用条件", 2),
            "high_risk": self.high_risk,
        }


class CaseRetriever:
    """加载 `knowledge/cases/` 案例库并提供检索。"""

    def __init__(self, cases_dir: Optional[Path] = None):
        self.cases_dir = Path(cases_dir) if cases_dir else _CASES_DIR
        self._cases: List[_Case] = []
        self._load()

    def _load(self) -> None:
        index = self.cases_dir / "_index.json"
        if not index.exists():
            return
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for meta in data.get("cases", []):
            rel = meta.get("file", "")
            path = self.cases_dir / rel if rel else None
            if path is None or not path.exists():
                continue
            try:
                body = path.read_text(encoding="utf-8")
            except OSError:
                continue
            self._cases.append(_Case(meta, body))

    # ------------------------------------------------------------ 检索
    def search(self, text: str, event_type: str = "", grade: str = "",
               top_k: int = 3) -> List[_Case]:
        """打分检索：problem_types 精确 > 关键词 > 六维 > 学段参考。"""
        if not self._cases:
            return []
        inferred = infer_dimensions(text, event_type)
        scored = []
        for c in self._cases:
            s = self._score(c, text, inferred, grade)
            if s > 0:
                scored.append((s, c))
        scored.sort(key=lambda x: -x[0])
        return [c for _, c in scored[:top_k]]

    def _score(self, case: _Case, text: str, inferred: Dict[str, float],
               grade: str) -> float:
        s = 0.0
        # 精确：problem_types 命中（权重最高）
        for pt in case.meta.get("problem_types", []):
            if pt and pt in text:
                s += 3.0
        # 关键词命中
        for kw in case.meta.get("keywords", []):
            if kw and kw in text:
                s += 1.0
        # 六维兜底：按案例维度权重 × 推断强度
        for dim, w in case.meta.get("dimensions", {}).items():
            s += 2.0 * (w / 3.0) * inferred.get(dim, 0.0)
        # 无任何内容命中：不参与检索（学段加分不能单独构成命中）
        if s == 0:
            return 0.0
        # 学段偏好：同段强加分，跨段仅弱参考
        if case.grade and grade:
            if case.grade == grade:
                s += 1.0
            elif case.grade == "高中":  # 系统服务高中，高中案例跨学段也优先
                s += 0.5
            else:
                s += 0.2
        return s

    # ------------------------------------------------------------ 输出
    def format_for_prompt(self, hits: List[_Case]) -> str:
        """把命中案例格式化为提示词块（类比参考，不输出原文细节）。"""
        if not hits:
            return ""
        lines = ["【相似案例参考】(以下案例仅作类比启发，不是答案；"
                 "必须结合本生学段/性格/家庭/历史差异判断，禁止机械套用)"]
        for c in hits:
            s = c.summary()
            if s["high_risk"]:
                lines.append(
                    f"- {s['case_id']}《{s['name']}》| {s['grade']} | "
                    f"问题:{','.join(s['problem_types'][:3])}")
                lines.append(
                    "  ⚠️ 高风险案例：仅作理解参考，不输出操作建议；"
                    "如涉心理危机请按学校心理危机流程处理")
                continue
            mech = "；".join(s["mechanisms"]) or "（原文未提炼机制）"
            app = "；".join(s["applicable"]) or "—"
            napp = "；".join(s["not_applicable"]) or "—"
            lines.append(
                f"- {s['case_id']}《{s['name']}》| {s['grade']} | "
                f"问题:{','.join(s['problem_types'][:3])}")
            lines.append(f"  核心机制：{mech}")
            lines.append(f"  适用：{app}")
            lines.append(f"  不适用：{napp}")
        return "\n".join(lines)
