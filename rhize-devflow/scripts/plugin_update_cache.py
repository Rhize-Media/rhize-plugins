"""Prepare with native CLIs in isolation; publish new versions without removing old paths."""
from __future__ import annotations

import hashlib
import io
import tarfile
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import tempfile


def tree(path):
    """Reject links/special files before copying any executable package content."""
    if path.is_symlink() or not path.is_dir():
        raise ValueError('invalid_package_directory')
    rows = []
    for item in sorted(path.rglob('*')):
        info = item.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('package_link_or_special_file')
        rows.append((str(item.relative_to(path)), stat.S_IMODE(info.st_mode),
                     hashlib.sha256(item.read_bytes()).hexdigest()))
        if len(rows) > 20000:
            raise ValueError('package_file_limit')
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def native(args, home):
    env = {'HOME': str(home), 'CODEX_HOME': str(home / '.codex'),
           'CLAUDE_CONFIG_DIR': str(home / '.claude'), 'PATH': os.environ['PATH'],
           'LANG': 'en_US.UTF-8', 'NO_COLOR': '1'}
    process = subprocess.Popen(args, cwd=home, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, _ = process.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    if process.returncode:
        raise ValueError('isolated_native_install_failed:' + str(process.returncode))
    if len(stdout) > 16 * 1024 * 1024:
        raise ValueError('native_output_limit')


def prepare(host, cli, catalog, targets, folder, commit):
    if host != 'codex':
        raise ValueError('idle_publication_unsupported_host')
    home = Path(tempfile.mkdtemp(prefix='staged-', dir=folder))
    (home / '.codex').mkdir()
    snapshot = home / 'catalog'
    snapshot.mkdir()
    result = subprocess.run(['/usr/bin/git', '--no-replace-objects', '-C', str(catalog),
                             'archive', commit, '.claude-plugin/marketplace.json', *targets],
                            capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError('approved_snapshot_unavailable')
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        members = archive.getmembers()
        if any(not (m.isfile() or m.isdir()) or Path(m.name).is_absolute()
               or '..' in Path(m.name).parts for m in members):
            raise ValueError('unsafe_approved_snapshot')
        archive.extractall(snapshot, filter='data')
    native([cli, 'plugin', 'marketplace', 'add', str(snapshot)], home)
    staged = {}
    for name, version in targets.items():
        native([cli, 'plugin', 'add', name + '@rhize-plugins'], home)
        path = home / '.codex/plugins/cache/rhize-plugins' / name / version
        manifest = json.loads((path / '.claude-plugin/plugin.json').read_text())
        if manifest.get('name') != name or manifest.get('version') != version:
            raise ValueError('staged_manifest_mismatch')
        staged[name] = {'path': str(path), 'digest': tree(path), 'sourceCommit': commit}
    return staged


def publish(host, targets, before, staged, read, write):
    if host != 'codex':
        raise ValueError('idle_publication_unsupported_host')
    cache = Path.home() / ('.' + host) / 'plugins/cache/rhize-plugins'
    changes = []
    for name, version in targets.items():
        old = before[name]
        if version == old['version']:
            continue
        if tuple(map(int, version.split('.'))) < tuple(map(int, old['version'].split('.'))):
            raise ValueError('publication_requires_newer_version')
        destination = cache / name / version
        if any(p.is_symlink() for p in (destination, *destination.parents)) or destination.exists():
            raise ValueError('immutable_version_collision')
        source = Path(staged[name]['path'])
        if tree(source) != staged[name]['digest']:
            raise ValueError('staged_package_changed')
        prior = Path(old['path'])
        if prior != cache / name / old['version']:
            raise ValueError('unexpected_previous_cache_path')
        tree(prior)
        changes.append((name, source, destination))
    # Every collision and schema check precedes publication. On interruption preserve both old and new paths.
    for name, source, destination in changes:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.rhize-stage-', dir=destination.parent) as temporary:
            package = Path(temporary) / 'package'
            shutil.copytree(source, package)
            if tree(package) != staged[name]['digest']:
                raise ValueError('staged_copy_changed')
            if destination.exists() or destination.is_symlink():
                raise ValueError('immutable_version_collision')
            os.rename(package, destination)
    return {**before, **{name: {'version': targets[name], 'enabled': before[name]['enabled'], 'path': str(path)}
                        for name, _, path in changes}}
