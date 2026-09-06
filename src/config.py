"""配置：全部通过环境变量读取，缺省值适用于本地开发与云上单机运行。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    db_path: str = field(
        default_factory=lambda: os.environ.get("DEYU_DB", "data/deyu.db"))
    llm_mock: bool = field(
        default_factory=lambda: os.environ.get("DEYU_LLM_MOCK", "0") == "1")
    api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("DEEPSEEK_API_KEY") or None)
    model: str = field(
        default_factory=lambda: os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))
    base_url: str = field(
        default_factory=lambda: os.environ.get("DEEPSEEK_BASE_URL",
                                               "https://api.deepseek.com"))
    # 调度窗口
    analysis_interval_minutes: int = field(
        default_factory=lambda: int(os.environ.get("DEYU_ANALYSIS_INTERVAL", "5")))
    weekly_day: int = field(
        default_factory=lambda: int(os.environ.get("DEYU_WEEKLY_DAY", "1")))   # 0=周一
    weekly_hour: int = field(
        default_factory=lambda: int(os.environ.get("DEYU_WEEKLY_HOUR", "8")))
    report_day: int = field(
        default_factory=lambda: int(os.environ.get("DEYU_REPORT_DAY", "1")))   # 每月1日
    report_hour: int = field(
        default_factory=lambda: int(os.environ.get("DEYU_REPORT_HOUR", "9")))
    # 案例沉淀：事件闭环后至少等待天数
    case_min_wait_days: int = field(
        default_factory=lambda: int(os.environ.get("DEYU_CASE_MIN_WAIT", "3")))
    # 每日推送扫描时刻（回访到期/周计划/周总结）
    notify_hour: int = field(
        default_factory=lambda: int(os.environ.get("DEYU_NOTIFY_HOUR", "8")))
