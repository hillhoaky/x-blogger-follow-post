#!/usr/bin/env python3
"""Export answer-free semantic cases or grade prior model decisions. Offline only."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_cases():
    return json.loads((ROOT / 'references/filter-cases.json').read_text())['cases']


def grade(cases, predictions):
    if not isinstance(predictions, list):
        raise ValueError('predictions must be an array')
    expected = {c['id']: c for c in cases}
    seen, failures = set(), []
    for p in predictions:
        if not isinstance(p, dict):
            failures.append({'id': None, 'errors': ['decision must be an object']})
            continue
        key = p.get('id')
        if not isinstance(key, str) or key not in expected or key in seen:
            failures.append({'id': key, 'errors': ['unknown or duplicate id']})
            continue
        seen.add(key)
        c, errors = expected[key], []
        if not isinstance(p.get('reason'), str) or not p['reason'].strip():
            errors.append('concrete reason required')
        for field, value in c['expected'].items():
            if field == 'has_incremental_facts':
                facts = p.get('incremental_facts')
                if not isinstance(facts, list) or any(not isinstance(f, str) or not f.strip() for f in facts) or bool(facts) != value:
                    errors.append('incremental_facts inconsistent with event relation')
            elif p.get(field) != value:
                errors.append(f'{field}: expected {value}, got {p.get(field)}')
        if errors:
            failures.append({'id': key, 'errors': errors})
    failures += [{'id': key, 'errors': ['missing decision']} for key in expected.keys() - seen]
    return {'case_count': len(cases), 'passed': not failures, 'failures': failures}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['export', 'grade'])
    p.add_argument('--output', type=Path)
    p.add_argument('--predictions', type=Path)
    args = p.parse_args()
    cases = load_cases()
    if args.command == 'export':
        result = {'cases': [{k: v for k, v in c.items() if k != 'expected'} for c in cases]}
    else:
        if not args.predictions:
            p.error('grade requires --predictions')
        result = grade(cases, json.loads(args.predictions.read_text()))
    value = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(value)
        print(json.dumps({'output': str(args.output.resolve()), 'passed': result.get('passed')}, ensure_ascii=False))
    else:
        print(value, end='')
    return 1 if result.get('passed') is False else 0


if __name__ == '__main__':
    raise SystemExit(main())
