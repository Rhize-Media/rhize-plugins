#!/usr/bin/env python3
"""Deterministic routine-check relaxation for Dev Flow `check` (S4). Stdlib only, Python 3.9.

Eligibility, the mandatory set and the relaxed plan come from git facts and static rules, never from Laya.
Laya (decision `check-relaxation`) may only choose between the full plan and the relaxed plan, and only
on an eligible diff in an earned `advise` mode; anything unknown, missing or failing means the full plan.

  check_plan.py plan   --repo R [--base REF] --stage S --checks FILE [--out FILE]
  check_plan.py verify --plan-file FILE [--stage S]     # exit 3: expired, run the full checks
  check_plan.py outcome --decision-id ID --chosen full|relaxed

Spec: docs/superpowers/specs/2026-10-16-laya-advise-everywhere-plan.md section 7 and 11.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DECISION = 'check-relaxation'
QUESTION = ('This change already qualifies for a deterministic reduced check set. Is the reduced set '
            'sufficient, or should the full set run?')
POLICY = {'candidates': ['full', 'relaxed'], 'rules': 's4-v1'}
CANDIDATES = [
    {'id': 'full', 'criterion': 'Run the complete set of checks the repository normally requires; choose it '
                                'when the change could affect behavior outside its classified paths or any doubt remains.'},
    {'id': 'relaxed', 'criterion': 'Run the reduced set (affected tests, changed-file lint, no browser or mutation '
                                   'run for untouched surfaces); choose it only when the change clearly stays '
                                   'inside low-risk classified paths.'},
]

KINDS = ('test-full', 'test-affected', 'lint', 'lint-changed', 'typecheck', 'build', 'browser-qa', 'mutation',
         'security-review', 'required-ci', 'deploy', 'publish', 'credentials', 'approval',
         'production-merge-review', 'other')
# Only these kinds can ever be relaxed; everything else (including typecheck and build) is mandatory.
RELAXABLE_KINDS = ('test-full', 'lint', 'browser-qa', 'mutation')
NEVER_RELAXABLE = ('security-review', 'required-ci', 'deploy', 'publish', 'credentials', 'approval',
                   'production-merge-review', 'typecheck', 'build')
ROUTINE_STAGES = ('implement', 'check', 'impact-map', 'test-evidence')  # review, release, production, unknown: full
MAX_PATHS = 2000
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,79}')


class GitError(Exception):
    pass


class InvariantError(Exception):
    pass


# ------------------------------------------------------------------ classification

_DOC_EXT = {'.md', '.mdx', '.rst', '.txt'}
_DOC_NAME = re.compile(r'^(readme|changelog|contributing|license|guide|notice|authors)')
_BEHAVIOR_NAMES = {'skill.md', 'claude.md', 'agents.md', 'gemini.md', 'claude.local.md', '.cursorrules'}
_BEHAVIOR_DIRS = {'commands', 'agents', 'skills', 'prompts'}
_UI_ONLY = {'.css', '.scss', '.sass', '.less', '.styl', '.html', '.htm', '.hbs', '.ejs', '.pug', '.njk', '.liquid',
            '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.woff', '.woff2', '.ttf', '.otf'}
_UI_CODE = {'.tsx', '.jsx', '.vue', '.svelte', '.astro'}  # carry logic too
_LOGIC = {'.py', '.js', '.mjs', '.cjs', '.ts', '.mts', '.cts', '.go', '.rs', '.java', '.kt', '.rb', '.php', '.c',
          '.h', '.cc', '.cpp', '.hpp', '.cs', '.swift', '.sh', '.bash', '.zsh', '.lua', '.pl', '.ex', '.exs',
          '.scala', '.dart'}
_CONFIG = {'.json', '.jsonc', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.xml', '.properties'}
_UI_DIRS = {'components', 'pages', 'app', 'routes', 'templates', 'views', 'styles', 'layouts', 'screens', 'public',
            'static', 'assets', 'ui'}
_TEST_DIRS = {'test', 'tests', '__tests__', 'spec', 'specs', 'e2e', '__mocks__'}
_TEST_NAME = re.compile(r'(\.test\.|\.spec\.|_test\.|_spec\.|^test_)')
_E2E = re.compile(r'(e2e|playwright|cypress|storybook|\.stories\.)')

_P_NAME = re.compile(
    r'^(dockerfile.*|.*\.dockerfile|docker-compose.*|compose\.ya?ml|g?makefile|jenkinsfile|procfile|vercel\.json|'
    r'netlify\.toml|fly\.toml|render\.yaml|wrangler\.toml|app\.yaml|serverless\.ya?ml|cloudbuild.*|buildspec.*|'
    r'azure-pipelines.*|\.gitlab-ci.*|\.travis.*|bitbucket-pipelines.*|codeowners|\.npmrc|\.netrc|\.pgpass|'
    r'\.env.*|.*\.env|.*\.env\..*|env\..*|\.nvmrc|\.node-version|\.python-version|\.tool-versions|'
    r'\.pre-commit-config\.ya?ml|hooks\.json|settings.*\.json|\.mcp\.json|plugin\.json|marketplace\.json|'
    r'package\.json|package-lock\.json|npm-shrinkwrap\.json|pnpm-workspace\.ya?ml|requirements.*\.txt|'
    r'constraints.*\.txt|pyproject\.toml|setup\.py|setup\.cfg|pipfile.*|go\.mod|go\.sum|cargo\..*|gemfile.*|'
    r'composer\.json|pom\.xml|build\.gradle.*|settings\.gradle.*|gradle\.properties|mix\.exs|deno\.jsonc?|'
    r'schema\.prisma|id_[a-z0-9]+|.*\.(tf|tfvars|sql|pem|key|p12|pfx|keystore|crt|cer))$')
_LOCK = re.compile(r'(^|[._-])lock(file)?([._-]|$)|\.lockb?$')
_P_DIRS = {'.github', '.circleci', '.gitlab', '.vercel', 'netlify', '.claude', '.codex', '.agents', '.claude-plugin',
           '.codex-plugin', '.husky', 'hooks', 'terraform', 'k8s', 'kubernetes', 'helm', 'ansible', 'charts',
           'infra', 'infrastructure', 'deploy', 'deployment', 'deployments', 'migrations', 'migration', 'migrate',
           'prisma', 'drizzle', 'supabase', 'pulumi'}
_CI_DIRS = {'ci', 'cd', '.ci', 'pipelines', 'workflows', 'release', 'releases'}
_AUTH_TOKENS = {'auth', 'authn', 'authz', 'authentication', 'authorization', 'authorize', 'authorise', 'session',
                'sessions', 'permission', 'permissions', 'rbac', 'acl', 'oauth', 'oauth2', 'sso', 'saml', 'jwt',
                'login', 'logout', 'signin', 'signup', 'password', 'passwd', 'csrf', 'cors', 'security',
                'middleware', 'guard', 'guards', 'policy', 'policies', 'credential', 'credentials', 'secret',
                'secrets', 'token', 'tokens', 'apikey', 'privatekey', 'keystore', 'keychain', 'passkey', 'mfa',
                '2fa', 'otp'}


def _protected(path, parts, name) -> bool:
    if _P_NAME.match(name) or _LOCK.search(name):
        return True
    if set(parts[:-1]) & _P_DIRS or (set(parts[:-1]) & _CI_DIRS and name.endswith(('.yml', '.yaml'))):
        return True
    tokens = set(re.findall(r'[a-z0-9]+', re.sub(r'([a-z])([A-Z])', r'\1 \2', path).lower()))
    squashed = re.sub(r'[^a-z0-9]', '', path.lower())
    return bool(tokens & _AUTH_TOKENS) or 'apikey' in squashed or 'privatekey' in squashed


def classify(path) -> set:
    """Classes of one repo-relative path: protected, docs, ui, logic, test, config, unknown (any unknown means full)."""
    parts = path.lower().split('/')
    name = parts[-1]
    ext = os.path.splitext(name)[1]
    if _protected(path, parts, name):
        return {'protected'}
    if name in _BEHAVIOR_NAMES or set(parts[:-1]) & _BEHAVIOR_DIRS:
        return {'logic'}  # prompts and skill text are behavior, not documentation
    if ext in _DOC_EXT and (parts[0] == 'docs' or 'docs' in parts[:-1] or (len(parts) == 1 and ext == '.md')
                            or _DOC_NAME.match(name)):
        return {'docs'}
    if ext not in _UI_ONLY | _UI_CODE | _LOGIC | _CONFIG:
        return {'unknown'}
    if set(parts[:-1]) & _TEST_DIRS or _TEST_NAME.search(name):
        return {'test', 'ui'} if _E2E.search(path.lower()) else {'test'}
    classes = {'ui'} if ext in _UI_ONLY | _UI_CODE or set(parts[:-1]) & _UI_DIRS else set()
    if ext in _UI_CODE | _LOGIC:
        classes.add('logic')
    if ext in _CONFIG:
        return {'config'}
    return classes


# ------------------------------------------------------------------ git facts

def _git(top, *args) -> bytes:
    try:
        done = subprocess.run(['git', '-c', 'core.excludesFile=/dev/null', '-c', 'core.quotepath=off',
                               '-C', str(top), *args], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitError(type(exc).__name__) from None
    if done.returncode != 0:
        raise GitError('git ' + args[0] + ' exited ' + str(done.returncode))
    return done.stdout


def collect(repo, base) -> dict:
    """Complete change set against `base` (default: merge-base with origin/main, else HEAD~): committed,
    staged, unstaged and untracked paths, renames/copies with both paths, deletions and mode changes."""
    top = _git(repo, 'rev-parse', '--show-toplevel').decode().strip()
    if base:
        if base.startswith('-'):
            raise GitError('invalid base ref')
        sha = _git(top, 'rev-parse', '--verify', base + '^{commit}').decode().strip()
    else:
        try:
            sha = _git(top, 'merge-base', 'origin/main', 'HEAD').decode().strip()
        except GitError:
            sha = _git(top, 'rev-parse', '--verify', 'HEAD~^{commit}').decode().strip()
    tokens = _git(top, 'diff', '--raw', '-z', '-M', '--find-copies', '--no-ext-diff', '--no-color',
                  '--ignore-submodules=none', sha).decode('utf-8', 'surrogateescape').split('\0')
    entries, flags, i = [], [], 0
    while i < len(tokens) and tokens[i]:
        meta = tokens[i].lstrip(':').split(' ')
        if len(meta) != 5 or not meta[4]:
            raise GitError('unparseable diff output')
        status, count = meta[4][0], 2 if meta[4][0] in 'RC' else 1
        paths = tokens[i + 1:i + 1 + count]
        if len(paths) != count or not all(paths):
            raise GitError('unparseable diff output')
        entries.append({'status': status, 'paths': paths, 'mode': meta[1]})
        if status not in 'ADMRC':
            flags.append(f'unsupported change type {status}: {paths[-1]}')
        elif status in 'MR' and meta[0] != meta[1]:
            flags.append(f'mode change: {paths[-1]}')
        if '120000' in (meta[0], meta[1]) or '160000' in (meta[0], meta[1]):
            flags.append(f'symlink or submodule: {paths[-1]}')
        i += 1 + count
    for path in _git(top, 'ls-files', '--others', '--exclude-standard', '--full-name', '-z'
                     ).decode('utf-8', 'surrogateescape').split('\0'):
        if path:
            entries.append({'status': '?', 'paths': [path], 'mode': ''})
    content = {}
    for path in sorted({p for e in entries for p in e['paths']}):
        target = Path(top) / path
        if target.is_symlink() or (target.exists() and not target.is_file()):
            flags.append(f'symlink or special file: {path}')
            content[path] = 'SPECIAL'
        elif target.is_file():
            content[path] = hashlib.sha256(target.read_bytes()).hexdigest()
        else:
            content[path] = 'DELETED'
    for e in entries:
        if e['status'] == '?':
            e['mode'] = '100755' if os.access(Path(top) / e['paths'][0], os.X_OK) else '100644'
    return {'base': sha, 'entries': entries, 'content': content, 'flags': flags}


# ------------------------------------------------------------------ deterministic plan

def sha256(value) -> str:
    data = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(data).hexdigest()


def normalize_stage(stage) -> str:
    return re.sub(r'[^a-z0-9-]', '', str(stage).lower())


def load_checks(path) -> tuple:
    """(checks, sha256 of the file bytes); ValueError for an unusable file."""
    raw = Path(path).read_bytes()
    if len(raw) > 1 << 20:
        raise ValueError('checks file too large')
    data = json.loads(raw)
    data = data.get('checks') if isinstance(data, dict) else data
    if not isinstance(data, list) or not data:
        raise ValueError('checks must be a non-empty list')
    checks, seen = [], set()
    for item in data:
        if (not isinstance(item, dict) or not isinstance(item.get('id'), str) or not _ID.fullmatch(item['id'])
                or item['id'] in seen or not isinstance(item.get('kind'), str)):
            raise ValueError('each check needs a unique id and a kind')
        seen.add(item['id'])
        checks.append({'id': item['id'], 'kind': item['kind'] if item['kind'] in KINDS else 'other'})
    return checks, sha256(raw)


def analyse(repo, base, stage, checks, checks_sha) -> dict:
    stage = normalize_stage(stage)
    out = {'eligible': False, 'reasons': [], 'diffSha256': None, 'base': None, 'stage': stage, 'classes': {},
           'full': checks, 'mandatory': checks, 'relaxable': [], 'relaxedPlan': checks, 'skipped': [], 'paths': []}
    try:
        change = collect(repo, base)
    except (GitError, ValueError, OSError) as exc:
        out['reasons'].append(f'git failure: {exc}')
        return out
    paths = sorted(change['content'])
    lines = sorted('\t'.join([e['status'], *e['paths'], e['mode']]) for e in change['entries'])
    out.update(base=change['base'], paths=paths, diffSha256=sha256(
        {'lines': lines, 'content': change['content'], 'stage': stage, 'checks': checks_sha}))
    by_path = {p: classify(p) for p in paths}
    for name in ('protected', 'unknown', 'config', 'docs', 'ui', 'logic', 'test'):
        out['classes'][name] = sum(name in c for c in by_path.values())
    blockers = list(change['flags'])
    if stage not in ROUTINE_STAGES:
        blockers.append(f'stage {stage or "(empty)"} is not a routine stage')
    if not paths:
        blockers.append('no changes detected')
    if len(paths) > MAX_PATHS:
        blockers.append('too many changed paths')
    for cls, label in (('protected', 'protected path'), ('unknown', 'unclassified path'),
                       ('config', 'configuration path')):
        blockers += [f'{label}: {p}' for p in paths if cls in by_path[p]][:5]
    if blockers:
        out['reasons'] = blockers[:12]
        return out
    docs_only = all(c == {'docs'} for c in by_path.values())
    has_ui = any('ui' in c for c in by_path.values())
    has_logic = any('logic' in c for c in by_path.values())
    relaxable, relaxed, skipped = [], [], []
    for check in checks:
        kind, replacement = check['kind'], 'skip'
        if kind == 'test-full' and docs_only:
            replacement = {'id': check['id'] + ':affected', 'kind': 'test-affected', 'relaxedFrom': check['id']}
        elif kind == 'lint':
            replacement = {'id': check['id'] + ':changed', 'kind': 'lint-changed', 'relaxedFrom': check['id']}
        elif not ((kind == 'browser-qa' and not has_ui) or (kind == 'mutation' and not has_logic)):
            relaxed.append(check)
            continue
        relaxable.append(check)
        if replacement == 'skip':
            skipped.append(check)
        else:
            relaxed.append(replacement)
    if not relaxable:
        out['reasons'] = ['no relaxation rule applies to the required checks']
        return out
    out.update(eligible=True, reasons=[f"{c['id']} ({c['kind']}) may be relaxed" for c in relaxable],
               mandatory=[c for c in checks if c not in relaxable], relaxable=relaxable, relaxedPlan=relaxed,
               skipped=skipped)
    return out


def _enforce(plan, state) -> None:
    """Advice can only remove relaxable items; mandatory and never-relaxable checks must all survive."""
    ids = {p['id'] for p in plan}
    originals = {c['id'] for c in state['full']}
    relaxable = {c['id'] for c in state['relaxable']}
    if (not {c['id'] for c in state['mandatory']} <= ids
            or any(c['kind'] in NEVER_RELAXABLE and c['id'] not in ids for c in state['full'])
            or any(c['kind'] not in RELAXABLE_KINDS for c in state['relaxable'])
            or any(p['id'] not in originals and p.get('relaxedFrom') not in relaxable for p in plan)):
        raise InvariantError('relaxed plan violates the mandatory set')


# ------------------------------------------------------------------ Laya (advice only)

_ADVICE = []


def _advice():
    if not _ADVICE:
        spec = importlib.util.spec_from_file_location('typed_advice', Path(__file__).with_name('typed_advice.py'))
        _ADVICE.append(importlib.util.module_from_spec(spec))
        spec.loader.exec_module(_ADVICE[0])
    return _ADVICE[0]


def build_plan(repo, stage, checks_path, base=None, advise_options=None) -> dict:
    checks, checks_sha = load_checks(checks_path)
    state = analyse(repo, base, stage, checks, checks_sha)
    advice, recommendation = {'asked': False}, None
    if state['eligible']:
        summary = (f"stage={state['stage']}; changed={len(state['paths'])}; "
                   + ' '.join(f'{k}={v}' for k, v in state['classes'].items())
                   + '; relaxable=' + ','.join(c['kind'] for c in state['relaxable']))
        try:
            result = _advice().advise(DECISION, summary, CANDIDATES, state['diffSha256'], critical_if_wrong=True,
                                      question=QUESTION, policy=POLICY, files=state['paths'],
                                      **(advise_options or {}))
            rec = result.get('recommendation')
            recommendation = rec['id'] if rec else None
            advice = {'asked': True, 'decisionId': result['decisionId'], 'mode': result['mode'],
                      'holdback': result['holdback'], 'recommendation': recommendation}
        except Exception as exc:  # noqa: BLE001 - advice is optional; failure means the full plan
            advice = {'asked': True, 'error': type(exc).__name__}
    plan, reasons = state['full'], list(state['reasons'])
    if state['eligible'] and recommendation == 'relaxed':
        try:
            _enforce(state['relaxedPlan'], state)
            plan = state['relaxedPlan']
        except InvariantError as exc:
            reasons.append(str(exc) + '; full plan')
    elif state['eligible']:
        reasons.append('Laya did not recommend relaxation (shadow, off, holdback or no recommendation); full plan')
    return {'eligible': state['eligible'], 'reasons': reasons, 'diffSha256': state['diffSha256'],
            'stage': state['stage'], 'base': state['base'], 'repo': str(Path(repo).resolve()),
            'checksFile': str(Path(checks_path).resolve()), 'classes': state['classes'],
            'mandatory': state['mandatory'], 'relaxable': state['relaxable'], 'plan': plan,
            'full': state['full'], 'skipped': state['skipped'] if plan is state['relaxedPlan'] else [],
            'advice': advice}


def verify_plan(plan_file, stage=None) -> dict:
    """{'valid': bool, 'reasons': [...], 'plan': [...]}; when not valid, `plan` is the full list (or empty)."""
    try:
        saved = json.loads(Path(plan_file).read_text())
        checks, checks_sha = load_checks(saved['checksFile'])
        now = analyse(saved['repo'], saved['base'], saved['stage'], checks, checks_sha)
    except (OSError, ValueError, KeyError, TypeError):
        return {'valid': False, 'reasons': ['plan file or checks file unreadable'], 'plan': []}
    reasons = []
    if stage is not None and normalize_stage(stage) != saved['stage']:
        reasons.append('stage changed')
    if now['diffSha256'] is None or now['diffSha256'] != saved.get('diffSha256'):
        reasons.append('diff, checks file or stage changed')
    plan = saved.get('plan')
    if not reasons and plan != now['full'] and not (now['eligible'] and plan == now['relaxedPlan']):
        reasons.append('plan does not match the deterministic plan')
    return {'valid': not reasons, 'reasons': reasons or ['unchanged'], 'plan': plan if not reasons else now['full']}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--repo', required=True)
    p.add_argument('--base')
    p.add_argument('--stage', required=True)
    p.add_argument('--checks', required=True)
    p.add_argument('--out')
    v = sub.add_parser('verify')
    v.add_argument('--plan-file', required=True)
    v.add_argument('--stage')
    o = sub.add_parser('outcome')
    o.add_argument('--decision-id', required=True)
    o.add_argument('--chosen', required=True, choices=('full', 'relaxed'))
    args = parser.parse_args(argv)
    if args.cmd == 'plan':
        try:
            result = build_plan(args.repo, args.stage, args.checks, args.base)
        except (OSError, ValueError) as exc:
            print(json.dumps({'error': str(exc)}), file=sys.stderr)
            return 2
        text = json.dumps(result, indent=2, sort_keys=True)
        if args.out:
            Path(args.out).write_text(text + '\n')
            os.chmod(args.out, 0o600)
        print(text)
        return 0
    if args.cmd == 'verify':
        result = verify_plan(args.plan_file, args.stage)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result['valid'] else 3
    return 0 if _advice().record_outcome(DECISION, args.decision_id, args.chosen) else 1


if __name__ == '__main__':
    sys.exit(main())
