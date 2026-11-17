"""Privacy and invocation semantics, with real subprocesses and isolated homes only."""
import contextlib
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

SCRIPTS = Path(__file__).resolve().parents[2] / 'rhize-ad-research/scripts'
spec = importlib.util.spec_from_file_location('usage', SCRIPTS / 'usage_telemetry.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


def event(host='codex'):
    return dict(id=uuid.uuid4().hex, day=u.today().isoformat(), version='0.5.0', declared_host=host,
                operation='reddit-search', provider='public-adapter', status='retrieved', error='none',
                duration='lt1s', returned=1, dropped=0, tokens=None, cost=None)


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve()
        self.home_patch = patch.dict(os.environ, HOME=str(self.home))
        self.home_patch.start()
    def tearDown(self):
        self.home_patch.stop()
        self.tmp.cleanup()
    def enabled(self):
        u.control('enable')
        return self.state()['generation']
    def state(self):
        with u.directory() as fd:
            return u.read(fd)
    def run_cli(self, name, *args, home=None):
        return subprocess.run([sys.executable, '-I', str(SCRIPTS / name), *args],
                              capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL,
                              env=dict(os.environ, HOME=str(home or self.home)))
    def test_disabled_no_mutations_or_lock_or_diagnostics(self):
        with patch.object(u, 'locked', side_effect=AssertionError('lock')), contextlib.redirect_stderr(io.StringIO()) as err:
            with u.measure('codex', 'meta-doctor', 'meta-response-journal') as outcome:
                outcome('checked')
        self.assertEqual(err.getvalue(), '')
        self.assertEqual(list(self.home.iterdir()), [])
        self.enabled(); u.control('disable')
        before = (u.root() / 'state.json').read_bytes()
        with patch.object(u, 'locked', side_effect=AssertionError('lock')):
            with u.measure('claude', 'meta-doctor', 'meta-response-journal') as outcome: outcome('checked')
        self.assertEqual(before, (u.root() / 'state.json').read_bytes())
    def test_closed_schema_and_secret_canaries(self):
        row = event()
        for key, value in [('query', 'CANARY_SECRET'), ('declared_host', 'CANARY_SECRET'),
                           ('error', 'CANARY_SECRET'), ('version', 'CANARY_SECRET'), ('returned', True),
                           ('returned', 101), ('tokens', 3), ('cost', 0)]:
            with self.subTest(key=key, value=value), self.assertRaises((ValueError, TypeError)):
                u.validate_event(dict(row, **{key: value}))
        secret_exception = type('CANARY_SECRET', (Exception,), {})('CANARY_SECRET')
        self.assertEqual(u.classify(secret_exception), 'unclassified')
        self.assertEqual(u.classify(ValueError('CANARY_SECRET')), 'unclassified')
        self.assertEqual(u.classify(ValueError('rate_limited')), 'rate_limit')
        self.enabled()
        with u.measure('codex', 'reddit-search', 'public-adapter') as outcome:
            outcome('unavailable', u.classify(secret_exception))
        self.assertNotIn('CANARY', (u.root() / 'state.json').read_text())
    def test_enable_tty_required_and_no_store_created(self):
        result = self.run_cli('usage_telemetry.py', 'enable')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(u.root().exists())
    def test_duplicate_event_and_concurrent_hosts_no_loss(self):
        generation = self.enabled()
        rows = [event('claude' if i % 2 else 'codex') for i in range(16)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda row: u.append(row, generation), rows))
        u.append(rows[0], generation)
        saved = self.state()['events']
        self.assertEqual({r['id'] for r in saved}, {r['id'] for r in rows})
        self.assertEqual({r['declared_host'] for r in saved}, {'claude', 'codex'})
    def test_disable_purge_reenable_invalidate_inflight(self):
        for command in ('disable', 'purge'):
            generation = self.enabled()
            u.control(command); self.enabled()
            u.append(event(), generation)
            self.assertEqual(self.state()['events'], [])
    def test_atomic_failure_preserves_old_state(self):
        generation = self.enabled()
        before = (u.root() / 'state.json').read_bytes()
        with patch.object(u.os, 'replace', side_effect=OSError('CANARY_SECRET')):
            with self.assertRaises(OSError): u.append(event(), generation)
        self.assertEqual(before, (u.root() / 'state.json').read_bytes())
        self.assertFalse(list(u.root().glob('.write-*')))
    def test_retention_report_cap_and_null_denominators(self):
        generation = self.enabled()
        old = dict(event(), day=(u.today() - u.dt.timedelta(days=31)).isoformat())
        with u.directory() as fd:
            state = u.read(fd); state['events'] = [old]; u.write(fd, state)
        self.assertEqual(u.report(self.state())['groups'], [])
        with patch.object(u, 'MAX_EVENTS', 2):
            for _ in range(3): u.append(dict(event(), returned=None, dropped=None), generation)
            saved = self.state()['events']
            self.assertEqual(len(saved), 2)
        report = u.control('report')
        self.assertEqual(report['groups'][0]['returned_unknown'], 2)
        self.assertEqual(report['groups'][0]['returned_known'], 0)
        serialized = json.dumps(report)
        for row in saved:
            self.assertNotIn(row['id'], serialized)
            self.assertNotIn(row['day'], serialized)
        self.assertIsNone(report['tokens'])
        self.assertIsNone(report['cost'])
    def test_file_types_owner_modes_bounds_and_purge_corrupt(self):
        self.enabled()
        state = u.root() / 'state.json'
        for bad in ('symlink', 'hardlink', 'fifo', 'mode', 'invalid', 'oversized', 'new_schema'):
            with self.subTest(bad=bad):
                if state.exists() or state.is_symlink(): state.unlink()
                target = self.home / 'target'; target.write_text('PRIVATE_CANARY'); target.chmod(0o600)
                if bad == 'symlink': state.symlink_to(target)
                elif bad == 'hardlink': os.link(target, state)
                elif bad == 'fifo': os.mkfifo(state, 0o600)
                elif bad == 'mode': state.write_text('{}'); state.chmod(0o644)
                elif bad == 'oversized': state.write_bytes(b'x' * (u.MAX_BYTES + 1)); state.chmod(0o600)
                elif bad == 'new_schema': state.write_text(json.dumps(dict(u.fresh(), schema=2))); state.chmod(0o600)
                else: state.write_text('{bad'); state.chmod(0o600)
                started = time.monotonic()
                with u.measure('codex', 'meta-doctor', 'meta-response-journal') as outcome: outcome('checked')
                self.assertLess(time.monotonic() - started, 1)
                with self.assertRaises((ValueError, OSError)):
                    u.control('status')
                u.control('purge')
                self.assertEqual(self.state()['events'], [])
                self.assertFalse(self.state()['enabled'])
                self.assertEqual(target.read_text(), 'PRIVATE_CANARY')
    def test_directory_symlink_and_private_mode(self):
        self.enabled()
        original = u.root(); other = original.with_name('other'); original.rename(other); original.symlink_to(other)
        with self.assertRaises(OSError): u.control('status')
        original.unlink(); other.rename(original); original.chmod(0o755)
        with self.assertRaises(ValueError): u.control('status')
        original.chmod(0o700)
        self.assertEqual((original / 'state.json').stat().st_mode & 0o777, 0o600)
        self.assertFalse((original / 'store.lock').exists())
    def test_keyboard_interrupt_propagates_and_is_not_success(self):
        self.enabled()
        with self.assertRaises(KeyboardInterrupt):
            with u.measure('codex', 'reddit-search', 'public-adapter'):
                raise KeyboardInterrupt()
        self.assertEqual(self.state()['events'][0]['status'], 'interrupted')
    def test_enabled_store_failure_does_not_change_research_exception(self):
        self.enabled()
        with patch.object(u, 'append', side_effect=OSError('CANARY_SECRET')), contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaisesRegex(RuntimeError, 'research'):
                with u.measure('claude', 'meta-doctor', 'meta-response-journal'):
                    raise RuntimeError('research')
        self.assertEqual(err.getvalue().strip(), u.WARNING)
    def test_read_schema_unknown_never_overwritten(self):
        self.enabled(); state = u.root() / 'state.json'
        raw = json.dumps(dict(u.fresh(), schema=99)); state.write_text(raw)
        with u.measure('codex', 'meta-doctor', 'meta-response-journal') as outcome: outcome('checked')
        self.assertEqual(state.read_text(), raw)
    def test_broker_never_imports_usage_or_touches_store(self):
        self.enabled(); before = (u.root() / 'state.json').read_bytes()
        code = "import runpy,sys; sys.argv=['agent_reach_public.py','--http']; runpy.run_path(sys.argv[0],run_name='__main__'); assert 'rhize_ad_usage' not in sys.modules"
        result = subprocess.run([sys.executable, '-I', '-c', code], cwd=SCRIPTS, input='{}', text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, (u.root() / 'state.json').read_bytes())
        self.assertEqual(result.stderr, '')
    def test_optional_module_missing_corrupt_symlink_preserves_cli(self):
        self.enabled()
        dest = self.home / 'copy'; dest.mkdir()
        for name in ('ad_research.py', 'research_brief.py', 'agent_reach_public.py'):
            shutil.copy(SCRIPTS / name, dest / name)
        module = dest / 'usage_telemetry.py'
        for mode in ('missing', 'corrupt', 'symlink'):
            if module.exists() or module.is_symlink(): module.unlink()
            if mode == 'corrupt': module.write_text('invalid Python !')
            elif mode == 'symlink': module.symlink_to(SCRIPTS / 'usage_telemetry.py')
            result = subprocess.run([sys.executable, '-I', str(dest / 'ad_research.py'), 'provider-check'], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            self.assertEqual(json.loads(result.stdout)['provider'], 'meta-ads-mcp')
            self.assertEqual(self.state()['events'], [])
            self.assertFalse((dest / '__pycache__').exists())
    def test_real_cli_hosts_stdout_parity_and_private_inputs(self):
        evidence = self.home / 'CANARY_PATH.json'
        data = {'schema': 1, 'run_id': str(uuid.uuid4()), 'host': 'codex', 'purpose': 'customer',
                'question': 'CANARY_QUESTION', 'queries': ['CANARY_QUERY'],
                'window': {'start': '2026-11-01', 'end': '2026-11-17'}, 'captured_at': '2026-11-17T01:00:00Z',
                'capture_method': 'host_transcribed', 'sources': [], 'findings': [], 'limitations': ['CANARY_CONTENT']}
        evidence.write_text(json.dumps(data))
        for host in ('claude', 'codex'):
            u.control('disable')
            baseline = self.run_cli('research_brief.py', str(evidence), '--host', host, '--format', 'json')
            self.enabled()
            enabled = self.run_cli('research_brief.py', str(evidence), '--host', host, '--format', 'json')
            self.assertEqual((enabled.stdout, enabled.stderr, enabled.returncode), (baseline.stdout, baseline.stderr, baseline.returncode))
            self.assertEqual(json.loads(enabled.stdout)['host'], 'codex')
            result = self.run_cli('ad_research.py', 'provider-check', '--host', host)
            self.assertEqual(result.returncode, 0)
            # Invalid URL fails before Docker or network; no sensitive input is recorded.
            result = self.run_cli('agent_reach_public.py', 'collect', '--host', host, '--operation', 'jina-read', '--target', 'CANARY_URL')
            self.assertEqual(result.returncode, 2)
        rows = self.state()['events']
        self.assertEqual(len(rows), 6)
        self.assertEqual({row['declared_host'] for row in rows}, {'claude', 'codex'})
        self.assertNotIn('CANARY', (u.root() / 'state.json').read_text())
        self.assertNotIn('CANARY', json.dumps(u.control('report')))
    def test_cli_argparse_errors_unobserved(self):
        self.enabled()
        self.assertEqual(self.run_cli('ad_research.py', 'plan').returncode, 2)
        self.assertEqual(self.state()['events'], [])

    def test_meta_import_empty_held_reuse_and_invoking_host(self):
        self.enabled()
        common = ['--client', 'CANARY_CLIENT', '--account', 'CANARY_ACCOUNT']
        def call(command, *args):
            r = self.run_cli('ad_research.py', command, *common, '--host', 'claude', *args)
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)
        call('setup', '--workspace', str(self.home / 'research'))
        for ads, total, expected in (([], 0, 'empty'), ([{'id': '12', 'page_id': '34', 'page_name': 'CANARY_CONTENT'}], 1, 'imported'), ([{'id': True}], 1, 'held')):
            run = call('plan', '--service', 'detailing', '--search-terms', 'CANARY_QUERY')
            call('collect', '--run', run['id'])
            self.assertEqual(self.state()['events'][-1]['status'], 'awaiting_response')
            inbox = self.home / 'inbox.json'
            inbox.write_text(json.dumps({'provider': 'meta-ads-mcp', 'tool': 'ads_library_search', 'request': run['input'],
                'run_id': run['id'], 'input_hash': run['input_hash'], 'capture_host': 'claude',
                'capture_method': 'host_transcribed', 'captured_at': u.dt.datetime.now(u.dt.timezone.utc).isoformat(),
                'response': {'ads': ads, 'estimated_total_count': total}}))
            call('resume', '--run', run['id'], '--response', str(inbox))
            self.assertEqual(self.state()['events'][-1]['status'], expected)
            # Cross-host invocation preserves original capture identity.
            r = self.run_cli('ad_research.py', 'resume', *common, '--host', 'codex', '--run', run['id'])
            self.assertEqual(r.returncode, 0)
            self.assertEqual(json.loads(r.stdout)['run']['capture_host'], 'claude')
            row = self.state()['events'][-1]
            self.assertEqual(row['declared_host'], 'codex')
            self.assertEqual(row['status'], 'held' if expected == 'held' else 'already_terminal')
            self.assertIsNone(row['returned'])
            if expected != 'held':
                call('export', '--run', run['id'], '--output', str(self.home / 'exports'))
                self.assertEqual(self.state()['events'][-1]['status'], 'exported')
        self.assertNotIn('CANARY', (u.root() / 'state.json').read_text())

    def test_public_rate_limit_empty_and_usable_are_distinct(self):
        spec = importlib.util.spec_from_file_location('public', SCRIPTS / 'agent_reach_public.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.enabled()
        for payload, status, error in ((ValueError('rate_limited'), 'unavailable', 'rate_limit'),
                ({'items': [], 'dropped_items': 0}, 'empty', 'none'),
                ({'items': [{'title': 'CANARY_CONTENT'}], 'dropped_items': 1}, 'retrieved', 'none')):
            kwargs = {'side_effect': payload} if isinstance(payload, Exception) else {'return_value': payload}
            with patch.object(sys, 'argv', ['cli', 'collect', '--host', 'codex', '--operation', 'reddit-search', '--query', 'CANARY_QUERY']), patch.object(module, 'run', **kwargs), patch.object(module, 'identity', return_value='hash'), contextlib.redirect_stdout(io.StringIO()):
                module.main()
            row = self.state()['events'][-1]
            self.assertEqual((row['status'], row['error']), (status, error))
        self.assertNotIn('CANARY', (u.root() / 'state.json').read_text())

    def test_lock_timeout_and_broken_pipe(self):
        self.enabled()
        with u.directory() as fd, u.locked(fd):
            started = time.monotonic()
            with self.assertRaises(TimeoutError): u.append(event(), self.state()['generation'])
            self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(u.classify(BrokenPipeError()), 'broken_pipe')

    def test_unknown_host_and_packaged_sibling_parity(self):
        self.enabled()
        self.assertEqual(self.run_cli('ad_research.py', 'provider-check').returncode, 0)
        self.assertEqual(self.state()['events'][-1]['declared_host'], 'unknown')
        helpers = []
        for name in ('ad_research.py', 'research_brief.py', 'agent_reach_public.py'):
            source = (SCRIPTS / name).read_text()
            helpers.append(source[source.index('@contextmanager'):source.index('def main(')])
        self.assertEqual(helpers[0], helpers[1]); self.assertEqual(helpers[0], helpers[2])

    def test_purge_cleans_orphans_corrupt_old_lock_and_empty_state_directory(self):
        self.enabled()
        temp = u.root() / ('.write-' + uuid.uuid4().hex)
        temp.write_text('STALE_OPERATIONAL_SNAPSHOT'); temp.chmod(0o600)
        lock = u.root() / 'store.lock'; os.mkfifo(lock, 0o600)
        state = u.root() / 'state.json'; state.unlink(); state.mkdir()
        u.control('purge')
        self.assertFalse(temp.exists())
        self.assertEqual(self.state()['events'], [])
        self.assertFalse(self.state()['enabled'])
    def test_clock_correction_prunes_future_without_losing_usable_store(self):
        generation = self.enabled()
        future = dict(event(), day='2999-01-01')
        with self.assertRaises(ValueError): u.append(future, generation)
        with u.directory() as fd:
            state = u.read(fd); state['events'] = [future, event()]; u.write(fd, state)
        self.assertEqual(sum(g['invocations'] for g in u.control('report')['groups']), 1)
        self.assertEqual(len(self.state()['events']), 1)
    def test_loader_never_reads_bytecode_or_writes_cache_even_enabled(self):
        self.enabled()
        dest = self.home / 'package'; scripts = dest / 'scripts'; scripts.mkdir(parents=True)
        (dest / '.claude-plugin').mkdir()
        (dest / '.claude-plugin/plugin.json').write_text('{"version":"0.5.0"}')
        for name in ('ad_research.py', 'usage_telemetry.py'): shutil.copy(SCRIPTS / name, scripts / name)
        result = subprocess.run([sys.executable, '-I', str(scripts / 'ad_research.py'), 'provider-check'], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(self.state()['events']), 1)
        self.assertFalse((scripts / '__pycache__').exists())
    def test_broker_does_not_even_execute_sibling_import(self):
        dest = self.home / 'broker'; dest.mkdir()
        shutil.copy(SCRIPTS / 'agent_reach_public.py', dest / 'agent_reach_public.py')
        marker = self.home / 'loaded'
        (dest / 'usage_telemetry.py').write_text('from pathlib import Path; Path('+repr(str(marker))+').touch()')
        result = subprocess.run([sys.executable, '-I', str(dest / 'agent_reach_public.py'), '--http'], input='{}', text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(marker.exists())
    def test_outcome_bookkeeping_cannot_fail_research(self):
        spec = importlib.util.spec_from_file_location('core_short', SCRIPTS / 'ad_research.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.enabled()
        for payload in ({}, {'records': 'not_a_count'}):
            with patch.object(module, 'export', return_value=payload), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
                code = module.main(['export', '--client', 'a', '--account', 'b', '--run', 'c', '--output', str(self.home)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue()), payload)
            self.assertEqual(err.getvalue(), '')
    def test_operation_choices_and_manifests_match_both_hosts(self):
        spec = importlib.util.spec_from_file_location('reach_ops', SCRIPTS / 'agent_reach_public.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.assertTrue(set(module.OPERATIONS).issubset(u.OPERATIONS))
        claude = json.loads((SCRIPTS.parent / '.claude-plugin/plugin.json').read_text())
        codex = json.loads((SCRIPTS.parent / '.codex-plugin/plugin.json').read_text())
        self.assertEqual(claude['version'], codex['version'])


if __name__ == '__main__':
    unittest.main()
