#!/usr/bin/env python3
"""RSS-only discovery and durable per-status ledger. Never publishes or opens X."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MAX_FEED = 8 * 1024 * 1024
TERMINAL = {"baseline", "skipped", "previewed", "published"}
RECOVERY = {"submitting", "publish_uncertain"}


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(value, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("ledger is busy; use one runner") from exc
        yield


def tag(element):
    return element.tag.rsplit("}", 1)[-1]


def text_of(element):
    return "".join(element.itertext()).strip()


def parse_feed(data, handle):
    if len(data) > MAX_FEED:
        raise ValueError("feed exceeds size limit")
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("DTD/entity declarations are unsupported")
    root = ET.fromstring(data)
    if tag(root) not in {"rss", "feed", "RDF"}:
        raise ValueError("response is not RSS/Atom")
    items, issues = {}, []
    for index, entry in enumerate(e for e in root.iter() if tag(e) in {"item", "entry"}):
        links, fields = [], {}
        for child in entry:
            name = tag(child)
            if name == "link" and child.get("rel", "alternate") == "alternate":
                links.append(child.get("href") or text_of(child))
            elif name in {"guid", "id"}:
                links.append(text_of(child))
            if name in {"title", "description", "summary", "content", "encoded", "pubDate", "published", "updated"}:
                fields[name] = text_of(child)
        candidates = {}
        for link in links:
            parts = urlsplit(link)
            if parts.scheme not in {"http", "https"} or parts.netloc.lower() not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
                continue
            match = re.fullmatch(r"/([A-Za-z0-9_]+)/status/([0-9]+)(?:/(?:photo|video)/[0-9]+)?/?", parts.path)
            if match and match[1].lower() == handle.lower():
                candidates[match[2]] = f"https://x.com/{handle}/status/{match[2]}"
        if len(candidates) != 1:
            issues.append({"item_index": index, "reason": "missing, foreign, or ambiguous author/status link"})
            continue
        status_id, url = next(iter(candidates.items()))
        digest = hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        item = {"status_id": status_id, "source_url": url, "rss_title": fields.get("title", ""),
                "rss_time": fields.get("pubDate") or fields.get("published") or fields.get("updated"),
                "rss_fingerprint": digest}
        if status_id in items and items[status_id]["rss_fingerprint"] != digest:
            issues.append({"status_id": status_id, "reason": "same status has conflicting RSS entries"})
        items.setdefault(status_id, item)
    if not items:
        raise ValueError("empty feed or no usable posts for configured author; detection not confirmed")
    return sorted(items.values(), key=lambda v: int(v["status_id"])), issues


def fetch_feed(url, state):
    headers = {"User-Agent": "IFXData-RSS-Follow/1.0", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"}
    if state:
        for name, key in [("If-None-Match", "etag"), ("If-Modified-Since", "last_modified")]:
            if state.get(key):
                headers[name] = state[key]
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
            data = response.read(MAX_FEED + 1)
            return data, {"etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified")}
    except urllib.error.HTTPError as exc:
        if exc.code == 304 and state:
            return None, {}
        raise


def ingest(state, source, items, issues, latest=0):
    if latest < 0:
        raise ValueError("bootstrap count must be nonnegative")
    if state is not None and latest:
        raise ValueError("bootstrap-latest is first-run only; never reset a ledger to backfill")
    stamp = now()
    if state is None:
        state = {"schema_version": 1, "handle": source["handle"], "feed_url": source["feed_url"],
                 "initialized_at": stamp, "baseline_floor_id": str(max(int(v["status_id"]) for v in items)), "items": {}}
        initial_candidates = {v["status_id"] for v in items[-latest:]} if latest else set()
    else:
        initial_candidates = set()
    discovered = []
    for item in items:
        key = item["status_id"]
        existing = state["items"].get(key)
        if existing:
            if existing["rss_fingerprint"] != item["rss_fingerprint"]:
                # Polling discovers new IDs; terminal posts are not revision jobs.
                existing["source_changed"] = existing["status"] not in TERMINAL
                existing["previous_rss_fingerprint"] = existing["rss_fingerprint"]
                existing["rss_fingerprint"] = item["rss_fingerprint"]
                existing["changed_at"] = stamp
                existing["rss_title"] = item["rss_title"]
                existing["rss_time"] = item["rss_time"]
            continue
        status = "discovered" if int(key) > int(state["baseline_floor_id"]) or key in initial_candidates else "baseline"
        state["items"][key] = {**item, "status": status, "initial_status": status, "first_seen_at": stamp, "history": []}
        if status == "discovered":
            discovered.append(key)
    state.update(last_poll_at=stamp, feed_issues=issues)
    return state, discovered


def retry_due(item, current=None):
    current = current or datetime.now(timezone.utc)
    result = item.get("last_result", {})
    value = result.get("retry_after") or item.get("retry_after")
    if not value and item["status"] == "blocked" and result.get("at"):
        try:
            value = (datetime.fromisoformat(result["at"].replace("Z", "+00:00")) + timedelta(minutes=30)).isoformat()
        except ValueError:
            return True
    if not value:
        return True
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is None or parsed <= current
    except ValueError:
        return True


def report(state, discovered=None, compact=False):
    ordered = sorted(state["items"].values(), key=lambda v: int(v["status_id"]))
    counts = {}
    for item in ordered:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    if compact:
        pending = [v for v in ordered if v["status"] not in TERMINAL | RECOVERY]
        due = [v for v in pending if retry_due(v)]
        keys = ["status_id", "source_url", "status", "source_changed", "task_path"]
        return {"rss": "ok", "new_ids": discovered or [],
                "due_candidates": [{k: v[k] for k in keys if k in v} for v in due],
                "deferred_count": len(pending) - len(due),
                "recovery_only": [{k: v[k] for k in keys if k in v} for v in ordered if v["status"] in RECOVERY],
                "feed_issues": state.get("feed_issues", [])}
    return {"handle": state["handle"], "new_ids": discovered or [], "counts": counts,
            "pending": [v for v in ordered if v["status"] not in TERMINAL | RECOVERY],
            "recovery_only": [v for v in ordered if v["status"] in RECOVERY],
            "changed_ids": [v["status_id"] for v in ordered if v.get("source_changed") and v["status"] not in TERMINAL],
            "events": [{k: v.get(k) for k in ["status_id", "status", "event_key", "key_facts", "event_at", "source_url"]}
                       for v in ordered if v.get("event_key") and v["status"] in {"prepared", "previewed", "published"} | RECOVERY],
            "feed_issues": state.get("feed_issues", [])}


def check_task(record, item, published=False):
    task_path = Path(record.get("task_path", "")).expanduser()
    if not task_path.is_file():
        raise ValueError("existing per-post task_path required")
    task = read_json(task_path)
    if task.get("admin_scope") != "vn" or task.get("target_language") != "vi" or str(task.get("source_status_id")) != item["status_id"]:
        raise ValueError("task must match status ID, vi language, and vn admin scope")
    if published:
        verification = task.get("verification", {})
        if not str(task.get("newsfeed_id", "")).isdigit() or int(task["newsfeed_id"]) < 1:
            raise ValueError("verified Vietnam Newsfeed ID required")
        if verification.get("scope") != "vn" or not verification.get("evidence"):
            raise ValueError("Vietnam readback evidence required")
        if any(verification.get(key) is not True for key in ["title", "body", "label", "important", "media_order"]):
            raise ValueError("all actual readback checks must pass")
    return task


def event_fields(state, status_id, record):
    key, facts, relation = record.get("event_key"), record.get("key_facts"), record.get("event_relation")
    if not isinstance(key, str) or not key.strip() or not isinstance(facts, list) or not facts or any(not isinstance(f, str) or not f.strip() for f in facts):
        raise ValueError("event_key and nonempty key_facts required")
    if relation not in {"new", "update"}:
        raise ValueError("prepared content must be a new event or substantive update")
    related = [v for k, v in state["items"].items() if k != status_id and v.get("event_key") == key and v["status"] in {"prepared", "previewed", "published"} | RECOVERY]
    normalized = lambda values: {" ".join(v.casefold().split()) for v in values}
    old = normalized([f for v in related for f in v.get("key_facts", [])])
    additions = normalized(facts) - old
    if related and (not additions or relation != "update"):
        raise ValueError("same event requires new facts and event_relation:update; otherwise skip duplicate")
    if relation == "update":
        new_facts = record.get("incremental_facts")
        if not isinstance(new_facts, list) or not new_facts or any(not isinstance(f, str) or not f.strip() for f in new_facts):
            raise ValueError("update requires incremental_facts")
        if not normalized(new_facts) <= additions:
            raise ValueError("incremental_facts must be genuinely additional facts in key_facts")
    return {"event_key": key, "key_facts": facts, "event_relation": relation, "incremental_facts": record.get("incremental_facts", []), "related_status_ids": record.get("related_status_ids", []), "event_at": now()}


def mark(state, status_id, record, operations=None):
    if operations is None:
        operations = read_json(ROOT / "references/sources.json").get("operations", {})
    item = state["items"][status_id]
    previous, target = item["status"], record.get("status")
    allowed = {"discovered": {"skipped", "review", "blocked", "prepared"},
               "review": {"review", "blocked", "skipped", "prepared"},
               "blocked": {"review", "blocked", "skipped", "prepared"},
               "prepared": {"review", "blocked", "submitting", "previewed"},
               "previewed": {"submitting"},
               "submitting": {"publish_uncertain", "published"},
               "publish_uncertain": {"published"}}
    adoption = target == "published" and record.get("adopt_existing") is True and previous in {"discovered", "review", "blocked", "prepared"}
    if target not in allowed.get(previous, set()) and not adoption:
        raise ValueError(f"forbidden transition {previous} -> {target}; never reset uncertain/terminal posts")
    if not str(record.get("reason", "")).strip():
        raise ValueError("concrete reason required")
    if target in {"skipped", "review", "prepared"} or adoption:
        rules = read_json(ROOT / "references/filters.json")
        valid_rules = {rule["id"] for rule in rules["rules"]}
        if record.get("rule_id") not in valid_rules or record.get("rule_version") != rules["version"]:
            raise ValueError("current filter rule ID/version required")
    if target == "prepared":
        if record.get("x_verified") is not True or not record.get("relevance"):
            raise ValueError("original-X verification and concrete audience relevance required")
        check_task(record, item)
        fields = event_fields(state, status_id, record)
    if target == "previewed":
        task = check_task(record, item)
        if task.get("publish_authorized") is not False or task.get("preview_verified") is not True:
            raise ValueError("preview requires publish_authorized:false and completed preview QA")
        if item.get("source_changed") and record.get("source_change_reviewed") is not True:
            raise ValueError("changed source requires review before preview")
    if target == "submitting":
        enabled = operations.get("mode") == "publish" and operations.get("publish_authorized") is True
        override = record.get("explicit_publish_override") is True and bool(record.get("authorization_evidence"))
        if not enabled and not override:
            raise ValueError("chat_preview mode forbids backend submission without a new explicit user override")
        task = check_task(record, item)
        if task.get("publish_authorized") is not True:
            raise ValueError("task lacks publish authorization")
        if item.get("source_changed") and record.get("source_change_reviewed") is not True:
            raise ValueError("RSS content changed; review before submission")
    if target == "published":
        task = check_task(record, item, published=True)
        item["newsfeed_id"] = str(task["newsfeed_id"])
    if record.get("source_change_reviewed") is True:
        item["source_changed"] = False
    if target == "prepared":
        item.update(fields)
    event = {**record, "at": now(), "previous_status": previous}
    item["status"] = target
    item["history"].append(event)
    item["last_result"] = event


def log_run(path, payload):
    stamp = now()
    filename = stamp.replace(":", "-") + f"-{os.getpid()}.json"
    save_json(path.parent / "runs" / filename, {"at": stamp, **payload})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["probe", "queue", "mark"])
    parser.add_argument("--source", default="fxtrader")
    parser.add_argument("--config", type=Path, default=ROOT / "references/sources.json")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--feed-file", type=Path, help="RSS XML from a permitted fetch; also useful for offline tests")
    parser.add_argument("--bootstrap-latest", type=int, default=0)
    parser.add_argument("--id")
    parser.add_argument("--record", type=Path)
    parser.add_argument("--compact", action="store_true", help="Only new/due work; omit history and event library")
    args = parser.parse_args()
    path = None
    try:
        source = read_json(args.config)["sources"][args.source]
        path = (args.state or Path(source["state_path"])).expanduser()
        with locked(path):
            state = read_json(path) if path.exists() else None
            if state and (state.get("handle") != source["handle"] or state.get("feed_url") != source["feed_url"]):
                raise ValueError("state/source mismatch")
            discovered = []
            if args.command == "probe":
                if args.bootstrap_latest and state:
                    raise ValueError("bootstrap-latest requires an uninitialized state")
                data, headers = (args.feed_file.read_bytes(), {}) if args.feed_file else fetch_feed(source["feed_url"], state)
                if data is not None:
                    items, issues = parse_feed(data, source["handle"])
                    state, discovered = ingest(state, source, items, issues, args.bootstrap_latest)
                    # An imported snapshot must not preserve validators from an unrelated fetch.
                    state.update(etag=headers.get("etag"), last_modified=headers.get("last_modified"))
                else:
                    state["last_poll_at"] = now()
                save_json(path, state)
                log_run(path, {"status": "ok", "new_ids": discovered, "feed_issues": state.get("feed_issues", [])})
            elif not state:
                raise ValueError("no initialized state; probe first")
            elif args.command == "mark":
                if not args.id or not args.record:
                    raise ValueError("mark requires --id and --record")
                mark(state, args.id, read_json(args.record), read_json(args.config).get("operations", {}))
                save_json(path, state)
            print(json.dumps(report(state, discovered, compact=args.compact), ensure_ascii=False))
        return 0
    except (ValueError, KeyError, OSError, ET.ParseError, urllib.error.URLError) as exc:
        if path is not None and args.command == "probe":
            try:
                log_run(path, {"status": "error", "message": str(exc)})
            except OSError:
                pass
        print(json.dumps({"status": "error", "message": str(exc), "ledger_unchanged": True}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
