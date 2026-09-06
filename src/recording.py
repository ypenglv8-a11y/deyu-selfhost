"""固定程序负责保存和回读；AI不决定保存成功，也不参与事实写入。"""
from dataclasses import asdict
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import uuid
from .models import Event


def facts(event):
    return {k: getattr(event, k) for k in ('id', 'student_id', 'student_name', 'date',
                                        'event_type', 'description', 'severity', 'recorder')}


def record(storage, student_id, text, day, event_type, request_id, severity='未知'):
    if not request_id.strip() or not text.strip() or len(text) > 20000:
        raise ValueError('需要非空请求标识和事实文本（最多20000字）')
    if date.fromisoformat(day) > date.today():
        raise ValueError('事实发生日期不能在未来')
    student = storage.get_student(student_id)
    if not student:
        raise ValueError('学生不存在，请先建档')
    from .models import EVENT_TYPES
    if event_type not in EVENT_TYPES or severity not in ('未知', '轻', '中', '重'):
        raise ValueError('类型或支持程度无效')
    eid = 'EVT-' + hashlib.sha256(request_id.encode()).hexdigest()[:32]
    incoming = Event(id=eid, student_id=student_id, student_name=student.name, date=day,
                     event_type=event_type, description=text, severity=severity,
                     recorder='教师输入')
    previous = storage.get_event(eid)
    if previous:
        # 学生改名不影响原记录，但不能用同请求ID改写学生或事实。
        expected = facts(incoming)
        expected['student_name'] = previous.student_name
        if facts(previous) != expected:
            raise ValueError('同一请求标识内容不同，拒绝覆盖；独立事件使用新标识')
    else:
        try:
            storage.add_event(incoming)
        except Exception:
            storage._conn.rollback()
            if storage.get_event(eid) is None:
                raise
        previous = storage.get_event(eid)
        if not previous or facts(previous) != facts(incoming):
            raise ValueError('写入后的事实回读不一致')
    persisted = storage.get_event(eid)
    canonical = json.dumps(facts(persisted), ensure_ascii=False, sort_keys=True)
    receipt = dict(event_id=eid, student_id=student_id, verified=True,
                   checked_at=datetime.now().astimezone().isoformat(),
                   sha256=hashlib.sha256(canonical.encode()).hexdigest(), facts=facts(persisted))
    storage._conn.execute('CREATE TABLE IF NOT EXISTS write_receipts (event_id TEXT PRIMARY KEY, receipt TEXT NOT NULL)')
    storage._conn.execute('INSERT OR REPLACE INTO write_receipts VALUES (?,?)',
                          (eid, json.dumps(receipt, ensure_ascii=False)))
    storage._conn.commit()
    return receipt


def query(storage, student_id, term=''):
    if storage.get_student(student_id) is None:
        raise ValueError('学生不存在')
    all_events = storage.list_events(student_id=student_id)
    hits = [asdict(e) for e in all_events if not term or term.casefold() in
            (e.id + '\n' + e.description).casefold()]
    return dict(scanned=len(all_events), matched=len(hits), truncated=False, events=hits,
                note='仅对事件ID和原始描述作字面匹配；未命中不等于从未记录。')


def followup_table(storage):
    storage._conn.execute('''CREATE TABLE IF NOT EXISTS support_followups (
      id TEXT PRIMARY KEY, event_id TEXT NOT NULL, due TEXT NOT NULL, plan TEXT NOT NULL,
      completed_at TEXT, feedback TEXT, teacher_review TEXT)''')
    storage._conn.commit()


def create_followup(storage, event_id, due, plan):
    if not storage.get_event(event_id):
        raise ValueError('关联事件不存在')
    if date.fromisoformat(due) < date.today() or not plan.strip():
        raise ValueError('回访需明确计划和今天或未来日期')
    followup_table(storage)
    fid = 'FU-' + uuid.uuid4().hex[:16]
    storage._conn.execute('INSERT INTO support_followups (id,event_id,due,plan) VALUES (?,?,?,?)',
                          (fid, event_id, due, plan))
    storage._conn.commit()
    return dict(storage._conn.execute('SELECT * FROM support_followups WHERE id=?', (fid,)).fetchone())


def complete_followup(storage, fid, feedback, review):
    if not feedback.strip() or not review.strip():
        raise ValueError('须有实际学生反馈与教师复盘；不能只填已完成')
    followup_table(storage)
    row = storage._conn.execute('SELECT * FROM support_followups WHERE id=?', (fid,)).fetchone()
    if not row:
        raise ValueError('回访不存在')
    if row['completed_at']:
        if row['feedback'] != feedback or row['teacher_review'] != review:
            raise ValueError('已完成回访不能覆盖；修正需另建关联回访')
        return dict(row)
    storage._conn.execute('UPDATE support_followups SET completed_at=?,feedback=?,teacher_review=? WHERE id=?',
                          (datetime.now().astimezone().isoformat(), feedback, review, fid))
    storage._conn.commit()
    return dict(storage._conn.execute('SELECT * FROM support_followups WHERE id=?', (fid,)).fetchone())


def backup(storage, target):
    import sqlite3
    path = Path(target)
    # 不覆盖旧备份，使用SQLite备份API，而非复制运行中的数据库文件。
    with path.open('xb'):
        pass
    with sqlite3.connect(path) as dest:
        storage._conn.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('备份完整性检查失败')
    return {'backup': str(path), 'integrity_check': 'ok'}
