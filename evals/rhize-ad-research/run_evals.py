#!/usr/bin/env python3
"""Offline routing/quality contracts plus collection-core regression tests."""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
def main():
    spec = json.loads((Path(__file__).parent / 'skill-evals.json').read_text())
    failures = []
    for case in spec['cases']:
        found = [s['id'] for s in spec['skills'] if any(re.search(p, case['prompt'], re.I) for p in s['include_patterns'])]
        if found != case['expected']:
            failures.append(case['id'])
    for skill in spec['skills']:
        source = (ROOT / skill['source']).read_text()
        if len(skill['positive_cases']) < 1 or len(skill['negative_cases']) < 2:
            failures.append(skill['id'] + ':coverage')
        for term in skill['quality_terms']:
            if term not in source:
                failures.append(skill['id'] + ':' + term)
    tests = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests/rhize-ad-research', '-p', 'test_*.py'], cwd=ROOT, capture_output=True, text=True, timeout=120)
    print(json.dumps({'status':'fail' if failures or tests.returncode else 'pass','cases':len(spec['cases']),'failures':failures,'tests':(tests.stdout+tests.stderr).strip(),'limitation':'Offline contracts only; no model-routing, provider, or Tom acceptance claim.'}, indent=2))
    return 1 if failures or tests.returncode else 0
if __name__ == '__main__':
    raise SystemExit(main())
