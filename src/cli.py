"""自部署命令行入口；默认离线演示，真实模型调用必须显式选择。"""
import argparse
from dataclasses import asdict
from datetime import date
import json
import os
from pathlib import Path
from .models import Student, EVENT_TYPES
from .storage_sqlite import SqliteStorage
from .recording import record, query, create_followup, complete_followup, followup_table, backup


def main():
    p = argparse.ArgumentParser(description='德育助手自部署版 · 吕钰鹏老师设计')
    p.add_argument('--db', default=os.environ.get('DEYU_DB', 'data/deyu.db'))
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('init-db')
    a = sub.add_parser('student-add')
    a.add_argument('--id', required=True); a.add_argument('--name', required=True)
    a.add_argument('--class-name', default='未填写')
    a = sub.add_parser('record')
    a.add_argument('--student', required=True); a.add_argument('--text', required=True)
    a.add_argument('--request-id', required=True)
    a.add_argument('--date', default=date.today().isoformat())
    a.add_argument('--type', choices=EVENT_TYPES, default='其他')
    a.add_argument('--severity', choices=['未知','轻','中','重'], default='未知')
    a = sub.add_parser('find'); a.add_argument('--student', required=True); a.add_argument('--query', default='')
    a = sub.add_parser('followup'); a.add_argument('--event', required=True)
    a.add_argument('--due', required=True); a.add_argument('--plan', required=True)
    a = sub.add_parser('complete'); a.add_argument('--id', required=True)
    a.add_argument('--feedback', required=True); a.add_argument('--review', required=True)
    sub.add_parser('due')
    a = sub.add_parser('backup'); a.add_argument('--to', required=True)
    for name in ('analyze', 'weekly', 'report'):
        a = sub.add_parser(name)
        a.add_argument('--real', action='store_true', help='授权本次将相关档案发送至配置的模型服务')
        if name == 'analyze': a.add_argument('--event', required=True)
        if name == 'report':
            a.add_argument('--student', required=True); a.add_argument('--period', required=True)
    args = p.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    storage = SqliteStorage(args.db)
    try:
        if args.cmd == 'init-db': result = {'initialized': True}
        elif args.cmd == 'student-add':
            if not args.id.strip() or not args.name.strip(): raise ValueError('学生编号和姓名不能为空')
            if storage.get_student(args.id): raise ValueError('学生编号已存在，拒绝覆盖')
            student = Student(args.id, args.name, args.class_name, '', '', risk_level='待教师核实')
            storage.upsert_student(student); result = asdict(storage.get_student(args.id))
        elif args.cmd == 'record': result = record(storage, args.student, args.text, args.date, args.type, args.request_id, args.severity)
        elif args.cmd == 'find': result = query(storage, args.student, args.query)
        elif args.cmd == 'followup': result = create_followup(storage, args.event, args.due, args.plan)
        elif args.cmd == 'complete': result = complete_followup(storage, args.id, args.feedback, args.review)
        elif args.cmd == 'due':
            followup_table(storage)
            result = [dict(r) for r in storage._conn.execute('SELECT * FROM support_followups WHERE completed_at IS NULL AND due<=? ORDER BY due', (date.today().isoformat(),))]
        elif args.cmd == 'backup': result = backup(storage, args.to)
        else:
            from .llm import build_llm
            from .analyzer import analyze_event, weekly_tracking, generate_report
            if not args.real:
                preview = SqliteStorage(':memory:')
                storage._conn.backup(preview._conn)
                storage._conn.close()
                storage = preview
            llm = build_llm(mock=not args.real)
            if args.cmd == 'analyze': value = asdict(analyze_event(storage, llm, args.event))
            elif args.cmd == 'weekly': value = weekly_tracking(storage, llm)
            else: value = asdict(generate_report(storage, llm, args.student, args.period))
            result = {'mode': '真实模型，输出仍需复核' if args.real else '离线演示固定输出，不是个案判断，不写入正式库', 'result': value}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        # 不回显供应商响应、密钥或学生原文。已保存事实不依赖模型成功。
        p.exit(2, '操作未完成（' + type(exc).__name__ + '）。请检查参数/记录和本地配置，勿声称已完成。\n')
    finally:
        storage._conn.close()


if __name__ == '__main__': main()
