"""laya-choice-v1: the skill-fit Laya instrument (Python mirror of hooks/lib/laya-instrument.js).

Both implementations must produce identical canonical requests for every case in
tests/rhize-context-manager/fixtures/typed-decisions/laya-choice-requests.json.

Parity rules (plan §4.2):
- lengths are Unicode code points (Python str indexing; JS Array.from);
- "whitespace" means ASCII whitespace only: space, \\t, \\n, \\r, \\f, \\v;
- the prompt head is the first PROMPT_HEAD_CODEPOINTS code points; when the prompt was longer
  and the head's last CUT_WINDOW code points contain ASCII whitespace, the head is cut back to
  the last such whitespace, then trailing ASCII whitespace is removed;
- a description has ASCII-whitespace runs collapsed to one space and is stripped, cut to
  DESCRIPTION_CODEPOINTS code points and stripped again;
- canonical JSON (sorted keys, compact separators, UTF-8, no ASCII escaping) is used for hashes.

The prompt head is sent only to the loopback Laya server and is never persisted.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

INSTRUMENT = 'laya-choice-v1'
MODEL = 'typed-decisions'
PROMPT_HEAD_CODEPOINTS = 1200
CUT_WINDOW = 200
DESCRIPTION_CODEPOINTS = 120
MAX_CANDIDATES = 5
QUESTION_ID = 'skill'
QUESTION = 'Which skill, if any, should be loaded to handle `request`?'
NONE_KEY = 'none'
NONE_CRITERION = 'none of these skills is needed; answer directly'
LENGTH_BUCKETS = ('lt200', '200-600', '600-1200', 'gt1200')

ASCII_WS = ' \t\n\r\f\v'
_WS_RUN = re.compile('[ \t\n\r\f\v]+')
_SKILL_ID = re.compile(r'skill:[A-Za-z0-9_.\-/]+\Z')


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def instrument_sha256(instrument: str = INSTRUMENT) -> str:
    if instrument == 'credential-cli-v1':
        catalog = Path(__file__).resolve().parents[2] / 'catalog/credential-workflows.json'
        return sha256_hex(canonical_json(json.loads(catalog.read_text())))
    if instrument != INSTRUMENT:
        raise ValueError('unknown instrument')
    return sha256_hex(canonical_json({
        'instrument': INSTRUMENT, 'model': MODEL, 'question': QUESTION, 'questionId': QUESTION_ID,
        'noneKey': NONE_KEY, 'noneCriterion': NONE_CRITERION,
        'promptHeadCodepoints': PROMPT_HEAD_CODEPOINTS, 'cutWindow': CUT_WINDOW,
        'descriptionCodepoints': DESCRIPTION_CODEPOINTS, 'maxCandidates': MAX_CANDIDATES}))


def length_bucket(prompt: str) -> str:
    n = len(prompt)
    if n < 200:
        return 'lt200'
    if n < 600:
        return '200-600'
    if n <= 1200:
        return '600-1200'
    return 'gt1200'


def prompt_head(prompt: str) -> tuple[str, bool]:
    if not isinstance(prompt, str):
        raise ValueError('prompt must be a string')
    if len(prompt) <= PROMPT_HEAD_CODEPOINTS:
        return prompt, False
    head = prompt[:PROMPT_HEAD_CODEPOINTS]
    window_start = PROMPT_HEAD_CODEPOINTS - CUT_WINDOW
    cut = max(head.rfind(ch, window_start) for ch in ASCII_WS)
    if cut >= window_start:
        head = head[:cut]
    return head.rstrip(ASCII_WS), True


def skill_name(skill_id: str) -> str:
    if not isinstance(skill_id, str) or not _SKILL_ID.match(skill_id):
        raise ValueError('invalid skill id')
    return skill_id[len('skill:'):].rsplit('/', 1)[-1]


def criterion_text(skill_id: str, description) -> str:
    name = skill_name(skill_id)
    if description is None:
        description = ''
    if not isinstance(description, str):
        raise ValueError('description must be a string or null')
    text = _WS_RUN.sub(' ', description).strip(ASCII_WS)[:DESCRIPTION_CODEPOINTS].rstrip(ASCII_WS)
    return f'{name}: {text}' if text else name


def build_choice_request(prompt: str, candidates: list) -> dict:
    """candidates: [{'skillId': str, 'description': str|None}], 1..MAX_CANDIDATES, unique ids.

    Returns {'request', 'keyMap', 'truncated', 'promptLengthBucket', 'criteriaSha256',
    'instrumentSha256'}. Raises ValueError on invalid input.
    """
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError('candidate count out of range')
    ids = []
    for item in candidates:
        if not isinstance(item, dict) or set(item) - {'skillId', 'description'} or 'skillId' not in item:
            raise ValueError('invalid candidate')
        skill_name(item['skillId'])
        ids.append(item['skillId'])
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate candidate')
    head, truncated = prompt_head(prompt)
    criteria = {}
    key_map = {}
    for index, item in enumerate(candidates):
        key = f's{index}'
        criteria[key] = criterion_text(item['skillId'], item.get('description'))
        key_map[key] = item['skillId']
    criteria[NONE_KEY] = NONE_CRITERION
    request = {'model': MODEL, 'state': {'request': head},
               'questions': {QUESTION_ID: {'type': 'choice', 'instructions': QUESTION, 'criteria': criteria}}}
    return {'request': request, 'keyMap': key_map, 'truncated': truncated,
            'promptLengthBucket': length_bucket(prompt),
            'criteriaSha256': sha256_hex(canonical_json(criteria)),
            'instrumentSha256': instrument_sha256()}


def decode_choice_response(response, key_map: dict) -> dict:
    """Validate a /v1/systemone response for a laya-choice-v1 request.

    Returns {'choice': skillId|'none', 'probabilities': [p for each shortlist key in order, p_none]}.
    Raises ValueError('invalid_response') on any contract violation.
    """
    try:
        if not isinstance(response, dict) or not isinstance(response.get('routing'), dict):
            raise ValueError
        if response['routing'].get('model') != MODEL:
            raise ValueError
        answers = response.get('answers')
        if not isinstance(answers, dict) or set(answers) != {QUESTION_ID}:
            raise ValueError
        answer = answers[QUESTION_ID]
        if not isinstance(answer, dict) or answer.get('type') != 'choice':
            raise ValueError
        keys = [f's{i}' for i in range(len(key_map))] + [NONE_KEY]
        if set(key_map) != set(keys[:-1]):
            raise ValueError
        choice = answer.get('choice')
        if choice not in keys:
            raise ValueError
        probs = answer.get('probabilities')
        if not isinstance(probs, dict) or set(probs) != set(keys):
            raise ValueError
        values = []
        for key in keys:
            p = probs[key]
            if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
                raise ValueError
            values.append(float(p))
    except (ValueError, KeyError, TypeError):
        raise ValueError('invalid_response') from None
    return {'choice': NONE_KEY if choice == NONE_KEY else key_map[choice], 'probabilities': values}
