import contextlib
import importlib.util
import io
import json
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
    def tearDown(self):
        core.ROOT = self.old_root
        self.tmp.cleanup()
    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = core.main(list(args))
        return code, json.loads(out.getvalue() or err.getvalue())
    def setup_client(self):
        return self.invoke('setup', '--client', 'tag', '--account', 'acct', '--workspace', str(self.root / 'workspace'))
    def test_setup_plan_and_safe_block(self):
        self.assertEqual(self.setup_client()[0], 0)
        code, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://www.facebook.com/ExamplePage', '--results-limit', '3', '--max-charge', '0.25')
        self.assertEqual(code, 0)
        self.assertEqual(run['unit_ceiling'], 3)
        code, failure = self.invoke('collect', '--client', 'tag', '--account', 'acct', '--run', run['id'])
        self.assertEqual(code, 2)
        self.assertEqual(failure['error'], 'Invalid or out-of-scope spike authority')
        self.assertEqual(core.read(core.run_path(self.root / 'workspace', run['id']))['lifecycle'], 'planned')
    def test_workspace_and_run_scope_are_bound(self):
        self.setup_client()
        code, _ = self.invoke('setup', '--client', 'other', '--account', 'acct', '--workspace', str(self.root/'workspace'))
        self.assertEqual(code, 2)
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '1', '--max-charge', '0.01')
        run['client'] = 'other'; core.save_run(self.root/'workspace', run)
        with patch.object(core.Transport, 'request') as request:
            for command in ('collect', 'resume', 'status', 'export'):
                extra = ['--output', str(self.root/'out')] if command == 'export' else []
                code, error = self.invoke(command, '--client', 'tag', '--account', 'acct', '--run', run['id'], *extra)
                self.assertEqual((code, error['error']), (2, 'run_scope_mismatch'))
            request.assert_not_called()

    def test_hostile_urls_and_ids(self):
        for url in ['https://facebook.com@evil.test/page', 'https://www.facebook.com/page?access_token=x', 'http://www.facebook.com/page', 'https://www.facebook.com/ads/library/?access_token=x']:
            with self.subTest(url=url), self.assertRaises(core.Blocked): core.validate_url(url)
        with self.assertRaises(core.Blocked): core.ident('../secret')
        self.assertEqual(core.clean_url('https://www.facebook.com/ads/library/?id=7&access_token=secret&utm_source=x'), 'https://www.facebook.com/ads/library/?id=7')
    def test_lock_prevents_concurrent_collector(self):
        with core.Lock('tag', 'acct'):
            with self.assertRaisesRegex(core.Blocked, 'active_collector'):
                with core.Lock('tag', 'acct'): pass
    def test_csv_formula_and_signed_link_redaction(self):
        self.setup_client()
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '1', '--max-charge', '1')
        run.update(lifecycle='succeeded', coverage='complete', result='nonempty'); core.save_run(self.root / 'workspace', run)
        core.write(core.run_path(self.root / 'workspace', run['id']).parent / 'records.json', [{'ad_id':'1','advertiser':'=evil','source_url':'https://example.com/?id=1&access_token=secret','text':' +cmd'}])
        code, _ = self.invoke('export', '--client', 'tag', '--account', 'acct', '--run', run['id'], '--output', str(self.root / 'out'))
        self.assertEqual(code, 0)
        result = (self.root / 'out/research.csv').read_text()
        self.assertIn("'=evil", result); self.assertIn("' +cmd", result); self.assertNotIn('secret', result)
    def test_grant_expired_and_unsupported_all_in(self):
        grant = dict(grantor='Jim', issued_at='2020-01-01T00:00:00Z', expires_at='2021-01-01T00:00:00Z', source_reference='instruction', client='tag', account='acct', cumulative_usd='1', billable_units=10, covered_cost_classes=['actor_events'], provider_use_decision='allowed', retention_decision='metadata_links_only', collector=core.pwd.getpwuid(core.os.getuid()).pw_name, mode='spike', ancillary_usd='0')
        with self.assertRaisesRegex(core.Blocked, 'expired_authority'): core.grant_validate(grant, 'tag', 'acct')
        grant['expires_at'] = '2099-01-01T00:00:00Z'; grant['covered_cost_classes'].append('all_in')
        with self.assertRaises(core.Blocked): core.grant_validate(grant, 'tag', 'acct')
    def test_pagination_resume_and_quarantine(self):
        self.setup_client()
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '100', '--max-charge', '1')
        run.update(lifecycle='succeeded', dataset_id='dataset', billing='reconciled', actual_charge_usd='0', charged_units=0, maximum_unit_price_usd='0.0058')
        workspace = self.root / 'workspace'
        core.save_run(workspace, run)
        class Fake:
            failed = False
            def request(self, method, path):
                if '/items?' not in path: return {'data': {'itemCount': 101}}
                if 'offset=0&' in path: return [{'ad_archive_id': str(i), 'page_name': 'Page'} for i in range(100)]
                if not self.failed:
                    self.failed = True
                    raise core.Blocked('interruption')
                return [{'page_name': 'Missing ID'}]
        fake = Fake()
        with self.assertRaises(core.Blocked): core.paginate(workspace, run, fake)
        run = core.read(core.run_path(workspace, run['id']))
        self.assertEqual(run['offset'], 100)
        run = core.paginate(workspace, run, fake)
        self.assertEqual((run['coverage'], run['result'], run['normalized'], run['quarantined']), ('parse_incomplete', 'nonempty', 100, 1))
    def test_complete_empty_vs_capped(self):
        self.setup_client()
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '1', '--max-charge', '1')
        run.update(lifecycle='succeeded', dataset_id='dataset', billing='reconciled', actual_charge_usd='0', charged_units=0, maximum_unit_price_usd='0.0058')
        class Fake:
            def request(self, method, path): return {'data': {'itemCount': 0}}
        run = core.paginate(self.root / 'workspace', run, Fake())
        self.assertEqual((run['coverage'], run['result']), ('unknown', 'unknown'))
    def test_lost_ack_reconciles_without_second_post(self):
        self.setup_client()
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '1', '--max-charge', '0.006')
        grant = dict(grantor='Jim', issued_at='2020-01-01T00:00:00Z', expires_at='2099-01-01T00:00:00Z', source_reference='instruction', client='tag', account='acct', cumulative_usd='10', billable_units=50, covered_cost_classes=['actor_events'], provider_use_decision='allowed', retention_decision='metadata_links_only', collector=core.pwd.getpwuid(core.os.getuid()).pw_name, mode='spike', ancillary_usd='0', spike_limit_policy={'source_reference':'provider docs','schema_hash':'schema','pricing_hash':'prices'}, usage_baseline={'usageCycle':{'startAt':'a','endAt':'b'}, 'totalUsageCreditsUsdAfterVolumeDiscount':'0'})
        data = {'grant': grant, 'runs': {}}
        class Fake:
            posts = 0
            matches = 1
            def request(self, method, path, payload=None, authenticated=True):
                if path == '/v2/users/me/usage/monthly': return {'data': grant['usage_baseline']}
                if method == 'POST': self.posts += 1; raise core.Blocked('lost acknowledgement')
                if '/acts/' in path:
                    items = [{'id': 'provider' + str(i), 'startedAt': core.now(), 'actId':core.ACTOR, 'buildId':core.BUILD, 'defaultKeyValueStoreId':'store'} for i in range(self.matches)]
                    return {'data': {'items':items,'total':len(items)}}
                if '/records/INPUT' in path:
                    return dict(run['input'], startUrls=[dict(run['input']['startUrls'][0], method='GET')])
                if '/actor-runs/' in path: return {'data': {'actId':core.ACTOR, 'buildId':core.BUILD, 'userId':'acct', 'defaultKeyValueStoreId':'store', 'options':{'maxTotalChargeUsd':'0.006','timeoutSecs':120,'memoryMbytes':1024}}}
                raise AssertionError(path)
        fake = Fake()
        check = {'authenticated_account_id':'acct', 'schema_hash':'schema', 'pricing_hash':'prices', 'minimum_published_unit_price_usd':'0.001', 'maximum_published_unit_price_usd':'0.0058', 'minimum_charge_usd':'0.0058'}
        workspace = self.root / 'workspace'
        with patch.object(core, 'provider_check', return_value=check):
            with self.assertRaisesRegex(core.Blocked, 'unresolved_submission'): core.submit_run(workspace, run, data, fake)
        run = core.read(core.run_path(workspace, run['id']))
        data = core.ledger('tag', 'acct')
        self.assertEqual(run['lifecycle'], 'submission_unknown')
        for matches in (0, 2):
            fake.matches = matches
            with self.assertRaisesRegex(core.Blocked, 'unresolved_submission'): core.reconcile_submission(workspace, run, data, fake)
        fake.matches = 1
        run = core.reconcile_submission(workspace, run, data, fake)
        self.assertEqual(run['provider_run_id'], 'provider0')
        self.assertEqual(fake.posts, 1)
        with self.assertRaises(core.Blocked): core.submit_run(workspace, run, data, fake)
    def test_unit_and_usd_overrun_block_before_post(self):
        self.setup_client()
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '1', '--max-charge', '0.05')
        grant = dict(grantor='Jim', issued_at='2020-01-01T00:00:00Z', expires_at='2099-01-01T00:00:00Z', source_reference='instruction', client='tag', account='acct', cumulative_usd='10', billable_units=50, covered_cost_classes=['actor_events'], provider_use_decision='allowed', retention_decision='metadata_links_only', collector=core.pwd.getpwuid(core.os.getuid()).pw_name, mode='spike', ancillary_usd='0', spike_limit_policy={'source_reference':'docs','schema_hash':'s','pricing_hash':'p'}, usage_baseline={'usageCycle':{'startAt':'a'},'totalUsageCreditsUsdAfterVolumeDiscount':'0'})
        check = {'authenticated_account_id':'acct','schema_hash':'s','pricing_hash':'p','minimum_published_unit_price_usd':'0.001','maximum_published_unit_price_usd':'0.0058','minimum_charge_usd':'0.0058'}
        with patch.object(core, 'provider_check', return_value=check):
            with self.assertRaisesRegex(core.Blocked, 'budget_exhausted'): core.submit_run(self.root / 'workspace', run, {'grant':grant, 'runs':{}}, object())
    def test_failed_and_cap_never_report_empty_success(self):
        self.setup_client()
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '1', '--max-charge', '0.006')
        run.update(lifecycle='failed', dataset_id='dataset', billing='reconciled', actual_charge_usd='0', charged_units=0, maximum_unit_price_usd='0.0058')
        class Fake:
            def request(self, method, path): return {'data': {'itemCount': 0}}
        run = core.paginate(self.root / 'workspace', run, Fake())
        self.assertEqual((run['coverage'], run['result']), ('pagination_incomplete', 'unknown'))
        self.assertEqual(core.operator_status(run)[0], 'Failed')
        run.update(lifecycle='succeeded', actual_charge_usd='0.006')
        run = core.paginate(self.root / 'workspace', run, Fake())
        self.assertEqual((run['coverage'], run['result']), ('unknown', 'unknown'))
        self.assertIn('capped', run['coverage_reasons'])
    def test_schema_drift_fails_closed(self):
        props = {x:{} for x in ('startUrls','resultsLimit','activeStatus','sorting','onlyTotal','includeAboutPage','isDetailsPerAd','enrichWithEcommerceData')}
        schema = {'properties':props, 'required':['startUrls']}
        tiers = {x:{'tieredEventPriceUsd':0.001} for x in ('FREE','BRONZE','SILVER','GOLD','PLATINUM','DIAMOND')}
        pricing = {'pricingModel':'PAY_PER_EVENT','startedAt':'2020-01-01T00:00:00Z','minimalMaxTotalChargeUsd':0.0058,'pricingPerEvent':{'actorChargeEvents':{'apify-default-dataset-item':{'isPrimaryEvent':True,'eventTieredPricingUsd':tiers},'ecommerce-enrichment':{}}}}
        class Fake:
            def request(self, method, path, authenticated=False):
                return {'data': {'id':core.ACTOR,'pricingInfos':[pricing]} if '/acts/' in path else {'id':core.BUILD,'actId':core.ACTOR,'buildNumber':core.BUILD_NUMBER,'inputSchema':json.dumps(schema)}}
        self.assertEqual(core.provider_check(Fake())['pricing_model'], 'PAY_PER_EVENT')
        pricing['startedAt'] = '2099-01-01T00:00:00Z'
        with self.assertRaisesRegex(core.Blocked, 'schema_change'): core.provider_check(Fake())
        pricing['startedAt'] = '2020-01-01T00:00:00Z'
        pricing['isPPEPlatformUsagePaidByUser'] = True
        with self.assertRaisesRegex(core.Blocked, 'schema_change'): core.provider_check(Fake())
        pricing['isPPEPlatformUsagePaidByUser'] = False
        del schema['properties']['enrichWithEcommerceData']
        with self.assertRaisesRegex(core.Blocked, 'schema_change'): core.provider_check(Fake())
    def test_rejection_unknown_and_successful_resume(self):
        self.setup_client()
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '2', '--max-charge', '0.006')
        grant = dict(grantor='Jim', issued_at='2020-01-01T00:00:00Z', expires_at='2099-01-01T00:00:00Z', source_reference='instruction', client='tag', account='acct', cumulative_usd='10', billable_units=50, covered_cost_classes=['actor_events'], provider_use_decision='allowed', retention_decision='metadata_links_only', collector=core.pwd.getpwuid(core.os.getuid()).pw_name, mode='spike', ancillary_usd='0.01', spike_limit_policy={'source_reference':'docs','schema_hash':'s','pricing_hash':'p'}, usage_baseline={'usageCycle':{'startAt':'a'},'totalUsageCreditsUsdAfterVolumeDiscount':'0'})
        check = {'authenticated_account_id':'acct','schema_hash':'s','pricing_hash':'p','minimum_published_unit_price_usd':'0.001','maximum_published_unit_price_usd':'0.0058','minimum_charge_usd':'0.0058'}
        class Fake:
            status = None
            posts = 0
            usage = '0'
            count = 0
            def request(self, method, path, payload=None, authenticated=True):
                if '/usage/monthly' in path: return {'data': {'usageCycle':{'startAt':'a'}, 'totalUsageCreditsUsdAfterVolumeDiscount':self.usage}}
                if method == 'POST':
                    self.posts += 1
                    if self.status: raise core.HTTPFailure(self.status)
                    return {'data':{'id':'provider' + str(self.posts),'actId':core.ACTOR,'buildId':core.BUILD,'userId':'acct'}}
                if '/actor-runs/' in path: return {'data':{'actId':core.ACTOR,'buildId':core.BUILD,'userId':'acct','status':'SUCCEEDED','usageTotalUsd':0.0058 if self.count else 0,'chargedEventCounts':{'apify-default-dataset-item':self.count} if self.count else {},'defaultDatasetId':'dataset'}}
                if '/items?' in path: return [{'ad_archive_id':'1','page_name':'Page'}]
                if '/datasets/' in path: return {'data':{'itemCount':self.count}}
                raise AssertionError(path)
        workspace = self.root / 'workspace'
        fake = Fake(); fake.status = 400
        data = {'grant':grant,'runs':{}}
        with patch.object(core, 'provider_check', return_value=check):
            with self.assertRaisesRegex(core.Blocked, 'provider_rejected_400'): core.submit_run(workspace, run, data, fake)
        self.assertEqual((data['runs'][run['id']]['billing'], data['runs'][run['id']]['actual_charge_usd']), ('reconciled', '0'))
        _, next_run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '2', '--max-charge', '0.006')
        fake.status = None; fake.usage = '0.002'
        with patch.object(core, 'provider_check', return_value=check): core.submit_run(workspace, next_run, data, fake)
        fake.count = 1
        done = core.resume_run(workspace, next_run, data, fake)
        self.assertEqual((done['lifecycle'], done['billing'], done['coverage'], done['result']), ('succeeded', 'reconciled', 'capped', 'nonempty'))
        data = core.ledger('tag', 'acct')
        self.assertEqual(fake.posts, 2)
        _, billed = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '2', '--max-charge', '0.006')
        fake.usage = '0.002'; fake.count = 1
        with patch.object(core, 'provider_check', return_value=check): core.submit_run(workspace, billed, data, fake)
        billed = core.resume_run(workspace, billed, data, fake)
        data = core.ledger('tag', 'acct')
        self.assertEqual((billed['billing'], billed['charged_units'], billed['result']), ('reconciled', 1, 'nonempty'))
        with patch.object(core, 'provider_check', return_value=check):
            _, third = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '2', '--max-charge', '0.006')
            fake.usage = '0.03'
            with self.assertRaisesRegex(core.Blocked, 'unexplained_account_usage'): core.submit_run(workspace, third, data, fake)
        self.assertEqual(fake.posts, 3)
        fake.usage = '0.0136'; fake.status = 500
        with patch.object(core, 'provider_check', return_value=check):
            with self.assertRaisesRegex(core.Blocked, 'unresolved_submission'): core.submit_run(workspace, third, data, fake)
        self.assertEqual(data['runs'][third['id']]['lifecycle'], 'submission_unknown')
        self.assertEqual(fake.posts, 4)
    def test_malformed_post_response_is_unknown(self):
        self.setup_client()
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '2', '--max-charge', '0.006')
        grant = dict(grantor='Jim', issued_at='2020-01-01T00:00:00Z', expires_at='2099-01-01T00:00:00Z', source_reference='instruction', client='tag', account='acct', cumulative_usd='10', billable_units=50, covered_cost_classes=['actor_events'], provider_use_decision='allowed', retention_decision='metadata_links_only', collector=core.pwd.getpwuid(core.os.getuid()).pw_name, mode='spike', ancillary_usd='0.01', spike_limit_policy={'source_reference':'docs','schema_hash':'s','pricing_hash':'p'}, usage_baseline={'usageCycle':{'startAt':'a'},'totalUsageCreditsUsdAfterVolumeDiscount':'0'})
        check = {'authenticated_account_id':'acct','schema_hash':'s','pricing_hash':'p','minimum_published_unit_price_usd':'0.001','maximum_published_unit_price_usd':'0.0058','minimum_charge_usd':'0.0058'}
        class Malformed:
            posts = 0
            def request(self, method, path, payload=None, authenticated=True):
                if method == 'POST':
                    self.posts += 1
                    return {'data': []}
                return {'data': grant['usage_baseline']}
        transport = Malformed()
        data = {'grant': grant, 'runs': {}}
        with patch.object(core, 'provider_check', return_value=check):
            with self.assertRaisesRegex(core.Blocked, 'unresolved_submission'):
                core.submit_run(self.root/'workspace', run, data, transport)
        self.assertEqual(transport.posts, 1)
        self.assertEqual(data['runs'][run['id']]['lifecycle'], 'submission_unknown')

    def test_list_export_guards_and_tampering(self):
        self.setup_client()
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '2', '--max-charge', '0.006')
        code, listing = self.invoke('list', '--client', 'tag', '--account', 'acct')
        self.assertEqual(code, 0); self.assertEqual(listing['runs'][0]['id'], run['id'])
        code, _ = self.invoke('export', '--client', 'tag', '--account', 'acct', '--run', run['id'], '--output', str(self.root/'out'))
        self.assertEqual(code, 2)
        run['input']['enrichWithEcommerceData'] = True; run['input_hash'] = core.digest(run['input'])
        grant = dict(grantor='Jim', issued_at='2020-01-01T00:00:00Z', expires_at='2099-01-01T00:00:00Z', source_reference='instruction', client='tag', account='acct', cumulative_usd='10', billable_units=50, covered_cost_classes=['actor_events'], provider_use_decision='allowed', retention_decision='metadata_links_only', collector=core.pwd.getpwuid(core.os.getuid()).pw_name, mode='spike', ancillary_usd='0')
        with self.assertRaisesRegex(core.Blocked, 'input_changed'): core.submit_run(self.root/'workspace', run, {'grant':grant,'runs':{}}, object())
        grant['provider_use_decision'] = 'denied'
        with self.assertRaisesRegex(core.Blocked, 'provider_policy_not_approved'): core.grant_validate(grant, 'tag', 'acct')
    def test_coverage_capped_with_per_url_bound_and_price_headroom(self):
        self.setup_client()
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', 'https://facebook.com/page2', '--results-limit', '2', '--max-charge', '0.006')
        run.update(lifecycle='succeeded', dataset_id='dataset', billing='reconciled', actual_charge_usd='0.002', charged_units=2, maximum_unit_price_usd='0.0058')
        class Fake:
            def request(self, method, path):
                if '/items?' not in path: return {'data':{'itemCount':2}}
                return [{'ad_archive_id':'1','page_name':'A'},{'ad_archive_id':'2','page_name':'B'}]
        run = core.paginate(self.root/'workspace', run, Fake())
        self.assertEqual(run['coverage'], 'capped')
        run['charged_units'] = 3
        run = core.paginate(self.root/'workspace', run, Fake())
        self.assertEqual(run['coverage'], 'unknown')
    def test_billed_error_row_blocks_followup_collection(self):
        self.setup_client()
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '5', '--max-charge', '0.024')
        run.update(lifecycle='succeeded', dataset_id='dataset', billing='reconciled', actual_charge_usd='0.0058', charged_units=1, maximum_unit_price_usd='0.0058')
        core.save_ledger('tag','acct',{'grant':None,'runs':{run['id']:{'billing':'reconciled','actual_charge_usd':'0.0058','charged_units':1}}})
        class Provider:
            def request(self, method, path):
                if '/items?' in path: return [{'error':'no_items','errorDescription':'Empty or private data for provided input','url':'https://facebook.com/page'}]
                return {'data':{'itemCount':1}}
        run=core.paginate(self.root/'workspace',run,Provider())
        self.assertEqual((run['coverage'],run['result'],run['normalized'],run['billing']),('provider_error','unknown',0,'reconciled'))
        self.assertEqual(run['provider_errors'],['no_items'])
        self.assertEqual(core.ledger('tag','acct')['runs'][run['id']]['collection_block'],'provider_error')

    def test_classification_failure_retains_incomplete_intent(self):
        self.setup_client()
        _, run = self.invoke('plan', '--client', 'tag', '--account', 'acct', '--urls', 'https://facebook.com/page', '--results-limit', '2', '--max-charge', '0.006')
        run.update(lifecycle='succeeded',dataset_id='dataset',billing='reconciled',actual_charge_usd='0.0058',charged_units=1,maximum_unit_price_usd='0.0058')
        core.save_ledger('tag','acct',{'grant':None,'runs':{run['id']:{'provider_run_id':'provider','billing':'reconciled','collection_finalized':True,'collection_block':'count_mismatch'}}})
        class Failure:
            def request(self,*args): raise core.Blocked('network_failure')
        with self.assertRaises(core.Blocked): core.paginate(self.root/'workspace',run,Failure())
        intent=core.ledger('tag','acct')['runs'][run['id']]
        self.assertFalse(intent['collection_finalized'])
        self.assertEqual(intent['collection_block'],'count_mismatch')

    def test_symlink_rejected(self):
        (self.root / 'alias').symlink_to(self.root / 'target')
        with self.assertRaises(core.Blocked): core.safe_dir(self.root / 'alias' / 'child')
    def test_error_redacts_untrusted_exception(self):
        with patch.object(core, 'provider_check', side_effect=ValueError('token=secret')):
            code, error = self.invoke('provider-check')
        self.assertEqual(code, 2); self.assertNotIn('secret', json.dumps(error))

if __name__ == '__main__': unittest.main()
