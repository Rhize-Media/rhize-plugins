"""Repair-plan mechanism checks; these are not natural workflow benefit evidence."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'rhize-context-manager/scripts'
sys.path.insert(0, str(SCRIPTS))
from workflow_selection import opportunity, decide, record, finish, hook_message
from memory_context.procedural_adapter import from_response


@pytest.mark.parametrize('payload,env,explicit,expected', [
    ({}, {'CODEX_THREAD_ID': 'parent'}, 'unknown', 'unknown'),
    ({}, {'CODEX_THREAD_ID': 'parent', 'CLAUDE_CODE_ENTRYPOINT': 'cli'}, 'unknown', 'claude'),
    ({'thread_id': 'native'}, {}, 'unknown', 'codex'),
    ({}, {'PLUGIN_ROOT': '/installed/plugin'}, 'unknown', 'codex'),
    ({}, {'CLAUDE_CODE_ENTRYPOINT': 'cli'}, 'unknown', 'claude'),
    ({'thread_id': 'native'}, {'CLAUDE_CODE_ENTRYPOINT': 'parent'}, 'unknown', 'unknown'),
    ({}, {'PLUGIN_ROOT': '/installed/plugin', 'CLAUDE_CODE_ENTRYPOINT': 'cli'}, 'unknown', 'unknown'),
    ({'thread_id': 42}, {'PLUGIN_ROOT': ' ', 'CLAUDE_CODE_ENTRYPOINT': ''}, 'unknown', 'unknown'),
    ({}, {}, 'unknown', 'unknown'),
    ({'thread_id': 'native'}, {'PLUGIN_ROOT': '/parent'}, 'claude', 'claude'),
    ({}, {'CLAUDE_CODE_ENTRYPOINT': 'parent'}, 'codex', 'codex'),
])
def test_host_inference_does_not_trust_inherited_session(payload, env, explicit, expected):
    from workflow_selection import detect_host
    assert detect_host(payload, env, explicit) == expected


def test_opportunity_dedup_and_privacy(tmp_path):
    payload = {'prompt':'Write a resource article about private topic xyz', 'session_id':'secret-session','turn_id':'turn1'}
    first, changed = opportunity(payload, 'codex', tmp_path, {})
    assert changed and first['selection'] is None and first['events'] == []
    second, changed = opportunity(payload, 'codex', tmp_path, {})
    assert not changed and first == second
    assert 'private topic xyz' not in json.dumps(first) and 'secret-session' not in json.dumps(first)
    assert hook_message(first) and first['classification']['variant'] is None
    other, changed = opportunity(payload, 'claude', tmp_path, {})
    assert changed and other['opportunityId'] != first['opportunityId']
    assert (tmp_path / (first['opportunityId']+'.json')).stat().st_mode & 0o777 == 0o600


def test_completion_requires_separate_stages(tmp_path):
    value,_ = opportunity({'prompt':'Draft an article','session_id':'x'}, 'codex', tmp_path, {})
    identity = value['opportunityId']
    selection=SimpleNamespace(id=identity,decision='reuse',workflow='rhize-content-engine',variant='local-draft',reason='existing_workflow',run_id='fixture-run',source_sha256='b'*64)
    decide(tmp_path, selection)
    with pytest.raises(ValueError): finish(tmp_path, SimpleNamespace(id=identity,status='completed'))
    evidence=tmp_path/'evidence.txt'; evidence.write_text('actual fixture evidence')
    for stage in ('execution','validation','capture'):
        if stage == 'capture': evidence.write_text(json.dumps({'schemaVersion':1,'beforeCount':2,'afterCount':3,'rowSha256':'a'*64,'capturedAt':'2026-09-19T00:00:00Z'}))
        record(tmp_path, SimpleNamespace(id=identity,event=stage,status='passed',evidence=str(evidence),run_id='fixture-run',source_sha256='b'*64))
    result=finish(tmp_path,SimpleNamespace(id=identity,status='completed'))
    assert result['terminalStatus']=='completed' and len(result['events'])==3
    with pytest.raises(ValueError): finish(tmp_path,SimpleNamespace(id=identity,status='failed'))


def test_failed_partial_do_not_require_fake_success(tmp_path):
    for status in ('failed','partial','unavailable'):
        v,_=opportunity({'prompt':'Draft an article','session_id':status},'claude',tmp_path,{})
        failure=tmp_path/(status+'.txt');failure.write_text('actual fixture failure observation')
        r=finish(tmp_path,SimpleNamespace(id=v['opportunityId'],status=status,reason='operator_stopped',evidence=str(failure)))
        assert r['terminalStatus']==status and r['events']==[]


def test_variant_requires_explicit_agent_decision(tmp_path):
    v,_=opportunity({'prompt':'Publish a website article','session_id':'x'},'codex',tmp_path,{})
    assert v['classification']['eligible'] is None and v['classification']['variant'] is None
    with pytest.raises(ValueError):
        decide(tmp_path,SimpleNamespace(id=v['opportunityId'],decision='reuse',workflow='rhize-content-engine',variant='full-publishing',reason='existing_workflow',run_id='fixture-run',source_sha256='b'*64))
    r=decide(tmp_path,SimpleNamespace(id=v['opportunityId'],decision='unavailable',workflow='rhize-content-engine',variant='full-publishing',reason='capability_missing'))
    assert r['selection']['decision']=='unavailable'


def test_adapter_never_grants_execution():
    ref={'name':'content-engine','version':'2.0.0','kind':'graph','description':'metadata','digestMatches':True,
         'sourceId':'a'*64,'sourceRevision':'b'*64,'trust':'unreviewed','health':'ok','score':5,'executionAuthorized':False}
    result=from_response({'protocolVersion':'rhize-procedural-recall-v1','executionAuthorized':False,
                          'status':'available','observedAt':'2026-09-19T00:00:00Z','references':[ref]},tenant='t',project='p')
    assert result['candidates'][0]['trustClass']=='unverified'
    assert result['candidates'][0]['contentRole']=='procedure-reference'
    ref['executionAuthorized']=True
    with pytest.raises(ValueError):
        from_response({'protocolVersion':'rhize-procedural-recall-v1','executionAuthorized':False,'status':'available','references':[ref]},tenant='t',project='p')


def load_builder():
    spec=importlib.util.spec_from_file_location('local_builder', SCRIPTS/'build_local_skill_map.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_local_root_allowlist_and_escape(tmp_path):
    builder=load_builder();root=tmp_path/'approved';root.mkdir();outside=tmp_path/'outside';outside.mkdir()
    (outside/'SKILL.md').write_text('---\nname: private-outside\ndescription: no\n---\n')
    (root/'escape').symlink_to(outside,target_is_directory=True)
    valid=root/'synced'/'article';valid.mkdir(parents=True)
    (valid/'SKILL.md').write_text('---\nname: rhize-content-engine\ndescription: resource articles\n---\n')
    cfg=tmp_path/'sources.json';cfg.write_text(json.dumps({'schemaVersion':1,'approvedSkillRoots':[{'id':'synced','path':str(root)}]}))
    nodes,edges,summary=builder.collect_local_skills(cfg)
    assert [n['name'] for n in nodes if n['kind']=='skill']==['rhize-content-engine']
    assert summary['skippedEntries']==1
    assert builder.collect_local_skills(None)[0]==[]


def test_manifest_root_skill(tmp_path):
    builder=load_builder();plugin=tmp_path/'humanizer';(plugin/'.claude-plugin').mkdir(parents=True)
    (plugin/'.claude-plugin/plugin.json').write_text(json.dumps({'skills':['./']}))
    (plugin/'SKILL.md').write_text('---\nname: humanizer\ndescription: review article prose\n---\n')
    settings=tmp_path/'settings.json';settings.write_text(json.dumps({'enabledPlugins':{'humanizer@third':True}}))
    nodes,_,summary,_=builder.collect_third_party_ecosystem({'plugins':{'humanizer@third':[{'installPath':str(plugin),'scope':'user'}]}},'rhize',settings,tmp_path/'absent')
    assert any(n['name']=='humanizer' and n['kind']=='skill' for n in nodes)
    assert summary['skills']==1


def test_retry_and_terminal_seal(tmp_path):
    v,_=opportunity({'prompt':'Write a resource article','session_id':'s'},'codex',tmp_path,{})
    identity=v['opportunityId'];decide(tmp_path,SimpleNamespace(id=identity,decision='reuse',workflow='rhize-content-engine',variant='local-draft',reason='existing_workflow',run_id='fixture-run',source_sha256='b'*64))
    evidence=tmp_path/'result';evidence.write_text('same validator report')
    for status in ('passed','failed','passed'):
        record(tmp_path,SimpleNamespace(id=identity,event='validation',status=status,evidence=str(evidence),run_id='fixture-run',source_sha256='b'*64))
    saved=json.loads((tmp_path/(identity+'.json')).read_text())
    assert [e['status'] for e in saved['events']]==['passed','failed','passed']
    finish(tmp_path,SimpleNamespace(id=identity,status='partial',reason='operator_stopped',evidence=str(evidence),run_id='fixture-run',source_sha256='b'*64))
    with pytest.raises(ValueError): record(tmp_path,SimpleNamespace(id=identity,event='execution',status='passed',evidence=str(evidence),run_id='fixture-run',source_sha256='b'*64))
    next_value,fresh=opportunity({'prompt':'Write a resource article','session_id':'s'},'codex',tmp_path,{})
    assert fresh and next_value['opportunityId'] != identity
    replay,fresh=opportunity({'prompt':'Write a resource article','session_id':'s'},'codex',tmp_path,{})
    assert not fresh and replay['opportunityId']==next_value['opportunityId']


def test_trivial_request_is_unclassified_until_explicit_skip(tmp_path):
    v,_=opportunity({'prompt':'Hello','session_id':'x'},'codex',tmp_path,{})
    assert v['classification']['eligible'] is None
    r=decide(tmp_path,SimpleNamespace(id=v['opportunityId'],decision='skip',workflow=None,variant=None,reason='simple_or_nonworkflow_task'))
    assert r['classification']['eligible'] is False
    from workflow_selection import report
    summary = report(tmp_path)
    assert summary['counts']['selected'] == 0 and summary['counts']['decided'] == 1
    assert summary['decisions']['skip'] == 1


def test_stage_binding_and_missing_report(tmp_path):
    from workflow_selection import report
    assert report(tmp_path/'missing')['counts'] is None
    v,_=opportunity({'prompt':'Draft an article','session_id':'binding'},'codex',tmp_path,{})
    decide(tmp_path,SimpleNamespace(id=v['opportunityId'],decision='reuse',workflow='rhize-content-engine',variant='local-draft',reason='existing_workflow',run_id='run1',source_sha256='b'*64))
    evidence=tmp_path/'evidence';evidence.write_text('actual evidence')
    with pytest.raises(ValueError,match='match the selected run'):
        record(tmp_path,SimpleNamespace(id=v['opportunityId'],event='execution',status='passed',evidence=str(evidence),run_id='other',source_sha256='b'*64))
    with pytest.raises(ValueError,match='explicit skip'):
        finish(tmp_path,SimpleNamespace(id=v['opportunityId'],status='skipped'))


def test_optin_router_preserves_other_advice_and_deduplicates_checkpoint(tmp_path):
    import os
    import shutil
    import subprocess
    home=tmp_path/'home'; data=tmp_path/'data'
    catalog=home/'.claude/context-manager';catalog.mkdir(parents=True)
    shutil.copyfile(ROOT/'tests/skill-map/fixtures/indexes-valid-map.json',catalog/'skill-map.indexes.json')
    cfg=data/'rhize/workflow-selection/config.json';cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({'schemaVersion':1,'enabled':True}))
    env={**os.environ,'HOME':str(home),'XDG_DATA_HOME':str(data),'PYTHONDONTWRITEBYTECODE':'1'}
    payload=json.dumps({'prompt':'help me get git and context tooling set up','session_id':'fixture','turn_id':'t1'})
    result=subprocess.run(['node',str(ROOT/'rhize-context-manager/hooks/skill-router.js')],input=payload,text=True,capture_output=True,env=env,timeout=8)
    assert result.returncode==0, result.stderr
    message=json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
    assert 'Workflow selection checkpoint' in message and 'Consider the rhize-context-manager:graphify skill' in message
    # Packaged hook sees the same host identity and must not inject again.
    result=subprocess.run([sys.executable,str(SCRIPTS/'workflow_selection.py'),'hook'],input=payload,text=True,capture_output=True,env=env,timeout=8)
    assert result.returncode==0 and result.stdout=='',result.stderr
    receipts=list((data/'rhize/workflow-selection/receipts').glob('*.json'))
    assert len(receipts)==1 and json.loads(receipts[0].read_text())['classification']['eligible'] is None
    # An unusable config must preserve the existing route, not swallow it.
    cfg.write_text('{broken')
    result=subprocess.run(['node',str(ROOT/'rhize-context-manager/hooks/skill-router.js')],input=payload,text=True,capture_output=True,env=env,timeout=8)
    assert 'Consider the rhize-context-manager:graphify skill' in result.stdout


def test_packaged_checkpoint_missing_entrypoint_is_nonblocking(tmp_path):
    import os,subprocess
    hooks=json.loads((ROOT/'rhize-context-manager/hooks/hooks.json').read_text())['hooks']['UserPromptSubmit']
    command=next(h['command'] for g in hooks for h in g['hooks'] if 'workflow_selection.py' in h['command'])
    env={**os.environ,'CLAUDE_PLUGIN_ROOT':str(tmp_path/'missing')}
    result=subprocess.run(command,shell=True,executable='/bin/sh',capture_output=True,text=True,env=env,timeout=8)
    assert result.returncode==0 and result.stderr==''
    assert 'unavailable' in json.loads(result.stdout)['systemMessage']


def test_procedural_preview_is_optin_and_baseline_unchanged():
    import subprocess
    from datetime import datetime,timezone
    from memory_context.core import MemoryContextAssembler
    from memory_context.procedural_adapter import ProceduralMemoryContextAssembler
    core=SCRIPTS/'memory_context/core.py'
    assert core.read_bytes()==subprocess.check_output(['git','show','e184246a5d325320126b18f6d3906b1d921fc025:rhize-context-manager/scripts/memory_context/core.py'],cwd=ROOT)
    candidate={'sourceSystem':'procedural-memory','sourceId':'a'*64,'sourceRevision':'b'*64,'tenant':'t','project':'p','sensitivity':'internal','trustClass':'unverified','retentionClass':'session','contentRole':'procedure-reference','recordedAt':'2026-09-19T00:00:00Z','provenance':['graph:content-engine@2.0.0'],'relevance':1.0,'content':'Inert graph reference'}
    document={'schemaVersion':1,'request':{'tenant':'t','project':'p','query':'article'},'adapters':[{'name':'procedural-memory','memoryType':'procedural','status':'available','protocolVersion':'rhize-procedural-recall-v1','candidates':[candidate]}]}
    with pytest.raises(ValueError):MemoryContextAssembler().assemble(document)
    manifest,_=ProceduralMemoryContextAssembler().assemble(document,datetime(2026,9,19,tzinfo=timezone.utc))
    assert len(manifest['candidates'])==1 and manifest['candidates'][0]['processingPolicy']=='reference-only'
    candidate['contentRole']='policy-reference'
    with pytest.raises(ValueError):ProceduralMemoryContextAssembler().assemble(document)
