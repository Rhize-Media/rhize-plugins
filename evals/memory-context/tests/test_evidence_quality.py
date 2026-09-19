import json
import os
from pathlib import Path

import pytest
from memory_context.model_identity import resolve_model, answer_eligibility
from memory_context.quality import grade_answer
from memory_context.model_evaluation import evaluate_answers


def test_claude_model_from_matching_transcript_only(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    p = tmp_path / '.claude/projects/project/session.jsonl'
    p.parent.mkdir(parents=True)
    p.write_text('\n'.join(json.dumps(r) for r in [
        {'type':'assistant','sessionId':'session','message':{'model':'claude-opus-5'}},
        {'type':'assistant','sessionId':'other','message':{'model':'wrong-model'}}]))
    event = {'session_id':'session','transcript_path':str(p)}
    assert resolve_model('claude', event, {}) == ('claude-opus-5', 'session_transcript_last_assistant')
    assert resolve_model('claude', {**event, 'model':'explicit[1m]'}, {}) == ('explicit[1m]', 'hook_event')
    assert resolve_model('codex', event, {}) == (None, 'unavailable')
    assert resolve_model('claude', {**event, 'session_id':'other'}, {}) == (None, 'unavailable')
    assert resolve_model('claude', {**event, 'transcript_path':str(p.parent/'..'/'..'/'..'/'session.jsonl')}, {}) == (None, 'unavailable')
    p.unlink()
    outside = tmp_path / 'outside.jsonl'
    outside.write_text(json.dumps({'type':'assistant','sessionId':'session','message':{'model':'secret-model'}}))
    p.symlink_to(outside)
    assert resolve_model('claude', event, {}) == (None, 'unavailable')


def test_missing_model_preserves_valid_session_cache():
    assert resolve_model('claude', {}, {'model':'m'}) == ('m', 'session_event_cache')
    assert resolve_model('claude', {'model':'<synthetic>'}, {}) == (None, 'unavailable')


def test_action_requests_are_not_answer_benchmarks():
    assert answer_eligibility('Implement the memory workflow') == 'action_request'
    assert answer_eligibility('Recall the policy and deploy the fix') == 'action_request'
    assert answer_eligibility('What is the release policy?') == 'bounded_question_candidate'
    assert answer_eligibility('How does deployment verification work?') == 'bounded_question_candidate'
    assert answer_eligibility('Memory workflow') == 'unclassified_request'


def test_grades_are_versioned_and_missing_never_passes():
    rubric = {'requiredTerms':['verified'], 'forbiddenTerms':['skip'], 'requiredSourceHashes':['s']}
    assert grade_answer('verified', ['s'], rubric)['passed'] is True
    assert grade_answer('skip verified', ['s'], rubric)['passed'] is False
    assert grade_answer('verified', [], rubric)['passed'] is False
    assert grade_answer('wrong', ['s'], rubric)['passed'] is False
    assert grade_answer('anything', [], None)['passed'] is None
    with pytest.raises(ValueError, match='empty rubric'):
        grade_answer('anything', [], {})
    assert grade_answer('unavailable', [], {'expectedAbstention':True})['passed'] is True
    assert grade_answer('42', [], {'expectedAbstention':True})['passed'] is False


def test_invalid_rubric_does_not_consume_model_usage(tmp_path):
    calls = []
    with pytest.raises(ValueError, match='empty rubric'):
        evaluate_answers('codex', 'm', 'question', {'A':'a', 'B':'b'}, tmp_path,
                         rubric={}, executor=lambda *args: calls.append(args))
    assert calls == []


def test_review_is_private_opt_in_and_blind(tmp_path):
    def executor(*args):
        return {'status':'completed','actuallyRan':True,'model':'m','answer':'verified', 'sourceIds':['s']}
    result = evaluate_answers('codex','m','question',{'A':'a','B':'b'},tmp_path,
        rubric={'requiredTerms':['verified']},executor=executor,review_dir=tmp_path/'review')
    bundle = result['reviewBundle']
    path = tmp_path/'review'/bundle['file']
    assert path.stat().st_mode & 0o777 == 0o600
    payload = json.loads(path.read_text())
    assert set(payload['responses']) == {'response-1','response-2'}
    assert 'armMapping' not in payload
    assert all('answer' not in r for r in result['arms'].values())
    assert all(r['grading']['humanReview']=='pending' for r in result['arms'].values())
