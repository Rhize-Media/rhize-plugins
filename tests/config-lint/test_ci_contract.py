"""Guard CI costs without excluding executable plugin instruction changes."""
from pathlib import Path
import fnmatch
import re

import yaml

ROOT = Path(__file__).resolve().parents[2]


def workflow(name):
    # BaseLoader preserves GitHub's `on` key instead of parsing it as a YAML 1.1 bool.
    return yaml.load((ROOT / '.github/workflows' / name).read_text(), Loader=yaml.BaseLoader)


def selected(path, patterns):
    included = False
    for pattern in patterns:
        exclude = pattern.startswith('!')
        glob = pattern.lstrip('!')
        # GitHub's leading **/ also matches a root-level file.
        matches = fnmatch.fnmatchcase(path, glob) or (
            glob.startswith('**/') and fnmatch.fnmatchcase(path, glob[3:])
        )
        if matches:
            included = not exclude
    return included


def test_narrative_docs_skip_but_runtime_instructions_and_code_run():
    data = workflow('validate.yml')
    for event in ('push', 'pull_request'):
        assert data['on'][event]['branches'] == ['main']
        paths = data['on'][event]['paths']
        for path in ('README.md', 'STATE.md', 'docs/guide.md', '.claude/plans/ci.md',
                     '.wolf/anatomy.md', 'rhize-core/README.md', 'rhize-core/GUIDE.md'):
            assert not selected(path, paths), path
        for path in ('rhize-core/skills/setup/SKILL.md', 'rhize-devflow/commands/review.md',
                     'rhize-devflow/agents/verifier.md', 'rhize-devflow/docs/impact-map-reference.md',
                     'rhize-core/skills/setup/references/contract.md',
                     'rhize-devflow/.codex-plugin/migrated-command-skills/review/SKILL.md',
                     'scripts/bump_version.py', '.github/package-lock.json',
                     '.github/requirements-ci.txt', '.github/workflows/validate.yml'):
            assert selected(path, paths), path


def test_ci_is_bounded_and_publishing_is_not_cancelled():
    for name in ('validate.yml', 'tag-release.yml'):
        data = workflow(name)
        assert data['concurrency']['cancel-in-progress'] == ('true' if name == 'validate.yml' else 'false')
        if name == 'tag-release.yml':
            assert data['concurrency']['queue'] == 'max'
        for job in data['jobs'].values():
            assert job['runs-on'] == 'ubuntu-latest'
            assert 0 < int(job['timeout-minutes']) <= 15
            for step in job['steps']:
                if 'uses' in step:
                    assert re.search(r'@[0-9a-f]{40}$', step['uses'])
    assert workflow('tag-release.yml')['on']['push']['paths'] == ['.claude-plugin/marketplace.json']


def test_version_gate_remains_in_required_validation_job():
    data = workflow('validate.yml')
    step = next(s for s in data['jobs']['validate']['steps'] if s.get('name') == 'Validate version bumps')
    assert step['if'] == "github.event_name == 'pull_request'"
    assert '--check --since "origin/$BASE_REF"' in step['run']
    assert step['env']['BASE_REF'] == '${{ github.base_ref }}'
    assert data['permissions'] == {'contents': 'read'}
