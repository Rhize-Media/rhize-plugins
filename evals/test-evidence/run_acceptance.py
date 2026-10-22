#!/usr/bin/env python3
"""Explicit, provider-free Docker acceptance; requires existing local digest-pinned images."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('test_evidence', ROOT / 'rhize-devflow/scripts/test_evidence.py')
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def fixture(root, test):
    root.mkdir()
    git(root, 'init', '-q')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    git(root, 'config', 'user.name', 'Fixture')
    (root / 'calc.py').write_text('def add(a,b): return a + b\n')
    (root / 'tests').mkdir()
    (root / 'tests/test_calc.py').write_text(test)
    (root / '.envrc').write_text('FAKE_SECRET=must-not-be-mounted\n')
    git(root, 'add', '.')
    git(root, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
    return dict(schema_version=evidence.RUN_SPEC_VERSION, base_sha=git(root, 'rev-parse', 'HEAD'),
                contract_class='behavior', invariant='addition returns a mathematical sum',
                test_files=['tests/test_calc.py'], production_files=['calc.py'],
                oracle={'kind': 'independent', 'evidence': 'known arithmetic 2+3=5'},
                mutation={'target_path': 'calc.py', 'search': 'a + b', 'replace': 'a - b', 'external_effect': False},
                test_invocation={'source': 'python_unittest', 'name': 'tests/test_calc.py'}, timeout_seconds=20)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--node-image')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='rhize-evidence-acceptance-') as directory:
        root = Path(directory).resolve()
        socket = os.environ.get('DOCKER_HOST') or next(('unix://' + str(p) for p in
            (Path('/var/run/docker.sock'), Path.home() / '.docker/run/docker.sock') if p.is_socket()), '')
        adapter = evidence.sandbox_adapter()
        original_client = adapter.DockerSandbox.client
        names = []
        def observed_client(self, *argv, **kwargs):
            if argv[0] == 'run':
                names.append(argv[argv.index('--name') + 1])
            try:
                return original_client(self, *argv, **kwargs)
            except adapter.SandboxUnavailable as exc:
                print(json.dumps({'operation': argv[0], 'unavailable': str(exc)}), file=sys.stderr)
                raise
        standard = 'import unittest\nfrom calc import add\nclass Math(unittest.TestCase):\n def test_add(self): self.assertEqual(add(2,3),5)\n'
        results = {}
        with patch.dict(os.environ, {'HOME': str(root / 'home'), 'DOCKER_HOST': socket, 'OPENAI_API_KEY': 'fake-never-inherit'}), patch.object(evidence, 'sandbox_adapter', return_value=adapter), patch.object(adapter.DockerSandbox, 'client', observed_client):
            for label, test in [('mutant', standard), ('syntax', standard), ('setup', standard.replace('def test_add(self):', 'def setUp(self):') + ' def test_valid(self): self.assertTrue(True)\n'), ('isolation', standard + '''
 def test_isolation(self):
  import os, socket
  from pathlib import Path
  self.assertNotEqual(os.getuid(),0)
  self.assertIsNone(os.environ.get('OPENAI_API_KEY'))
  self.assertFalse(Path('/workspace/.envrc').exists())
  self.assertFalse(Path('/var/run/docker.sock').exists())
  self.assertFalse(Path('OUTSIDE_PATH').exists())
  with self.assertRaises(OSError): Path('/workspace/calc.py').write_text('bad')
  with self.assertRaises(OSError): Path('/forbidden-write').write_text('bad')
  with self.assertRaises(OSError): socket.create_connection(('198.18.0.1',80),timeout=.25)
'''.replace('OUTSIDE_PATH', str(root / 'outside-secret'))), ('timeout', '''
import subprocess,sys,time,unittest
class Deadline(unittest.TestCase):
 def test_descendant(self):
  subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
  time.sleep(60)
''')]:
                (root / 'outside-secret').write_text('fake-host-secret')
                repo = root / label
                spec = fixture(repo, test)
                if label == 'isolation': spec['mutation'] = None
                if label == 'timeout': spec.update(mutation=None, timeout_seconds=1)
                if label == 'syntax': spec['mutation']['replace'] = '['
                packet = evidence.run_evidence(repo, spec, root / (label + '.json'), root / 'leases', args.image)
                verdict = evidence.validate_packet(packet, repo)
                expected = 'killed' if label == 'mutant' else 'oracle_supported' if label == 'isolation' else 'mutation_unavailable'
                assert packet['verdict'] == expected, (label, packet)
                assert verdict['review_verdict'] == ('supported' if label in ('mutant','isolation') else 'unsupported'), verdict
                assert git(repo, 'status', '--porcelain') == ''
                results[label] = {'verdict': packet['verdict'], 'review': verdict['review_verdict']}
                print(json.dumps({'case': label, **results[label]}), file=sys.stderr)
            if args.node_image:
                repo = root / 'node'
                spec = fixture(repo, standard)
                (repo / 'package.json').write_text(json.dumps({'scripts': {'test': 'node test.js'}}))
                (repo / 'calc.js').write_text('exports.add = (a,b) => a + b;\n')
                (repo / 'test.js').write_text("if(require('./calc').add(2,3)!==5)process.exit(1);\n")
                git(repo, 'add', '.')
                git(repo, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Node fixture')
                spec.update(base_sha=git(repo,'rev-parse','HEAD'),test_files=['test.js'],production_files=['calc.js'],test_invocation={'source':'package_script','name':'test'},mutation=None)
                packet = evidence.run_evidence(repo, spec, root / 'node.json', root / 'leases', args.node_image)
                assert packet['verdict'] == 'oracle_supported', packet
                assert evidence.validate_packet(packet, repo)['review_verdict'] == 'supported'
                results['node'] = {'verdict': 'oracle_supported', 'review': 'supported'}
            probe = adapter.DockerSandbox(args.image, root / 'final-config')
            for name in names:
                assert probe.client('ps', '-aq', '--filter', 'name=^/' + name + '$') == '', name
        print(json.dumps({'acceptance': 'passed', 'cases': results, 'containers_removed': len(names), 'provider_calls': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
