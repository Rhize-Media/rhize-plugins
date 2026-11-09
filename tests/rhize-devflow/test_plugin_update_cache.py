"""Real filesystem invariants for additive publication, without live cache effects."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'rhize-devflow/scripts/plugin_update_cache.py'
spec = importlib.util.spec_from_file_location('cache', SCRIPT)
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


def package(path, version):
    (path / '.claude-plugin').mkdir(parents=True)
    (path / '.claude-plugin/plugin.json').write_text(json.dumps({'name': 'fixture', 'version': version}))
    (path / 'hook.py').write_text('print("intact")')
    return path


@pytest.fixture
def publication(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.Path, 'home', lambda: tmp_path)
    old = package(tmp_path / '.codex/plugins/cache/rhize-plugins/fixture/1.0.0', '1.0.0')
    new = package(tmp_path / 'staged', '1.1.0')
    before = {'fixture': {'version': '1.0.0', 'path': str(old), 'enabled': True}}
    staged = {'fixture': {'path': str(new), 'digest': cache.tree(new)}}
    return tmp_path, old, new, before, staged


def publish(before, staged, version='1.1.0'):
    return cache.publish('codex', {'fixture': version}, before, staged, None, None)


def test_publication_keeps_old_paths_bytes_and_inodes(publication):
    root, old, new, before, staged = publication
    original = {(str(p.relative_to(old)), p.stat().st_ino, p.read_bytes()) for p in old.rglob('*') if p.is_file()}
    result = publish(before, staged)
    assert cache.tree(Path(result['fixture']['path'])) == cache.tree(new)
    assert original == {(str(p.relative_to(old)), p.stat().st_ino, p.read_bytes()) for p in old.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='collision'):
        publish(before, staged)


def test_equal_version_is_noop_and_downgrade_refused(publication):
    _, old, _, before, staged = publication
    assert publish(before, staged, '1.0.0') == before
    with pytest.raises(ValueError, match='newer'):
        publish(before, staged, '0.9.0')
    assert old.is_dir()


@pytest.mark.parametrize('kind', ['changed', 'link', 'collision'])
def test_invalid_stage_cannot_touch_old_version(publication, kind):
    root, old, new, before, staged = publication
    digest = cache.tree(old)
    if kind == 'changed':
        (new / 'hook.py').write_text('unexpected')
    elif kind == 'link':
        (new / 'link').symlink_to(old / 'hook.py')
    else:
        (old.parent / '1.1.0').mkdir()
    with pytest.raises(ValueError):
        publish(before, staged)
    assert cache.tree(old) == digest


def test_claude_registration_never_manually_written(publication):
    _, _, _, before, staged = publication
    with pytest.raises(ValueError, match='unsupported_host'):
        cache.publish('claude', {'fixture': '1.1.0'}, before, staged, None, None)


def test_staging_reads_commit_not_dirty_worktree(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
    git('init', '-q')
    package(repo / 'fixture', '1.1.0')
    (repo / '.claude-plugin').mkdir()
    (repo / '.claude-plugin/marketplace.json').write_text('{"name":"rhize-plugins"}')
    git('add', '.')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture')
    commit = git('rev-parse', 'HEAD')
    (repo / 'fixture/hook.py').write_text('dirty content')
    def native(args, home):
        if args[2] == 'marketplace':
            assert (Path(args[-1]) / 'fixture/hook.py').read_text() == 'print("intact")'
        else:
            import shutil
            shutil.copytree(home / 'catalog/fixture', home / '.codex/plugins/cache/rhize-plugins/fixture/1.1.0')
    monkeypatch.setattr(cache, 'native', native)
    staged = cache.prepare('codex', '/fixture/cli', repo, {'fixture': '1.1.0'}, tmp_path, commit)
    assert (Path(staged['fixture']['path']) / 'hook.py').read_text() == 'print("intact")'
    assert staged['fixture']['sourceCommit'] == commit
