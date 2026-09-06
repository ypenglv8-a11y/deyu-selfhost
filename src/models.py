"""数据模型：与钉钉 AI 表格 5 张表对应的实体定义。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# ---- 枚举（与表格点选项一致）----

EVENT_TYPES = ["迟到", "课堂纪律", "作业", "情绪", "人际", "手机", "健康", "其他"]
SEVERITIES = ["轻", "中", "重"]
RESULTS = ["改善", "部分改善", "暂无改善", "观察中"]
EVENT_STATUS = ["待跟进", "跟进中", "已闭环"]
RISK_LEVELS = ["🟢 正常", "🟡 关注", "🔴 重点干预"]
ROLES = ["班主任", "德育导师", "年级主任", "德育主任", "管理员"]
CASE_STATUS = ["草稿", "已确认", "已发布", "内部"]

# L 分级
L1, L2, L3 = "L1", "L2", "L3"


@dataclass
class Student:
    """学生档案（对应 01_学生档案表）"""
    id: str                          # 内部 id（学号或序号）
    name: str
    class_name: str
    gender: str                      # 男 / 女
    boarding: str                    # 住宿 / 走读
    dorm: str = ""                   # 宿舍号
    tutor: str = ""                  # 德育导师姓名（权限源头字段）
    key_vars: str = ""               # 关键变量备注（家庭/同伴/健康等）
    risk_level: str = "🟢 正常"      # 历史关注等级（仅教师维护）
    latest_change_note: str = ""     # 最近变化提示（AI 每周更新）
    entry_year: int = 2026

    def deidentified(self) -> str:
        """脱敏特征描述（用于案例库）：不含姓名/班级/宿舍号等可定位信息。

        规则：性别 + 住宿类型即可；宿舍号会缩小到个位数学生，容易定位，一律不出现。
        若要表达"宿舍违纪比例高"这类背景，请放在案例 background 的"分析"里描述现象，
        不写具体宿舍号。
        """
        return f"{self.gender}·{self.boarding}生"


@dataclass
class Event:
    """事件记录（对应 02_事件记录表）—— 老师端只填 4 字段，其余 AI 生成"""
    id: str
    student_id: str
    student_name: str
    date: str                        # YYYY-MM-DD
    event_type: str
    description: str                 # 一句话（可空）
    severity: str = "中"             # 轻/中/重
    # 老师补填
    handling: str = ""               # 处理方式
    result: str = ""                 # 改善/部分改善/暂无改善/观察中
    status: str = "待跟进"
    recorder_role: str = ""
    recorder: str = ""
    # AI 生成（写回）
    level: str = ""                  # L1/L2/L3（AI 判定）
    ai_analysis: str = ""            # 归因分析（多解释路径）
    ai_suggestions: str = ""         # 建议（1-3 条）
    ai_followup: str = ""            # 跟进计划
    # 连贯引导：上一条事件的处理效果
    prev_event_id: str = ""
    prev_suggestion: str = ""
    prev_result: str = ""
    analysis_fail_count: int = 0

    def is_closed_for_case(self) -> bool:
        """是否满足案例沉淀条件：已闭环 + 结果已填"""
        return self.status == "已闭环" and self.result in ("改善", "部分改善", "暂无改善")


@dataclass
class Case:
    """案例（对应 03_案例库表）—— 副产品"""
    id: str
    event_id: str
    student_id: str
    title: str
    problem_type: str
    deidentified_profile: str        # 脱敏学生特征
    background: str
    analysis: str
    process: str                     # 处理过程
    outcome: str                     # 结果
    reusable_principle: str          # 可复用要点（1-2 条）
    applicable: str = ""             # 适用场景
    not_applicable: str = ""         # 不适用场景
    status: str = "草稿"
    creator: str = ""
    created_at: str = ""


@dataclass
class Teacher:
    """教师角色（对应 04_角色班级表）"""
    name: str
    role: str                        # 班主任/德育导师/年级主任/德育主任/管理员
    class_name: str = ""
    students: List[str] = field(default_factory=list)  # 德育导师名下学生 id


@dataclass
class GrowthReport:
    """成长报告（对应 05_成长报告表）"""
    id: str
    student_id: str
    student_name: str
    period: str                      # 如 2026-09 / 2026 秋季学期
    content: str
    created_at: str = ""
