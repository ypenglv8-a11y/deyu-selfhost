"""SQLite 实现：表结构与钉钉 AI表格 5 张表一一对应。"""
from __future__ import annotations

import json
import sqlite3
from typing import List, Optional

from .models import Case, Event, GrowthReport, Student, Teacher
from .storage import Storage

_SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    class_name TEXT NOT NULL,
    gender TEXT,
    boarding TEXT,
    dorm TEXT DEFAULT '',
    tutor TEXT DEFAULT '',
    key_vars TEXT DEFAULT '',
    risk_level TEXT DEFAULT '🟢 正常',
    latest_change_note TEXT DEFAULT '',
    entry_year INTEGER DEFAULT 2026
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    student_name TEXT NOT NULL,
    date TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT DEFAULT '',
    severity TEXT DEFAULT '中',
    handling TEXT DEFAULT '',
    result TEXT DEFAULT '',
    status TEXT DEFAULT '待跟进',
    recorder_role TEXT DEFAULT '',
    recorder TEXT DEFAULT '',
    level TEXT DEFAULT '',
    ai_analysis TEXT DEFAULT '',
    ai_suggestions TEXT DEFAULT '',
    ai_followup TEXT DEFAULT '',
    prev_event_id TEXT DEFAULT '',
    prev_suggestion TEXT DEFAULT '',
    prev_result TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    title TEXT,
    problem_type TEXT,
    deidentified_profile TEXT,
    background TEXT,
    analysis TEXT,
    process TEXT,
    outcome TEXT,
    reusable_principle TEXT,
    applicable TEXT DEFAULT '',
    not_applicable TEXT DEFAULT '',
    status TEXT DEFAULT '草稿',
    creator TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS teachers (
    name TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    class_name TEXT DEFAULT '',
    students_json TEXT DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    student_name TEXT NOT NULL,
    period TEXT NOT NULL,
    content TEXT,
    created_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_student ON events(student_id, date);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
"""


class SqliteStorage(Storage):
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        # 轻量迁移：旧库补列（幂等）
        cols = {r["name"] for r in self._conn.execute(
            "PRAGMA table_info(events)")}
        if "analysis_fail_count" not in cols:
            self._conn.execute(
                "ALTER TABLE events ADD COLUMN analysis_fail_count INTEGER DEFAULT 0")
        self._conn.commit()

    # ---------- 学生 ----------
    def get_student(self, student_id: str) -> Optional[Student]:
        row = self._conn.execute(
            "SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
        return self._row_to_student(row) if row else None

    def list_students(self, class_name: Optional[str] = None) -> List[Student]:
        if class_name:
            rows = self._conn.execute(
                "SELECT * FROM students WHERE class_name=?", (class_name,))
        else:
            rows = self._conn.execute("SELECT * FROM students")
        return [self._row_to_student(r) for r in rows.fetchall()]

    def upsert_student(self, s: Student) -> None:
        self._conn.execute(
            """INSERT INTO students (id,name,class_name,gender,boarding,dorm,tutor,key_vars,
                                     risk_level,latest_change_note,entry_year)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, class_name=excluded.class_name,
                 gender=excluded.gender, boarding=excluded.boarding,
                 dorm=excluded.dorm, tutor=excluded.tutor, key_vars=excluded.key_vars,
                 risk_level=excluded.risk_level,
                 latest_change_note=excluded.latest_change_note,
                 entry_year=excluded.entry_year""",
            (s.id, s.name, s.class_name, s.gender, s.boarding, s.dorm, s.tutor,
             s.key_vars, s.risk_level, s.latest_change_note, s.entry_year))
        self._conn.commit()

    # ---------- 事件 ----------
    def add_event(self, e: Event) -> str:
        self._conn.execute(
            """INSERT INTO events (id,student_id,student_name,date,event_type,description,
                                   severity,handling,result,status,recorder_role,recorder,
                                   level,ai_analysis,ai_suggestions,ai_followup,
                                   prev_event_id,prev_suggestion,prev_result)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (e.id, e.student_id, e.student_name, e.date, e.event_type, e.description,
             e.severity, e.handling, e.result, e.status, e.recorder_role, e.recorder,
             e.level, e.ai_analysis, e.ai_suggestions, e.ai_followup,
             e.prev_event_id, e.prev_suggestion, e.prev_result))
        self._conn.commit()
        return e.id

    def get_event(self, event_id: str) -> Optional[Event]:
        row = self._conn.execute(
            "SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return self._row_to_event(row) if row else None

    def list_events(self, student_id: Optional[str] = None,
                    since: Optional[str] = None,
                    status: Optional[str] = None) -> List[Event]:
        sql = "SELECT * FROM events WHERE 1=1"
        args = []
        if student_id:
            sql += " AND student_id=?"
            args.append(student_id)
        if since:
            sql += " AND date>=?"
            args.append(since)
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY date ASC"
        rows = self._conn.execute(sql, args).fetchall()
        return [self._row_to_event(r) for r in rows]

    def update_event(self, e: Event) -> None:
        self._conn.execute(
            """UPDATE events SET student_name=?,date=?,event_type=?,description=?,
               severity=?,handling=?,result=?,status=?,recorder_role=?,recorder=?,
               level=?,ai_analysis=?,ai_suggestions=?,ai_followup=?,
               prev_event_id=?,prev_suggestion=?,prev_result=?,analysis_fail_count=?
               WHERE id=?""",
            (e.student_name, e.date, e.event_type, e.description,
             e.severity, e.handling, e.result, e.status, e.recorder_role, e.recorder,
             e.level, e.ai_analysis, e.ai_suggestions, e.ai_followup,
             e.prev_event_id, e.prev_suggestion, e.prev_result,
             getattr(e, "analysis_fail_count", 0) or 0, e.id))
        self._conn.commit()

    def events_needing_analysis(self) -> List[Event]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE (ai_analysis='' OR ai_analysis IS NULL) "
            "AND status!='已闭环' AND status!='analysis_failed'"
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def events_closed_for_case(self) -> List[Event]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE status='已闭环' AND result IN ('改善','部分改善','暂无改善')"
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    # ---------- 案例 ----------
    def add_case(self, c: Case) -> str:
        self._conn.execute(
            """INSERT INTO cases (id,event_id,student_id,title,problem_type,
                                  deidentified_profile,background,analysis,process,outcome,
                                  reusable_principle,applicable,not_applicable,status,creator,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c.id, c.event_id, c.student_id, c.title, c.problem_type,
             c.deidentified_profile, c.background, c.analysis, c.process, c.outcome,
             c.reusable_principle, c.applicable, c.not_applicable, c.status,
             c.creator, c.created_at))
        self._conn.commit()
        return c.id

    def list_cases(self, status: Optional[str] = None) -> List[Case]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM cases WHERE status=?", (status,))
        else:
            rows = self._conn.execute("SELECT * FROM cases")
        out = []
        for r in rows.fetchall():
            c = Case(id=r["id"], event_id=r["event_id"], student_id=r["student_id"],
                     title=r["title"] or "", problem_type=r["problem_type"] or "",
                     deidentified_profile=r["deidentified_profile"] or "",
                     background=r["background"] or "", analysis=r["analysis"] or "",
                     process=r["process"] or "", outcome=r["outcome"] or "",
                     reusable_principle=r["reusable_principle"] or "",
                     applicable=r["applicable"] or "", not_applicable=r["not_applicable"] or "",
                     status=r["status"], creator=r["creator"] or "",
                     created_at=r["created_at"] or "")
            out.append(c)
        return out

    # ---------- 教师 / 角色 ----------
    def list_teachers(self, role: Optional[str] = None) -> List[Teacher]:
        if role:
            rows = self._conn.execute(
                "SELECT * FROM teachers WHERE role=?", (role,))
        else:
            rows = self._conn.execute("SELECT * FROM teachers")
        out = []
        for r in rows.fetchall():
            out.append(Teacher(
                name=r["name"], role=r["role"], class_name=r["class_name"] or "",
                students=json.loads(r["students_json"] or "[]")))
        return out

    def upsert_teacher(self, t: Teacher) -> None:
        self._conn.execute(
            """INSERT INTO teachers (name,role,class_name,students_json)
               VALUES (?,?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                 role=excluded.role, class_name=excluded.class_name,
                 students_json=excluded.students_json""",
            (t.name, t.role, t.class_name, json.dumps(t.students, ensure_ascii=False)))
        self._conn.commit()

    def student_ids_for_teacher(self, teacher_name: str) -> List[str]:
        t = self._conn.execute(
            "SELECT * FROM teachers WHERE name=?", (teacher_name,)).fetchone()
        if not t:
            return []
        if t["role"] == "班主任" and t["class_name"]:
            rows = self._conn.execute(
                "SELECT id FROM students WHERE class_name=?", (t["class_name"],))
            return [r["id"] for r in rows.fetchall()]
        if t["role"] == "德育导师":
            return json.loads(t["students_json"] or "[]")
        return []

    # ---------- 成长报告 ----------
    def add_report(self, r: GrowthReport) -> str:
        self._conn.execute(
            """INSERT INTO reports (id,student_id,student_name,period,content,created_at)
               VALUES (?,?,?,?,?,?)""",
            (r.id, r.student_id, r.student_name, r.period, r.content, r.created_at))
        self._conn.commit()
        return r.id

    def list_reports(self, student_id: Optional[str] = None) -> List[GrowthReport]:
        if student_id:
            rows = self._conn.execute(
                "SELECT * FROM reports WHERE student_id=?", (student_id,))
        else:
            rows = self._conn.execute("SELECT * FROM reports")
        return [GrowthReport(id=r["id"], student_id=r["student_id"],
                             student_name=r["student_name"], period=r["period"],
                             content=r["content"], created_at=r["created_at"] or "")
                for r in rows.fetchall()]

    # ---------- 内部 ----------
    @staticmethod
    def _row_to_student(r: sqlite3.Row) -> Student:
        return Student(id=r["id"], name=r["name"], class_name=r["class_name"],
                       gender=r["gender"] or "", boarding=r["boarding"] or "",
                       dorm=r["dorm"] or "", tutor=r["tutor"] or "",
                       key_vars=r["key_vars"] or "",
                       risk_level=r["risk_level"] or "🟢 正常",
                       latest_change_note=r["latest_change_note"] or "",
                       entry_year=r["entry_year"] or 2026)

    @staticmethod
    def _row_to_event(r: sqlite3.Row) -> Event:
        return Event(id=r["id"], student_id=r["student_id"],
                     student_name=r["student_name"], date=r["date"],
                     event_type=r["event_type"], description=r["description"] or "",
                     severity=r["severity"] or "中", handling=r["handling"] or "",
                     result=r["result"] or "", status=r["status"] or "待跟进",
                     recorder_role=r["recorder_role"] or "",
                     recorder=r["recorder"] or "", level=r["level"] or "",
                     ai_analysis=r["ai_analysis"] or "",
                     ai_suggestions=r["ai_suggestions"] or "",
                     ai_followup=r["ai_followup"] or "",
                     prev_event_id=r["prev_event_id"] or "",
                     prev_suggestion=r["prev_suggestion"] or "",
                     prev_result=r["prev_result"] or "",
                     analysis_fail_count=r["analysis_fail_count"] or 0)
