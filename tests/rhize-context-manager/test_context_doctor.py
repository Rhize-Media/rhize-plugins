"""Contract tests use isolated processes/files; no live credentials or services."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
import tempfile
from datetime import timedelta
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
import context_doctor as doctor


class DoctorContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.spec = {'id': 'test', 'kind': 'http', 'required': True,
                     'timeout_seconds': 0.2, 'params': {'url': 'http://127.0.0.1:9/health'}}
        self.context = {'run_id': '00000000-0000-4000-8000-000000000001',
                        'config_digest': 'a' * 64, 'repo': str(self.root),
                        'home': str(self.root), 'window_start': doctor.utc_now()}

    def tearDown(self):
        self.tmp.cleanup()

    def worker(self, body):
        path = self.root / 'worker.py'
        path.write_text('import json,sys,time,os\nr=json.load(sys.stdin)\n' + body)
        return [sys.executable, str(path)]

    def collect(self, body):
        return doctor.collect_probe(self.spec, self.context, self.worker(body))

    def test_missing_executable_is_not_run(self):
        row = doctor.collect_probe(self.spec, self.context, [str(self.root / 'missing')])
        self.assertEqual((row['outcome'], row['reason']), ('NOT_RUN', 'missing_executable'))

    def test_timeout_is_not_run(self):
        row = self.collect('time.sleep(20)\n')
        self.assertEqual((row['outcome'], row['reason']), ('NOT_RUN', 'timeout'))

    def test_malformed_and_nonzero_never_pass(self):
        for body, reason in [("print('not json')\n", 'malformed_output'),
                             ("print('secret-token');sys.exit(7)\n", 'nonzero_exit')]:
            row = self.collect(body)
            self.assertEqual((row['outcome'], row['reason']), ('NOT_RUN', reason))
            self.assertNotIn('secret-token', json.dumps(row))

    def test_replayed_identity_and_future_measurement_are_rejected(self):
        base = "p=r['context'];o={'run_id':p['run_id'],'probe_id':r['spec']['id'],'config_digest':p['config_digest'],'observed_at':r['requested_at'],'outcome':'OK','reason':'measured','facts':{}}\n"
        for mutation in ["o['run_id']='old-run'", "o['config_digest']='old-config'",
                         "o['probe_id']='wrong'", "o['observed_at']='2099-01-01T00:00:00+00:00'",
                         "o['observed_at']='2000-01-01T00:00:00+00:00'",
                         "o['extra']='secret-token'", "o['outcome']='healthy'"]:
            row = self.collect(base + mutation + '\nprint(json.dumps(o))\n')
            self.assertEqual(row['outcome'], 'NOT_RUN', mutation)
        self.assertEqual(self.collect(base + 'print(json.dumps(o))\n')['outcome'], 'OK')

    def test_problems_and_incomplete_coverage_coexist(self):
        rows = [{'probe_id':'a','required':True,'outcome':'PROBLEM','reason':'stale'},
                {'probe_id':'b','required':True,'outcome':'NOT_RUN','reason':'blocked_credential'}]
        self.assertEqual(doctor.summarize(rows)['headline'], 'Problems detected; coverage incomplete')
        rows[0]['outcome'] = 'OK'
        self.assertEqual(doctor.summarize(rows)['headline'], 'Coverage incomplete')

    def test_optional_omission_is_visible(self):
        rows = [{'probe_id':'a','required':True,'outcome':'OK','reason':'measured'},
                {'probe_id':'b','required':False,'outcome':'NOT_RUN','reason':'unsupported'}]
        summary = doctor.summarize(rows)
        self.assertEqual(summary['headline'], 'Required checks passed; optional coverage incomplete')
        self.assertEqual(summary['optional_not_run'], 1)

    def test_private_atomic_write(self):
        path = self.root / 'private' / 'result.json'
        doctor.atomic_json(path, {'ok':True})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(json.loads(path.read_text()), {'ok':True})

    def test_watchdog_sees_killed_attempt_without_completion(self):
        state = self.root / 'state'
        doctor.atomic_json(state / self.context['run_id'] / 'started.json',
                           {'schema_version':1, 'run_id':self.context['run_id'],
                            'started_at':'2000-01-01T00:00:00+00:00'})
        result = doctor.watch(state, max_age_hours=192, max_runtime_seconds=2)
        self.assertEqual(result['outcome'], 'PROBLEM')
        self.assertIn('unfinished_run', result['reasons'])
        self.assertIn('missing_completion', result['reasons'])

    def test_auth_failure_is_structured_and_secret_free(self):
        from context_doctor_probes import credential_expiry
        row = credential_expiry(self.root, lambda argv: (1, b'secret-token'))
        self.assertEqual(row[0:2], ('NOT_RUN', 'blocked_credential'))
        self.assertNotIn('secret-token', json.dumps(row))

    def test_explicit_rtk_input_wins_without_ambient_path(self):
        from context_doctor_probes import cli
        binary=self.root/'rtk'; binary.write_text('#!/bin/sh\necho fixture-rtk\n'); binary.chmod(0o700)
        with patch.dict(os.environ,{'PATH':'/nonexistent'}):
            self.assertEqual(cli(self.root,'rtk',['--version'],executable=str(binary)),(0,b'fixture-rtk\n'))
            with self.assertRaises(FileNotFoundError):cli(self.root,'rtk',['--version'])

    def valid_report(self):
        body = "p=r['context'];print(json.dumps({'run_id':p['run_id'],'probe_id':r['spec']['id'],'config_digest':p['config_digest'],'observed_at':r['requested_at'],'outcome':'OK','reason':'measured','facts':{}}))\n"
        config = {'schema_version':1, 'probes':[self.spec]}
        self.context['config_digest'] = doctor.digest(config)
        start = doctor.utc_now()
        row = self.collect(body)
        return {'schema_version':1, 'run_id':self.context['run_id'], 'status':'completed',
                'started_at':start, 'completed_at':doctor.utc_now(), 'repo':str(self.root),
                'config':config, 'config_digest':doctor.digest(config), 'source_digest':'b'*64,
                'probes':[row], 'summary':doctor.summarize([row]),
                'delta':{'baseline_run_id':None, 'baseline_digest':None, 'status':'no_compatible_baseline','changes':[]},
                'procedure_run_id':None, 'monitor':{'status':'disabled'}}

    def test_report_rejects_missing_duplicate_mandatory_and_forged_headline(self):
        report = self.valid_report()
        doctor.validate_report(report)
        mutations = [lambda r:r.update(probes=[]), lambda r:r['probes'].append(r['probes'][0]),
                     lambda r:r['probes'][0].update(required=False),
                     lambda r:r['summary'].update(headline='All healthy'),
                     lambda r:r['probes'][0].update(exit_code=7),
                     lambda r:r.update(schema_version=True)]
        for mutate in mutations:
            modified = copy.deepcopy(report)
            mutate(modified)
            with self.assertRaises(ValueError):
                doctor.validate_report(modified)

    def test_prior_report_cannot_cross_config_scope_or_revision(self):
        report = self.valid_report()
        state = self.root / 'state'
        doctor.atomic_json(state / report['run_id'] / 'report.json', report)
        for config, revision, repo in [('x','b'*64,str(self.root)),
                                       (report['config_digest'],'x',str(self.root)),
                                       (report['config_digest'],'b'*64,'another-repo')]:
            self.assertIsNone(doctor.prior_report(state, config, revision, repo, doctor.utc_now()))
        self.assertIsNotNone(doctor.prior_report(state, report['config_digest'], 'b'*64, str(self.root), doctor.utc_now()))

    def test_fresh_failed_assessment_counts_as_completion(self):
        report = self.valid_report()
        report['probes'][0].update(outcome='PROBLEM', reason='capture_stale')
        report['summary'] = doctor.summarize(report['probes'])
        state = self.root / 'state'
        doctor.atomic_json(state / report['run_id'] / 'started.json',
                           {k:report[k] for k in ('schema_version','run_id','started_at')})
        doctor.atomic_json(state / report['run_id'] / 'report.json', report)
        self.assertEqual(doctor.watch(state, 192, 600)['outcome'], 'OK')

    def test_expired_optional_and_empty_mandatory_config_refuse(self):
        spec = copy.deepcopy(self.spec)
        spec.update(required=False, owner='test', review_by='2000-01-01T00:00:00Z')
        with self.assertRaises(ValueError):
            doctor.validate_config({'schema_version':1,'probes':[spec]})
        with self.assertRaises(ValueError):
            doctor.validate_config({'schema_version':1,'probes':[]})

    def test_cli_persists_not_run_and_rejects_manual_render_rewrite(self):
        config = self.root / 'config.json'
        spec = dict(self.spec, kind='harness', params={})
        config.write_text(json.dumps({'schema_version':1,'probes':[spec]}))
        state = self.root / 'state'
        result = subprocess.run([sys.executable,str(SCRIPTS/'context_doctor.py'),'run',
                    '--repo',str(self.root),'--home',str(self.root),'--state-dir',str(state),
                    '--config',str(config)],capture_output=True,text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('Coverage incomplete',result.stdout)
        files = list(state.glob('*/report.json'))
        self.assertEqual(len(files),1)
        report = doctor.validate_report(json.loads(files[0].read_text()))
        self.assertEqual(report['probes'][0]['outcome'],'NOT_RUN')
        self.assertEqual(report['monitor']['status'],'disabled')

    def test_real_parent_kill_leaves_unfinished_attempt(self):
        binary = self.root / '.local/share/mise/shims/rtk'
        binary.parent.mkdir(parents=True)
        marker = self.root / 'child-parent'
        binary.write_text('#!'+sys.executable+'\nimport os,time,pathlib\npathlib.Path('+repr(str(marker))+').write_text(str(os.getppid()))\ntime.sleep(20)\n')
        binary.chmod(0o700)
        config = self.root / 'config.json'
        config.write_text(json.dumps({'schema_version':1,'probes':[dict(self.spec,kind='rtk',timeout_seconds=10,params={})]}))
        state = self.root / 'state'
        process = subprocess.Popen([sys.executable,str(SCRIPTS/'context_doctor.py'),'run',
                   '--repo',str(self.root),'--home',str(self.root),'--state-dir',str(state),
                   '--config',str(config)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+5
            while not marker.exists() and time.monotonic()<deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists())
            process.kill(); process.wait(timeout=2)
            self.assertEqual(list(state.glob('*/report.json')),[])
            self.assertIn('unfinished_run',doctor.watch(state,192,0)['reasons'])
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
            if marker.exists():
                try: os.killpg(int(marker.read_text()),signal.SIGKILL)
                except ProcessLookupError: pass

    def test_capture_does_not_turn_stale_health_into_continuous_failure(self):
        import sqlite3
        from context_doctor_probes import capture
        directory=self.root/'.claude-mem';directory.mkdir()
        now=doctor.timestamp(doctor.utc_now())
        old=now-timedelta(days=3)
        (directory/'observer-health.json').write_text(json.dumps({'consecutiveFailures':0,
                 'lastSuccessAt':int(old.timestamp()*1000),'lastErrorAt':None,'failingSinceAt':None}))
        with sqlite3.connect(directory/'claude-mem.db') as conn:
            conn.execute('CREATE TABLE observations (created_at_epoch INTEGER)')
            conn.execute('CREATE TABLE sdk_sessions (started_at_epoch INTEGER)')
            conn.execute('INSERT INTO observations VALUES (?)',(int(now.timestamp()*1000),))
            conn.execute('INSERT INTO sdk_sessions VALUES (?)',(int(now.timestamp()*1000),))
        outcome,reason,facts=capture(self.root,(old-timedelta(days=1)).isoformat())
        self.assertEqual((outcome,reason),('PROBLEM','capture_telemetry_stale'))
        self.assertEqual(facts['consecutive_failures'],0)

    def test_no_sessions_is_unknown_not_healthy(self):
        import sqlite3
        from context_doctor_probes import capture
        directory=self.root/'.claude-mem';directory.mkdir()
        (directory/'observer-health.json').write_text(json.dumps({'consecutiveFailures':0}))
        with sqlite3.connect(directory/'claude-mem.db') as conn:
            conn.execute('CREATE TABLE observations (created_at_epoch INTEGER)')
            conn.execute('CREATE TABLE sdk_sessions (started_at_epoch INTEGER)')
        self.assertEqual(capture(self.root,doctor.utc_now())[:2],('NOT_RUN','no_sessions_in_window'))

    def test_refreshable_access_expiry_is_not_claimed_login_expiry(self):
        from context_doctor_probes import credential_expiry
        outcome,reason,facts=credential_expiry(self.root,lambda argv:(0,json.dumps({'claudeAiOauth':
                    {'expiresAt':1,'refreshToken':'secret-token'}}).encode()))
        self.assertEqual((outcome,reason),('NOT_RUN','refresh_expiry_unknown'))
        self.assertNotIn('secret-token',json.dumps(facts))

    def test_nonstring_timestamps_are_malformed_not_crashes(self):
        base="p=r['context'];o={'run_id':p['run_id'],'probe_id':r['spec']['id'],'config_digest':p['config_digest'],'observed_at':None,'outcome':'OK','reason':'measured','facts':{}}\n"
        for value in (None, 3, [], {}):
            row=self.collect(base+'o["observed_at"]='+repr(value)+'\nprint(json.dumps(o))\n')
            self.assertEqual((row['outcome'],row['reason']),('NOT_RUN','malformed_output'))

    def test_nonlocal_url_never_reaches_opener(self):
        from context_doctor_probes import probe, NoRedirect
        spec=dict(self.spec,params={'url':'http://127.0.0.1:80@external.example/health'})
        with patch('context_doctor_probes.urllib.request.build_opener') as opener:
            self.assertEqual(probe(spec,self.context)[:2],('NOT_RUN','nonlocal_probe_refused'))
            opener.assert_not_called()
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://external.example'))

    def test_socket_permission_denial_is_missing_coverage(self):
        import urllib.error
        from context_doctor_probes import probe
        with patch('context_doctor_probes.urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=urllib.error.URLError(PermissionError('sandbox denied'))
            self.assertEqual(probe(self.spec,self.context)[:2],('NOT_RUN','permission_denied'))

    def test_invalid_capture_age_cannot_disable_staleness_detection(self):
        for value in (-1,0,True,float('nan'),float('inf'),'24'):
            spec=dict(self.spec,kind='claude_mem',params={'maximum_age_hours':value})
            with self.assertRaises(ValueError):
                doctor.validate_config({'schema_version':1,'probes':[spec]})

    def test_delta_requires_bound_compatible_baseline(self):
        previous=self.valid_report()
        current=self.valid_report()
        current['delta']=doctor.report_delta(previous,current['probes'])
        self.assertIn('unchanged',doctor.render(current,previous))
        with self.assertRaises(ValueError):doctor.render(current)
        altered=copy.deepcopy(previous);altered['probes'][0]['reason']='something_else'
        with self.assertRaises(ValueError):doctor.render(current,altered)
        current['delta']['status']='changed'
        with self.assertRaises(ValueError):doctor.render(current,previous)

    def test_watchdog_rejects_other_scope_and_configuration(self):
        report=self.valid_report();state=self.root/'state'
        doctor.atomic_json(state/report['run_id']/'started.json',{k:report[k] for k in ('schema_version','run_id','started_at')})
        doctor.atomic_json(state/report['run_id']/'report.json',report)
        self.assertIn('scope_mismatch',doctor.watch(state,192,600,'/other',report['config_digest'])['reasons'])
        self.assertIn('config_mismatch',doctor.watch(state,192,600,str(self.root),'other')['reasons'])

    def test_watchdog_recovers_with_fresh_config_after_release(self):
        state=self.root/'state'; old=self.valid_report()
        doctor.atomic_json(state/'old'/'started.json', {'run_id':old['run_id'],'started_at':old['started_at']})
        doctor.atomic_json(state/'old'/'report.json', old)
        self.spec['timeout_seconds']=0.3
        current=self.valid_report()
        doctor.atomic_json(state/'current'/'started.json', {'run_id':current['run_id'],'started_at':current['started_at']})
        doctor.atomic_json(state/'current'/'report.json', current)
        self.assertEqual(doctor.watch(state,192,600,str(self.root),current['config_digest'])['outcome'],'OK')

    def test_malformed_historical_uuid_is_rejected_without_crashing_selection(self):
        state=self.root/'state'; report=self.valid_report(); report['run_id']=17
        doctor.atomic_json(state/'bad'/'report.json',report)
        self.assertIsNone(doctor.prior_report(state,report['config_digest'],report['source_digest'],report['repo'],doctor.utc_now()))
        report=self.valid_report(); report['delta']={'baseline_run_id':17,'baseline_digest':'a'*64,'status':'unchanged','changes':[]}
        with self.assertRaises(ValueError):doctor.validate_report(report)

    def test_sentry_signal_uses_same_checkin_identity_and_no_report_content(self):
        from context_doctor_monitor import check_in
        config=self.root/'monitor.json'
        config.write_text(json.dumps({'organization':'example','monitor_slug':'test',
                           'environment':'test','keychain_service':'test-dsn'}))
        with patch('context_doctor_monitor.subprocess.run') as keychain, patch('context_doctor_monitor.urllib.request.urlopen') as send:
            keychain.return_value=subprocess.CompletedProcess([],0,stdout=b'https://public@o123.ingest.us.sentry.io/456',stderr=b'')
            send.return_value.__enter__.return_value.status=200
            for status in ('in_progress','ok'):
                self.assertEqual(check_in(config,self.context['run_id'],status)['status'],'accepted')
            payloads=[json.loads(call.args[0].data.splitlines()[2]) for call in send.call_args_list]
            self.assertEqual(payloads[0]['check_in_id'],payloads[1]['check_in_id'])
            self.assertEqual(set(payloads[0]),{'check_in_id','monitor_slug','status','environment'})
            self.assertNotIn(str(self.root),str(payloads))

    def test_monitor_failure_is_visible_and_secret_free(self):
        from context_doctor_monitor import check_in
        config=self.root/'monitor.json'
        config.write_text(json.dumps({'organization':'example','monitor_slug':'test',
                           'environment':'test','keychain_service':'test-dsn'}))
        with patch('context_doctor_monitor.subprocess.run') as keychain:
            keychain.return_value=subprocess.CompletedProcess([],1,stdout=b'secret-value',stderr=b'')
            outcome=check_in(config,self.context['run_id'],'ok')
            self.assertEqual(outcome['status'],'failed')
            self.assertNotIn('secret-value',json.dumps(outcome))


if __name__ == '__main__':
    unittest.main()
