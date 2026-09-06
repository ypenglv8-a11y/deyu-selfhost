import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from src.models import Student, Event
from src.storage_sqlite import SqliteStorage
from src.recording import record, query, create_followup, complete_followup, backup
from src.theory import grade_event, build_analysis_messages
from src.analyzer import weekly_tracking, generate_report, analyze_event


class CaptureLLM:
    def __init__(self, result): self.result, self.messages = result, []
    def chat_json(self, messages): self.messages = messages; return self.result


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name)/'test.db')
        self.s = SqliteStorage(self.db); self.addCleanup(self.s._conn.close)
        self.s.upsert_student(Student('S1','虚构学生甲','示例班','','',risk_level='教师原判断'))
        self.day = date.today().isoformat()

    def save(self, key='message-1', text='虚构事实：任务尚未开始'):
        return record(self.s,'S1',text,self.day,'作业',key)

    def test_receipt_and_retry(self):
        a=self.save(); b=self.save()
        self.assertEqual(a['event_id'],b['event_id']); self.assertTrue(a['verified'])
        self.assertEqual(len(self.s.list_events()),1)
        self.assertEqual(query(self.s,'S1','任务')['matched'],1)

    def test_changed_request_blocked(self):
        self.save()
        with self.assertRaises(ValueError): self.save(text='另一事实')

    def test_distinct_messages_not_merged(self):
        self.save();self.save('message-2')
        self.assertEqual(len(self.s.list_events()),2)

    def test_unknown_student_not_saved(self):
        with self.assertRaises(ValueError): record(self.s,'missing','虚构事实',self.day,'其他','x')
        self.assertEqual(self.s.list_events(),[])

    def test_fact_mutation_detected_on_retry(self):
        eid=self.save()['event_id']; e=self.s.get_event(eid);e.description='改动';self.s.update_event(e)
        with self.assertRaises(ValueError):self.save()

    def test_unknown_and_old_repetition_never_auto_crisis(self):
        e=Event('E','S1','甲',self.day,'作业','虚构','未知')
        self.assertEqual(grade_event(e,[]),'L2')
        e.severity='轻'
        old=[Event(str(i),'S1','甲','2020-01-01','作业','虚构','轻') for i in range(10)]
        self.assertEqual(grade_event(e,old),'L1')
        for h in old:h.date=self.day
        self.assertEqual(grade_event(e,old),'L2')

    def test_no_automatic_risk_rewrite(self):
        self.save();llm=CaptureLLM({'note':'证据待核','risk_level':'🔴 重点干预'})
        weekly_tracking(self.s,llm)
        self.assertEqual(self.s.get_student('S1').risk_level,'教师原判断')
        self.assertTrue(self.s.get_student('S1').latest_change_note.startswith('【AI待复核】'))

    def test_report_period_no_other_months(self):
        self.save(text='本月虚构事实')
        self.s.add_event(Event('OLD','S1','甲','2020-01-01','作业','不应混入','中'))
        llm=CaptureLLM({'report':'依据已有记录的草稿'})
        report=generate_report(self.s,llm,'S1',self.day[:7])
        self.assertNotIn('不应混入',json.dumps(llm.messages,ensure_ascii=False))
        self.assertIn('AI草稿',report.content)
        with self.assertRaises(ValueError):generate_report(self.s,llm,'S1','2020-02')

    def test_followup_requires_real_feedback_and_preserves_first_completion(self):
        eid=self.save()['event_id']; f=create_followup(self.s,eid,self.day,'核实起步条件')
        with self.assertRaises(ValueError):complete_followup(self.s,f['id'],'','教师复盘')
        complete_followup(self.s,f['id'],'学生说明仍有困难','调整支持条件')
        with self.assertRaises(ValueError):complete_followup(self.s,f['id'],'改称已改善','另一复盘')
        self.assertEqual(self.s.get_event(eid).status,'待跟进')

    def test_analysis_includes_real_feedback(self):
        eid=self.save()['event_id'];f=create_followup(self.s,eid,self.day,'核实')
        complete_followup(self.s,f['id'],'虚构反馈：起步依然困难','虚构复盘：继续核实')
        llm=CaptureLLM({'analysis':'待核实','suggestions':['提供支持'],'followup_plan':'明确日期后回访'})
        analyze_event(self.s,llm,eid)
        self.assertIn('起步依然困难',json.dumps(llm.messages,ensure_ascii=False))

    def test_database_backup_reopens(self):
        self.save();p=Path(self.tmp.name)/'backup.db';backup(self.s,p)
        with sqlite3.connect(p) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
        with self.assertRaises(FileExistsError):backup(self.s,p)

    def test_two_deployments_do_not_share_storage(self):
        self.save(); other=SqliteStorage(str(Path(self.tmp.name)/'other.db'))
        try:self.assertEqual(other.list_students(),[]);self.assertEqual(other.list_events(),[])
        finally:other._conn.close()

    def test_cli_offline_analysis_does_not_pollute_real_database(self):
        eid=self.save()['event_id']
        output=subprocess.run([sys.executable,'-m','src.cli','--db',self.db,'analyze','--event',eid],text=True,capture_output=True)
        self.assertEqual(output.returncode,0,output.stderr)
        self.assertIn('不写入正式库',json.loads(output.stdout)['mode'])
        self.assertFalse(self.s.get_event(eid).ai_analysis)

    def test_cli_complete_roundtrip(self):
        def run(*args):
            res=subprocess.run([sys.executable,'-m','src.cli','--db',self.db,*args],text=True,capture_output=True)
            self.assertEqual(res.returncode,0,res.stderr);return json.loads(res.stdout)
        receipt=run('record','--student','S1','--text','虚构CLI事实','--request-id','cli-1')
        self.assertTrue(receipt['verified'])
        self.assertEqual(run('find','--student','S1','--query','CLI事实')['matched'],1)
        fu=run('followup','--event',receipt['event_id'],'--due',self.day,'--plan','虚构计划')
        self.assertEqual(len(run('due')),1)
        run('complete','--id',fu['id'],'--feedback','虚构学生反馈','--review','虚构教师复盘')
        self.assertEqual(run('due'),[])


if __name__=='__main__':unittest.main()
