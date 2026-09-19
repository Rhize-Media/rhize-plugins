import importlib.util
from pathlib import Path
import json

spec = importlib.util.spec_from_file_location('evidence_report', Path(__file__).parents[1]/'evidence_report.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_native_counts_actual_arrays_and_keeps_invalid_and_truncated():
    result = report.native_summary({'claudeVersion':'x','cases':[{'name':'case','runsPerCase':99,'arms':{
        'with':[{'turns':0,'error':'environment refusal','graders':[], 'passed':False},
                {'turns':6,'error':'Reached maximum number of turns','graders':[{'scored':True}], 'passed':True}],
        'without':[{'turns':3,'error':None,'graders':[{'scored':True}], 'passed':True}]}}]})
    assert result['actualRuns']==3
    assert result['arms']['with']=={'attempts':2,'environmentInvalid':1,'truncated':1,'reportedPasses':1}


def test_both_hosts_visible_and_missing_is_unavailable(tmp_path):
    r = report.build_report(tmp_path,tmp_path/'memory',tmp_path/'routine',tmp_path/'central')
    assert r['memory']['summary'] is None
    assert r['routines']['receipts'] is None
    assert r['central']['configurationAvailable'] is False
    summary = report.memory_summary([{'host':'claude','answerStatus':'unavailable_model'}, {'host':'codex','answerStatus':'queued'}])
    assert set(summary['hosts'])=={'claude','codex'}
    assert summary['hosts']['claude']['capturedPairs']==1
    assert summary['hosts']['claude']['gradedCompletePairs']==0


def test_single_arm_flags_do_not_create_controlled_pairs(tmp_path):
    root=tmp_path/'routine';root.mkdir()
    (root/'one.json').write_text(json.dumps({'schemaVersion':2,'comparable':True,'arm':'A'}))
    r=report.build_report(tmp_path,tmp_path/'memory',root,tmp_path/'central')
    assert r['routines']['declaredComparableByArm']=={'A':1}
    assert r['routines']['controlledPairStatus']=='not_established_by_individual_receipt_flags'


def test_invalid_health_is_unavailable_and_reported(tmp_path):
    health = tmp_path/'memory'/'health'
    health.mkdir(parents=True)
    (health/'claude.json').write_text('{broken')
    r = report.build_report(tmp_path, tmp_path/'memory', tmp_path/'routine', tmp_path/'central')
    assert r['memory']['health']['claude'] is None
    assert r['memory']['errors'][0]['file'] == 'claude.json'
