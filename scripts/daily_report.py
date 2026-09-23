#!/usr/bin/env python3
"""Summarize one Hanoi calendar day from local records; performs no network calls."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone, date
import json
from pathlib import Path
import sys

HANOI = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parents[1]


def on_day(value, day):
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.astimezone(HANOI).date() == day
    except ValueError:
        return False


def summarize(state, runs, day):
    outcomes = {key: [] for key in ["previewed", "published", "skipped"]}
    discovered, pending = [], []
    for item in state.get("items", {}).values():
        if item.get("initial_status", item.get("status")) != "baseline" and on_day(item.get("first_seen_at"), day):
            discovered.append(item["status_id"])
        for target in outcomes:
            found = next((event for event in item.get("history", []) if event.get("status") == target and on_day(event.get("at"), day)), None)
            if found:
                outcomes[target].append({"id": item["status_id"], "url": item.get("source_url"), "newsfeed_id": item.get("newsfeed_id"), **found})
        if item.get("status") in {"discovered", "prepared", "blocked", "review", "submitting", "publish_uncertain"}:
            pending.append({"id": item["status_id"], "status": item["status"], "reason": item.get("last_result", {}).get("reason", "等待处理")})
    daily_runs = [run for run in runs if on_day(run.get("at"), day)]
    return {"date": day.isoformat(), "timezone": "Asia/Ho_Chi_Minh", "generated_at": datetime.now(HANOI).isoformat(),
            "coverage_started_at": state.get("initialized_at"), "checks": len(daily_runs),
            "check_success": sum(r.get("status") == "ok" for r in daily_runs),
            "check_failure": sum(r.get("status") == "error" for r in daily_runs),
            "discovered": len(discovered), "outcomes": outcomes,
            "skip_reasons": dict(Counter(v.get("rule_id", "unclassified") for v in outcomes["skipped"])),
            "pending_at_report_time": pending,
            "feedback": [v for v in state.get("feedback_history", []) if on_day(v.get("at"), day)]}


def markdown(result):
    outcome = result["outcomes"]
    lines = [f'# X 博主运营日报 · {result["date"]}', '',
             '统计时区：河内（UTC+7），范围为该自然日 00:00 至次日 00:00。',
             f'生成时间：{result["generated_at"]}', f'账本开始时间：{result["coverage_started_at"] or "未记录"}', '',
             '本报告为延迟补写。' if result.get('delayed') else '按自然日统计。', '',
             f'- RSS 检查：{result["checks"]} 次（成功 {result["check_success"]}，失败 {result["check_failure"]}）' if result['checks'] else '- RSS 检查：未记录，不据此断言没有活动。',
             f'- 新发现：{result["discovered"]} 条',
             f'- 对话预览：{len(outcome["previewed"])} 条',
             f'- 后台实际发布：{len(outcome["published"])} 条',
             f'- 跳过：{len(outcome["skipped"])} 条，其中事件重复 {result["skip_reasons"].get("EVENT_DUPLICATE",0)} 条',
             f'- 报告生成时待处理：{len(result["pending_at_report_time"])} 条', '']
    for label, status in [('对话预览','previewed'), ('实际发布','published'), ('跳过明细','skipped')]:
        lines += [f'## {label}', '']
        for item in outcome[status]:
            suffix = f'；Newsfeed ID {item["newsfeed_id"]}' if status == 'published' else ''
            lines.append(f'- [{item["id"]}]({item["url"]})：{item.get("reason", "")}{suffix}')
        if not outcome[status]:
            lines.append('本日无对应记录。')
        lines.append('')
    lines += ['## 待处理（生成时快照）', '']
    lines += [f'- {v["id"]} · {v["status"]}：{v["reason"]}' for v in result['pending_at_report_time']] or ['无待处理记录。']
    lines += ['', '## 用户反馈与规则调整', '']
    lines += [f'- {v.get("summary", "已记录反馈")}' for v in result['feedback']] or ['本日账本未记录反馈调整；如对话有新反馈，核对后补充，不凭空生成。']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--date', help='YYYY-MM-DD; default: previous Hanoi calendar day')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--delayed', action='store_true', help='Mark this calendar-day report as a delayed backfill')
    args = parser.parse_args()
    config = json.loads((ROOT/'references/sources.json').read_text())
    path = (args.state or Path(config['sources']['fxtrader']['state_path'])).expanduser()
    state = json.loads(path.read_text()) if path.exists() else {}
    day = date.fromisoformat(args.date) if args.date else datetime.now(HANOI).date() - timedelta(days=1)
    runs = [json.loads(p.read_text()) for p in sorted((path.parent/'runs').glob('*.json'))]
    result = summarize(state, runs, day)
    result['delayed'] = args.delayed
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown(result), encoding='utf-8')
    args.output.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'report': str(args.output.resolve()), 'date': result['date'], 'previews':len(result['outcomes']['previewed']), 'published':len(result['outcomes']['published'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
