#!/usr/bin/env python3
"""Offline behavioral checks; no network, browser, live ledger, or publishing."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
import rss_queue as queue
import daily_report
import patrol

SOURCE = {"handle": "fxtrader", "feed_url": "https://rss.app/feeds/ar9gRF2tWDZD8ThY.xml"}
FILTER_VERSION = queue.read_json(queue.ROOT / 'references/filters.json')['version']


def rss(ids, body="news", handle="fxtrader"):
    return ("<rss><channel>" + "".join(
        f"<item><title>{body}</title><link>https://x.com/{handle}/status/{n}?s=20</link><guid>changing-guid-{i}</guid></item>"
        for i, n in enumerate(ids)) + "</channel></rss>").encode()


def ingest(state, ids, latest=0, body="news"):
    items, issues = queue.parse_feed(rss(ids, body), SOURCE["handle"])
    return queue.ingest(state, SOURCE, items, issues, latest)


class WorkflowChecks(unittest.TestCase):
    def test_feed_fetch_retries_one_transient_network_failure(self):
        class Response:
            headers = {"ETag": "test-etag", "Last-Modified": None}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _limit):
                return b"<rss/>"

        transient = queue.urllib.error.URLError("temporary DNS failure")
        with mock.patch.object(queue.urllib.request, "urlopen", side_effect=[transient, Response()]) as opened, \
             mock.patch.object(queue.time, "sleep") as wait:
            data, headers = queue.fetch_feed(SOURCE["feed_url"], None)
        self.assertEqual(data, b"<rss/>")
        self.assertEqual(headers["etag"], "test-etag")
        self.assertEqual(opened.call_count, 2)
        wait.assert_called_once_with(1)

    def test_preview_mode_blocks_accidental_submission(self):
        state, _ = ingest(None, [100], latest=1)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'task.json'
            task = {'source_status_id':'100','target_language':'vi','admin_scope':'vn','publish_authorized':False,'preview_verified':True}
            queue.save_json(path, task)
            record = {'status':'prepared','rule_id':'MARKET_RELEVANT','rule_version':FILTER_VERSION,'reason':'market news','x_verified':True,'relevance':'FX','event_key':'fed|rate|2026-09-23','key_facts':['rate unchanged'],'event_relation':'new','task_path':str(path)}
            queue.mark(state, '100', record)
            queue.mark(state, '100', {'status':'previewed','reason':'preview QA passed','task_path':str(path)})
            self.assertFalse(queue.report(state)['pending'])
            task['publish_authorized'] = True
            queue.save_json(path, task)
            with self.assertRaisesRegex(ValueError, 'chat_preview'):
                queue.mark(state,'100',{'status':'submitting','reason':'old authorization','task_path':str(path)})

    def test_event_duplicate_and_material_update(self):
        state, _ = ingest(None, [100, 110], latest=2)
        state['items']['100'].update(status='previewed',event_key='fed|rate|2026-09-23',key_facts=['rate unchanged'])
        duplicate = {'event_key':'fed|rate|2026-09-23','key_facts':['RATE unchanged'],'event_relation':'update','incremental_facts':['RATE unchanged']}
        with self.assertRaises(ValueError):
            queue.event_fields(state,'110',duplicate)
        update = {**duplicate,'key_facts':['rate unchanged','official statement released'],'incremental_facts':['official statement released']}
        self.assertEqual(queue.event_fields(state,'110',update)['incremental_facts'], ['official statement released'])

    def test_daily_report_hanoi_midnight_and_preview_not_publish(self):
        day = daily_report.date(2026,9,23)
        self.assertTrue(daily_report.on_day('2026-09-22T17:00:00+00:00',day))
        self.assertTrue(daily_report.on_day('2026-09-23T16:59:59+00:00',day))
        self.assertFalse(daily_report.on_day('2026-09-23T17:00:00+00:00',day))
        state={'items':{'100':{'status_id':'100','status':'previewed','initial_status':'discovered','first_seen_at':'2026-09-23T10:00:00+00:00','history':[{'status':'previewed','at':'2026-09-23T10:30:00+00:00'}]}}}
        result=daily_report.summarize(state,[],day)
        self.assertEqual(len(result['outcomes']['previewed']),1)
        self.assertEqual(len(result['outcomes']['published']),0)
        self.assertEqual(result['discovered'],1)

    def test_baseline_no_historical_publication(self):
        state, new = ingest(None, [110, 100])
        self.assertEqual(new, [])
        self.assertEqual(queue.report(state)["pending"], [])
        self.assertTrue(all(v["status"] == "baseline" for v in state["items"].values()))

    def test_repeat_reorder_and_delayed_discovery(self):
        state, _ = ingest(None, [100])
        state, first = ingest(state, [120, 100, 120])
        self.assertEqual(first, ["120"])
        state, second = ingest(state, [110, 120, 90])
        self.assertEqual(second, ["110"])
        self.assertEqual([v["status_id"] for v in queue.report(state)["pending"]], ["110", "120"])
        self.assertEqual(state["items"]["90"]["status"], "baseline")

    def test_explicit_first_run_latest(self):
        state, new = ingest(None, [100, 120, 110], latest=1)
        self.assertEqual(new, ["120"])
        with self.assertRaises(ValueError):
            ingest(state, [130], latest=1)

    def test_atom_twitter_and_foreign_author(self):
        data = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>tag:ignored</id><link href="https://twitter.com/FXTrader/status/123/photo/1"/><title>news</title></entry><entry><link href="https://x.com/other/status/456"/></entry></feed>'
        items, issues = queue.parse_feed(data, "fxtrader")
        self.assertEqual(items[0]["source_url"], "https://x.com/fxtrader/status/123")
        self.assertEqual(len(issues), 1)

    def test_body_quote_is_not_discovery_link(self):
        data = b'<rss><channel><item><link>https://x.com/other/status/1</link><description>https://x.com/fxtrader/status/2</description></item></channel></rss>'
        with self.assertRaises(ValueError):
            queue.parse_feed(data, "fxtrader")

    def test_empty_html_and_entity_rejected(self):
        for data in [b'<rss><channel/></rss>', b'<html>login</html>', b'<!DOCTYPE rss><rss/>']:
            with self.subTest(data=data), self.assertRaises(ValueError):
                queue.parse_feed(data, "fxtrader")

    def test_failed_parse_preserves_ledger_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path, feed = Path(temp) / "state.json", Path(temp) / "feed.xml"
            state, _ = ingest(None, [100])
            queue.save_json(path, state)
            before = path.read_bytes()
            feed.write_text("<rss>")
            result = subprocess.run([sys.executable, str(queue.ROOT / "scripts/rss_queue.py"), "probe", "--state", str(path), "--feed-file", str(feed)], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_bytes(), before)

    def test_content_change_does_not_republish(self):
        state, _ = ingest(None, [100], latest=1)
        state["items"]["100"]["status"] = "published"
        state, new = ingest(state, [100], body="changed")
        self.assertEqual(new, [])
        self.assertEqual(state["items"]["100"]["status"], "published")
        self.assertEqual(queue.report(state)["changed_ids"], [])
        self.assertFalse(queue.report(state, compact=True)["due_candidates"])
        self.assertEqual(state["items"]["100"]["rss_title"], "changed")

    def test_idle_terminal_changes_and_due_retry(self):
        state, _ = ingest(None, [100, 110], latest=1)
        state['items']['110'].update(status='blocked', last_result={'at':'2099-01-01T00:00:00Z'})
        state, new = ingest(state, [100, 110], body='changed metadata')
        self.assertEqual(new, [])
        self.assertEqual(queue.report(state)['changed_ids'], ['110'])
        compact = queue.report(state, compact=True)
        self.assertEqual(compact['deferred_count'], 1)
        self.assertEqual(compact['due_candidates'], [])
        self.assertNotIn('events', compact)
        state['items']['110']['last_result']['retry_after'] = '2020-01-01T00:00:00Z'
        self.assertEqual([v['status_id'] for v in queue.report(state, compact=True)['due_candidates']], ['110'])

    def test_report_gate_and_delivery_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            state = {'operations':{'first_report_date':'2026-09-23'}}
            before = daily_report.datetime(2026,9,23,23,59,tzinfo=daily_report.HANOI)
            self.assertEqual(patrol.due_reports(state,out,before), [])
            midnight = before + daily_report.timedelta(minutes=1)
            self.assertEqual(patrol.due_reports(state,out,midnight)[0]['date'], '2026-09-23')
            folder = out/'reports'; folder.mkdir()
            (folder/'2026-09-23.md').write_text('report')
            queue.save_json(folder/'2026-09-23.json', {})
            self.assertFalse(patrol.due_reports(state,out,midnight)[0]['needs_generation'])
            queue.save_json(folder/'delivery-index.json', {'2026-09-23':{'delivered_at':'test'}})
            self.assertEqual(patrol.due_reports(state,out,midnight), [])
            later = midnight + daily_report.timedelta(days=2)
            self.assertEqual([v['date'] for v in patrol.due_reports(state,out,later)], ['2026-09-24','2026-09-25'])
            self.assertTrue(patrol.due_reports(state,out,later)[0]['delayed'])

    def test_patrol_cli_quiet_work_failure_and_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path, feed = root/'state.json', root/'feed.xml'
            state, _ = ingest(None, [100])
            state['operations'] = {'first_report_date':daily_report.datetime.now(daily_report.HANOI).date().isoformat()}
            queue.save_json(state_path,state)
            command = [sys.executable,str(queue.ROOT/'scripts/patrol.py'),'--state',str(state_path),'--output-root',str(root/'outputs'),'--feed-file',str(feed)]
            def run():
                value = subprocess.run(command,capture_output=True,text=True,check=True)
                return json.loads(value.stdout)
            feed.write_bytes(rss([100],body='metadata changed'))
            self.assertEqual(run()['action'],'idle')
            feed.write_bytes(rss([100,110]))
            result = run()
            self.assertEqual(result['action'],'work')
            self.assertEqual(result['new_ids'],['110'])
            state = queue.read_json(state_path)
            state['items']['110']['status'] = 'previewed'
            queue.save_json(state_path,state)
            self.assertEqual(run()['action'],'idle')
            feed.write_text('<rss>')
            self.assertTrue(run()['notify_new_problem'])
            self.assertEqual(run()['action'],'idle')
            feed.write_bytes(rss([100,110]))
            self.assertTrue(run()['recovered'])
            self.assertEqual(run()['action'],'idle')

    def test_skip_reason_and_terminal_dedup(self):
        state, _ = ingest(None, [100], latest=1)
        with self.assertRaises(ValueError):
            queue.mark(state, "100", {"status": "skipped"})
        queue.mark(state, "100", {"status": "skipped", "reason": "中国股市", "rule_id": "CN_EQUITY", "rule_version": FILTER_VERSION})
        state, _ = ingest(state, [100])
        self.assertEqual(queue.report(state)["pending"], [])
        with self.assertRaises(ValueError):
            queue.mark(state, "100", {"status": "prepared", "reason": "retry"})

    def test_vietnam_guard_and_uncertain_recovery(self):
        state, _ = ingest(None, [100], latest=1)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "task.json"
            task = {"source_status_id": "100", "target_language": "vi", "admin_scope": "total", "publish_authorized": True}
            queue.save_json(path, task)
            prepared = {"status": "prepared", "rule_id": "MARKET_RELEVANT", "rule_version": FILTER_VERSION, "reason": "FX", "x_verified": True, "relevance": "USD market", "task_path": str(path), "event_key":"fed|rate|2026-09-23", "key_facts":["decision confirmed"], "event_relation":"new"}
            with self.assertRaises(ValueError):
                queue.mark(state, "100", prepared)
            task["admin_scope"] = "vn"
            queue.save_json(path, task)
            queue.mark(state, "100", prepared)
            submit = {"status": "submitting", "reason": "QA passed", "task_path": str(path), "explicit_publish_override":True,"authorization_evidence":"offline fixture explicit authorization"}
            queue.mark(state, "100", submit)
            self.assertEqual(len(queue.report(state)["recovery_only"]), 1)
            queue.mark(state, "100", {"status": "publish_uncertain", "reason": "network interrupted"})
            with self.assertRaises(ValueError):
                queue.mark(state, "100", submit)
            published = {"status": "published", "reason": "verified", "task_path": str(path)}
            with self.assertRaises(ValueError):
                queue.mark(state, "100", published)
            task.update(newsfeed_id="456", verification={"scope": "vn", "title": True, "body": True, "label": True, "important": True, "media_order": True, "evidence": "offline test fixture only"})
            queue.save_json(path, task)
            queue.mark(state, "100", published)
            self.assertEqual(state["items"]["100"]["newsfeed_id"], "456")
            self.assertEqual(queue.report(state)["recovery_only"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
