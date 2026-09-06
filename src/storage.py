"""存储抽象层：定义智能体所需的全部数据操作。

设计意图：
- 本接口是"平台无关"的 —— 云端智能体只依赖这套接口读写数据。
- 当前实现：SQLite（本地开发 / 云上单机运行）。
- 钉钉通道接入后：实现 DingTalkStorage（通过 dws / 钉钉 API 读写 AI表格），
  智能体其余代码零改动 —— 见 storage_dingtalk.py 的接口说明。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import Case, Event, GrowthReport, Student, Teacher


class Storage(ABC):
    # ---------- 学生 ----------
    @abstractmethod
    def get_student(self, student_id: str) -> Optional[Student]: ...

    @abstractmethod
    def list_students(self, class_name: Optional[str] = None) -> List[Student]: ...

    @abstractmethod
    def upsert_student(self, student: Student) -> None: ...

    # ---------- 事件 ----------
    @abstractmethod
    def add_event(self, event: Event) -> str: ...

    @abstractmethod
    def get_event(self, event_id: str) -> Optional[Event]: ...

    @abstractmethod
    def list_events(self, student_id: Optional[str] = None,
                    since: Optional[str] = None,
                    status: Optional[str] = None) -> List[Event]: ...

    @abstractmethod
    def update_event(self, event: Event) -> None: ...

    @abstractmethod
    def events_needing_analysis(self) -> List[Event]:
        """待 AI 分析的事件：AI 分析字段为空 且 状态未闭环"""
        ...

    @abstractmethod
    def events_closed_for_case(self) -> List[Event]:
        """满足案例沉淀条件的事件（已闭环 + 有结果）"""
        ...

    # ---------- 案例 ----------
    @abstractmethod
    def add_case(self, case: Case) -> str: ...

    @abstractmethod
    def list_cases(self, status: Optional[str] = None) -> List[Case]: ...

    # ---------- 教师 / 角色 ----------
    @abstractmethod
    def list_teachers(self, role: Optional[str] = None) -> List[Teacher]: ...

    @abstractmethod
    def upsert_teacher(self, teacher: Teacher) -> None: ...

    @abstractmethod
    def student_ids_for_teacher(self, teacher_name: str) -> List[str]:
        """某教师可见的学生范围（班主任=本班；德育导师=名下学生）"""
        ...

    # ---------- 成长报告 ----------
    @abstractmethod
    def add_report(self, report: GrowthReport) -> str: ...

    @abstractmethod
    def list_reports(self, student_id: Optional[str] = None) -> List[GrowthReport]: ...
