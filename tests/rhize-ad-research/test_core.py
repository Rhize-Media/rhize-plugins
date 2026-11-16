import contextlib
import copy
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'rhize-ad-research/scripts/ad_research.py'
spec = importlib.util.spec_from_file_location('ad_research', SCRIPT)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.old_root = core.ROOT
        core.ROOT = self.root / 'registry'
        self.scope = ['--client','tag','--account','rhize']
        self.invoke('setup', *self.scope, '--workspace', str(self.root/'workspace'))
    def tearDown(self):
        core.ROOT = self.old_root
        self.tmp.cleanup()
    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = core.main(list(args))
        return code, json.loads(out.getvalue() or err.getvalue())
    def plan(self, *extra):
        code, run = self.invoke('plan', *self.scope, '--host','codex','--service','detailing','--search-terms','mobile detailing','--limit','5', *extra)
        self.assertEqual(code, 0)
        return run
    def envelope(self, run, ads=None, total=50):
        return {'provider':core.PROVIDER,'tool':core.TOOL,'request':run['input'],
                'run_id':run['id'],'input_hash':run['input_hash'],'capture_host':run['capture_host'],
                'capture_method':'host_transcribed','captured_at':core.now(),
                'response':{'structuredContent':{'results':json.dumps({'estimated_total_count':total,'ads':ads if ads is not None else [self.ad()]})},'isError':False}}
    def ad(self, **changes):
        return dict({'id':'1418113620529463','page_id':807611415766243,'page_name':'The Aesthetics Garage',
                     'ad_creative_link_title':'Full Detail From $195, We Come to You.',
                     'ad_creation_time':1794182190,'ad_delivery_start_time':1794187030,
                     'ad_snapshot_url':'https://www.facebook.com/ads/library/?id=1418113620529463','currency':'USD'}, **changes)
    def ingest(self, run, value):
        p=self.root/'input.json';core.write(p,value)
        return self.invoke('collect',*self.scope,'--run',run['id'],'--response',str(p))
    def directory(self, run): return core.run_path(self.root/'workspace',run['id']).parent
    def test_actual_meta_shape_and_missing_fields(self):
        run=self.plan(); code,result=self.ingest(run,self.envelope(run))
        self.assertEqual(code,0); state=result['run']
        self.assertEqual((state['normalized'],state['coverage'],state['estimated_total_count']),(1,'sample',50))
        row=core.read(self.directory(run)/'records.json')[0]
        self.assertIsNone(row['text']);self.assertIsNone(row['active_status'])
        self.assertEqual(row['title'],'Full Detail From $195, We Come to You.')
        self.assertTrue(row['start_date'].endswith('+00:00'))
        self.assertIn('no_pagination',state['coverage_reasons'])
    def test_all_supported_mcp_wrappers(self):
        for wrapper in ('raw','structured','text'):
            run=self.plan(); env=self.envelope(run)
            value=json.loads(env['response']['structuredContent']['results'])
            env['response']={'raw':value,'structured':{'results':json.dumps(value)},'text':{'content':[{'type':'text','text':json.dumps(value)}]}}[wrapper]
            self.assertEqual(self.ingest(run,env)[0],0)
    def test_duplicates_quarantine_and_no_complete_inventory(self):
        run=self.plan();ads=[self.ad(),self.ad(),self.ad(id=True),self.ad(ad_delivery_start_time='bad')]
        code,result=self.ingest(run,self.envelope(run,ads,4))
        self.assertEqual(code,0)
        self.assertEqual([result['run'][k] for k in ('normalized','duplicates','quarantined')],[1,1,2])
        self.assertIn('parse_incomplete',result['run']['coverage_reasons'])
        self.assertNotEqual(result['run']['coverage'],'complete')
    def test_zero_results_are_unverified(self):
        run=self.plan();_,r=self.ingest(run,self.envelope(run,[],0))
        self.assertEqual((r['run']['coverage'],r['run']['result']),('unknown','unverified_empty'))
        self.assertEqual(r['operator_status'],'No ads returned; absence unverified')
    def test_capped_and_estimate_mismatch(self):
        for total,reason in ((900,'capped'),(0,'estimate_mismatch')):
            run=self.plan();_,r=self.ingest(run,self.envelope(run,total=total))
            self.assertIn(reason,r['run']['coverage_reasons'])
    def test_invalid_query_bounds_and_pagination(self):
        for change in ({'limit':0},{'limit':51},{'limit':True},{'offset':2},{'countries':['USA']},{'page_ids':['../../x']}):
            query=dict(self.plan()['input'],**change)
            with self.assertRaises(core.Blocked):core.query_validate(query)
    def test_wrong_query_provider_and_tool_fail_closed(self):
        for field in ('request','provider','tool'):
            run=self.plan();env=self.envelope(run)
            env[field]={'search_terms':'different'} if field=='request' else 'other'
            self.assertEqual(self.ingest(run,env)[0],2)
            self.assertTrue((self.directory(run)/'response.json').exists())
            self.assertFalse((self.directory(run)/'records.json').exists())
    def test_errors_malformed_and_oversized_response(self):
        for response in ({'isError':True,'content':[]},{'results':'not json'},{'ads':[], 'estimated_total_count':False},{'ads':[self.ad()]*6,'estimated_total_count':6},{'content':[3]}):
            run=self.plan();env=self.envelope(run);env['response']=response
            self.assertEqual(self.ingest(run,env)[0],2)
        path=self.root/'huge';path.write_text('x'*(core.MAX_RESPONSE+1))
        with self.assertRaisesRegex(core.Blocked,'response_too_large'):core.read(path)
    def test_resume_does_not_call_provider_or_duplicate(self):
        run=self.plan();_,request=self.invoke('collect',*self.scope,'--run',run['id'])
        self.assertEqual(request['request'],run['input'])
        core.write(Path(request['inbox_path']),self.envelope(run))
        _,first=self.invoke('resume',*self.scope,'--run',run['id'],'--response',request['inbox_path'])
        before=(self.directory(run)/'records.json').read_bytes()
        _,second=self.invoke('resume',*self.scope,'--run',run['id'])
        self.assertEqual(first['run'],second['run']);self.assertEqual(before,(self.directory(run)/'records.json').read_bytes())
    def test_interruption_after_raw_write_recovers(self):
        run=self.plan();original=core.write
        def interrupted(path,value):
            if Path(path).name=='records.json':raise OSError('interrupted')
            return original(path,value)
        with patch.object(core,'write',side_effect=interrupted):self.assertEqual(self.ingest(run,self.envelope(run))[0],2)
        self.assertTrue((self.directory(run)/'response.json').exists())
        code,r=self.invoke('resume',*self.scope,'--run',run['id'])
        self.assertEqual((code,r['run']['normalized']),(0,1))
    def test_response_is_immutable_and_hash_checked(self):
        run=self.plan();env=self.envelope(run);self.ingest(run,env)
        other=copy.deepcopy(env);other['response']['isError']=True
        self.assertEqual(self.ingest(run,other)[1]['error'],'immutable_response_conflict')
        core.write(self.directory(run)/'response.json',other)
        self.assertEqual(self.invoke('resume',*self.scope,'--run',run['id'])[1]['error'],'evidence_changed:response.json')
    def test_missing_terminal_evidence_never_reopens(self):
        for name in ('response.json','records.json'):
            run=self.plan();self.ingest(run,self.envelope(run))
            (self.directory(run)/name).unlink()
            before=(self.directory(run)/'manifest.json').read_bytes()
            for command in ('resume','status','export'):
                extra=['--output',str(self.root/'out')] if command=='export' else []
                self.assertEqual(self.invoke(command,*self.scope,'--run',run['id'],*extra)[1]['error'],'evidence_missing:'+name)
            self.assertEqual(before,(self.directory(run)/'manifest.json').read_bytes())
    def test_record_tampering_blocks_export_status_resume(self):
        run=self.plan();self.ingest(run,self.envelope(run))
        core.write(self.directory(run)/'records.json',[{'ad_id':'999'}])
        for command in ('resume','status','export'):
            extra=['--output',str(self.root/'out')] if command=='export' else []
            self.assertEqual(self.invoke(command,*self.scope,'--run',run['id'],*extra)[1]['error'],'evidence_changed:records.json')
    def test_capture_binding_and_schema_drift(self):
        for field,value,reason in (('run_id','wrong','response_run_mismatch'),('input_hash','wrong','response_run_mismatch'),('capture_host','claude','response_host_mismatch'),('captured_at','2020-01-01T00:00:00Z','invalid_capture_time'),('capture_method','invented','invalid_capture_method')):
            run=self.plan();env=self.envelope(run);env[field]=value
            self.assertEqual(self.ingest(run,env)[1]['error'],reason)
        for extra,reason in (({'cursor':'abc'},'unexpected_pagination'),({'new_field':1},'response_schema_drift')):
            run=self.plan();env=self.envelope(run);env['response']={'ads':[],'estimated_total_count':0,**extra}
            self.assertEqual(self.ingest(run,env)[1]['error'],reason)
    def test_failed_capture_is_sealed_and_not_reparsed(self):
        run=self.plan();env=self.envelope(run);env['response']={'isError':True}
        self.assertEqual(self.ingest(run,env)[1]['error'],'provider_error')
        manifest=core.read(self.directory(run)/'manifest.json')
        self.assertEqual(manifest['response_hash'],core.digest(env))
        self.assertEqual(self.invoke('resume',*self.scope,'--run',run['id'])[1]['run']['block_reason'],'provider_error')
        self.assertEqual(self.invoke('export',*self.scope,'--run',run['id'],'--output',str(self.root/'out'))[1]['error'],'no_exportable_sample')
    def test_all_quarantined_held_and_mixed_partial(self):
        run=self.plan();_,result=self.ingest(run,self.envelope(run,[self.ad(id=True)]))
        self.assertEqual((result['run']['lifecycle'],result['operator_status']),('failed','Held: all_quarantined'))
        run=self.plan();_,result=self.ingest(run,self.envelope(run,[self.ad(),self.ad(id=True)]))
        self.assertEqual(result['operator_status'],'Partial sample collected')
    def test_duplicate_json_keys_and_unsealed_file_rejected(self):
        with self.assertRaisesRegex(core.Blocked,'duplicate_json_key'):core.decode('{"ads":[],"ads":[]}')
        run=self.plan();core.write(self.directory(run)/'response.json',self.envelope(run))
        self.assertEqual(self.invoke('resume',*self.scope,'--run',run['id'])[1]['error'],'unsealed_response')
    def test_crash_after_records_before_terminal_manifest_recovers(self):
        run=self.plan();original=core.save_run
        def interrupted(workspace,value):
            if value['lifecycle']=='succeeded':raise OSError('interrupted')
            return original(workspace,value)
        with patch.object(core,'save_run',side_effect=interrupted):self.assertEqual(self.ingest(run,self.envelope(run))[0],2)
        before=(self.directory(run)/'records.json').read_bytes()
        code,result=self.invoke('resume',*self.scope,'--run',run['id'])
        self.assertEqual((code,result['run']['lifecycle']),(0,'succeeded'))
        self.assertEqual(before,(self.directory(run)/'records.json').read_bytes())
    def test_scope_binding_and_workspace_ownership(self):
        self.assertEqual(self.invoke('setup','--client','other','--account','rhize','--workspace',str(self.root/'workspace'))[0],2)
        run=self.plan();run['client']='other';core.save_run(self.root/'workspace',run)
        for cmd in ('collect','resume','status','export'):
            extra=['--output',str(self.root/'out')] if cmd=='export' else []
            self.assertEqual(self.invoke(cmd,*self.scope,'--run',run['id'],*extra)[1]['error'],'run_scope_mismatch')
    def test_page_filter_mismatch_is_quarantined(self):
        run=self.plan('--page-ids','123');_,r=self.ingest(run,self.envelope(run))
        self.assertEqual(r['run']['quarantined'],1)
    def test_csv_formula_and_safe_snapshot_link(self):
        run=self.plan();self.ingest(run,self.envelope(run,[self.ad(page_name='=evil',ad_creative_body=' +cmd',ad_snapshot_url='https://evil.test/?access_token=secret')]))
        code,_=self.invoke('export',*self.scope,'--run',run['id'],'--output',str(self.root/'out'))
        self.assertEqual(code,0)
        csv=(self.root/'out'/(run['id']+'-research.csv')).read_text()
        self.assertIn("'=evil",csv);self.assertIn("' +cmd",csv);self.assertNotIn('secret',csv)
    def test_legacy_evidence_and_ledger_remain_readable_unchanged(self):
        run=self.plan();run.pop('provider');run.update(lifecycle='succeeded',billing='reconciled',actual_charge_usd='0.0058')
        core.save_run(self.root/'workspace',run);core.write(self.directory(run)/'records.json',[])
        ledger=core.ROOT/(core.key('tag','rhize')+'.json');core.write(ledger,{'runs':{run['id']:{'actual_charge_usd':'0.0058'}}});before=ledger.read_bytes()
        for command in ('collect','resume'):self.assertEqual(self.invoke(command,*self.scope,'--run',run['id'])[1]['error'],'legacy_provider_retired_read_only')
        self.assertEqual(self.invoke('status',*self.scope,'--run',run['id'])[0],0)
        self.assertEqual(self.invoke('export',*self.scope,'--run',run['id'],'--output',str(self.root/'out'))[0],0)
        self.assertEqual(before,ledger.read_bytes())
    def test_symlink_traversal_and_concurrency(self):
        (self.root/'alias').symlink_to(self.root/'target')
        with self.assertRaises(core.Blocked):core.safe_dir(self.root/'alias'/'child')
        with self.assertRaises(core.Blocked):core.ident('../secret')
        with core.Lock('tag','rhize'):
            with self.assertRaisesRegex(core.Blocked,'active_collector'):
                with core.Lock('tag','rhize'):pass
    def test_noncontrolled_exceptions_are_redacted(self):
        with patch.object(core,'mapping',side_effect=ValueError('token=secret')):
            code,error=self.invoke('doctor',*self.scope)
        self.assertEqual(code,2);self.assertNotIn('secret',json.dumps(error))
    def test_meta_tool_guard_is_search_only_without_granting_permission(self):
        script=SCRIPT.with_name('meta_tool_guard.py')
        for name,blocked in (('mcp__meta-ads__ads_library_search',False),('mcp__meta_ads__ads_library_search',False),('mcp__meta-ads__ads_create_campaign',True),('mcp__meta-ads__ads_get_ad_accounts',True),('mcp__meta-ads__ads_delete__ads_library_search',True),('mcp__other__read',False)):
            result=subprocess.run([sys.executable,str(script)],input=json.dumps({'tool_name':name}),text=True,capture_output=True,check=True)
            if blocked:self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'],'deny')
            else:self.assertEqual(result.stdout,'')
    def test_response_and_export_symlinks_rejected(self):
        run=self.plan();source=self.root/'source.json';core.write(source,self.envelope(run))
        link=self.root/'link.json';link.symlink_to(source)
        self.assertEqual(self.invoke('resume',*self.scope,'--run',run['id'],'--response',str(link))[1]['error'],'Symlink files are not supported')
        self.ingest(run,core.read(source));out=self.root/'out';out.mkdir()
        (out/(run['id']+'-research.csv')).symlink_to(self.root/'victim')
        self.assertEqual(self.invoke('export',*self.scope,'--run',run['id'],'--output',str(out))[1]['error'],'Symlink files are not supported')
    def test_missing_workspace_is_not_recreated(self):
        self.plan();workspace=self.root/'workspace';workspace.rename(self.root/'moved')
        for command in ('doctor','list'):
            self.assertEqual(self.invoke(command,*self.scope)[1]['error'],'workspace_missing')
        self.assertFalse(workspace.exists())
    def test_capture_utc_z_and_transcription_wrappers(self):
        for wrapper in ('object','null'):
            run=self.plan();env=self.envelope(run);env['captured_at']=core.now().replace('+00:00','Z')
            value=json.loads(env['response']['structuredContent']['results'])
            env['response']={'structuredContent':{'results':value}} if wrapper=='object' else {'structuredContent':None,'content':[{'type':'text','text':json.dumps(value)}]}
            self.assertEqual(self.ingest(run,env)[0],0)
    def test_lone_surrogate_quarantines_instead_of_sticking(self):
        run=self.plan();code,result=self.ingest(run,self.envelope(run,[self.ad(ad_creative_body=chr(0xd83d))]))
        self.assertEqual((code,result['run']['result']),(0,'all_quarantined'))
    def test_capturing_status_does_not_suggest_provider_call(self):
        run=self.plan();run['lifecycle']='capturing'
        self.assertEqual(core.operator_status(run)[0],'Response sealed; processing incomplete')
        self.assertIn('without a provider call',core.operator_status(run)[1])
    def test_case_alias_overlap_uses_directory_identity(self):
        first=self.root/'one';second=self.root/'two';first.mkdir();second.mkdir()
        with patch.object(core.os.path,'samefile',return_value=True):
            self.assertTrue(core.workspaces_overlap(first,second))
    def test_legacy_nonterminal_is_inspect_only(self):
        run={'lifecycle':'running'}
        self.assertIn('inspect retained files only',core.operator_status(run)[1])
    def test_captured_native_host_fixtures(self):
        for host in ('claude','codex'):
            run=self.plan('--host',host,'--page-ids','807611415766243');env=self.envelope(run)
            env['response']=json.loads((Path(__file__).parent/'fixtures'/('meta-'+host+'.json')).read_text())
            code,result=self.ingest(run,env)
            self.assertEqual((code,result['run']['normalized']),(0,4))
            ids={row['ad_id'] for row in core.read(self.directory(run)/'records.json')}
            self.assertEqual(ids,{'28924778817173958','1418113620529463','4803258856623755','1451717590384988'})
    def test_captured_legacy_manifest_exports_without_mutation(self):
        run=json.loads((Path(__file__).parent/'fixtures/legacy-manifest.json').read_text())
        core.save_run(self.root/'workspace',run);core.write(self.directory(run)/'records.json',[])
        before=(self.directory(run)/'manifest.json').read_bytes()
        code,result=self.invoke('export',*self.scope,'--run',run['id'],'--output',str(self.root/'out'))
        self.assertEqual((code,result['records'],result['coverage']),(0,0,'provider_error'))
        self.assertEqual(before,(self.directory(run)/'manifest.json').read_bytes())
    def test_local_doctor_does_not_claim_authentication(self):
        self.assertEqual(self.invoke('doctor',*self.scope)[1]['live_access'],'not_checked_by_local_doctor')
        self.assertFalse(self.invoke('provider-check')[1]['pagination_supported'])

if __name__=='__main__':unittest.main()
