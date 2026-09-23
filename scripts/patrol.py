#!/usr/bin/env python3
"""Cheap heartbeat gate: local report dates, one RSS probe, compact actionable output."""
import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
import daily_report
import rss_queue as queue


def due_reports(state, output_root, current=None):
    current = current or datetime.now(daily_report.HANOI)
    current = current.astimezone(daily_report.HANOI)
    folder = output_root / "reports"
    receipt_path = folder / "delivery-index.json"
    receipts = queue.read_json(receipt_path) if receipt_path.exists() else {}
    first = state.get("operations", {}).get("first_report_date", "2026-09-23")
    day, result = date.fromisoformat(first), []
    while day < current.date():
        key = day.isoformat()
        md = folder / f"{key}.md"
        js = md.with_suffix(".json")
        if key not in receipts or not md.is_file() or not js.is_file():
            result.append({"date": key, "output": str(md.resolve()),
                           "needs_generation": not (md.is_file() and js.is_file()),
                           "delayed": current.date() > day + timedelta(days=1) or (current.hour, current.minute) > (0, 10)})
        day += timedelta(days=1)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--feed-file", type=Path, help="Offline fixtures only; production fetches RSS")
    parser.add_argument("--ack-report", help="Record a report delivered in this task; no RSS request")
    args = parser.parse_args()
    config = queue.read_json(queue.ROOT / "references/sources.json")
    state_path = (args.state or Path(config["sources"]["fxtrader"]["state_path"])).expanduser()
    state = queue.read_json(state_path) if state_path.exists() else {}
    if args.ack_report:
        key = date.fromisoformat(args.ack_report).isoformat()
        md = args.output_root / "reports" / f"{key}.md"
        if not md.is_file() or not md.with_suffix(".json").is_file():
            raise ValueError("Report MD and JSON must exist before delivery is acknowledged")
        index = md.parent / "delivery-index.json"
        with queue.locked(index):
            receipts = queue.read_json(index) if index.exists() else {}
            receipts[key] = {"delivered_at": queue.now(), "report": str(md.resolve())}
            queue.save_json(index, receipts)
        print(json.dumps({"report_acknowledged": key}))
        return 0
    reports = due_reports(state, args.output_root)
    if reports:
        print(json.dumps({"action": "reports_first", "reports_due": reports}, ensure_ascii=False))
        return 0
    command = [sys.executable, str(queue.ROOT / "scripts/rss_queue.py"), "probe", "--state", str(state_path), "--compact"]
    if args.feed_file:
        command += ["--feed-file", str(args.feed_file)]
    probe = subprocess.run(command, capture_output=True, text=True)
    result = json.loads(probe.stdout if probe.returncode == 0 else probe.stderr)
    status_path = state_path.parent / "patrol-status.json"
    previous = queue.read_json(status_path) if status_path.exists() else {}
    failure = result.get("message") if probe.returncode else None
    issues = result.get("feed_issues", [])
    prior_problem = previous.get("failure") or previous.get("feed_issues")
    new_problem = bool(failure or issues) and (failure != previous.get("failure") or issues != previous.get("feed_issues", []))
    recovered = bool(prior_problem) and not (failure or issues)
    queue.save_json(status_path, {"at": queue.now(), "failure": failure, "feed_issues": issues})
    action = "work" if result.get("due_candidates") or result.get("recovery_only") else "idle"
    if new_problem or recovered:
        action = "notice" if action == "idle" else action
    result.update(action=action, notify_new_problem=new_problem, recovered=recovered)
    if probe.returncode:
        result["action"] = "notice" if new_problem else "idle"
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    main()
