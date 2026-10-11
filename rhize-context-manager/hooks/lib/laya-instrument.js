'use strict';
// laya-choice-v1: the skill-fit Laya instrument (Node reference; Python mirror:
// scripts/typed_decisions/instrument.py). Both must produce identical canonical
// requests for every case in
// tests/rhize-context-manager/fixtures/typed-decisions/laya-choice-requests.json.
//
// Parity rules (plan §4.2): lengths are Unicode code points (Array.from);
// "whitespace" is ASCII whitespace only (space \t \n \r \f \v); the prompt head
// is the first PROMPT_HEAD_CODEPOINTS code points, cut back to the last ASCII
// whitespace inside the final CUT_WINDOW code points when the prompt was longer,
// then right-stripped; descriptions collapse ASCII-whitespace runs, strip, cut
// to DESCRIPTION_CODEPOINTS and strip again; canonical JSON (sorted keys,
// compact) is used only for hashes. The prompt head goes only to the loopback
// Laya server and is never persisted.
const crypto = require('crypto');

const INSTRUMENT = 'laya-choice-v1';
const MODEL = 'typed-decisions';
const PROMPT_HEAD_CODEPOINTS = 1200;
const CUT_WINDOW = 200;
const DESCRIPTION_CODEPOINTS = 120;
const MAX_CANDIDATES = 5;
const QUESTION_ID = 'skill';
const QUESTION = 'Which skill, if any, should be loaded to handle `request`?';
const NONE_KEY = 'none';
const NONE_CRITERION = 'none of these skills is needed; answer directly';
const ASCII_WS = new Set([' ', '\t', '\n', '\r', '\f', '\v']);
const SKILL_ID = /^skill:[A-Za-z0-9_.\-/]+$/;

function canonicalJson(value) {
  const sortDeep = (v) => {
    if (Array.isArray(v)) return v.map(sortDeep);
    if (v && typeof v === 'object') {
      const out = {};
      for (const key of Object.keys(v).sort()) out[key] = sortDeep(v[key]);
      return out;
    }
    return v;
  };
  return JSON.stringify(sortDeep(value));
}

function sha256Hex(text) {
  return crypto.createHash('sha256').update(String(text), 'utf8').digest('hex');
}

function instrumentSha256() {
  return sha256Hex(canonicalJson({
    instrument: INSTRUMENT, model: MODEL, question: QUESTION, questionId: QUESTION_ID,
    noneKey: NONE_KEY, noneCriterion: NONE_CRITERION,
    promptHeadCodepoints: PROMPT_HEAD_CODEPOINTS, cutWindow: CUT_WINDOW,
    descriptionCodepoints: DESCRIPTION_CODEPOINTS, maxCandidates: MAX_CANDIDATES,
  }));
}

function lengthBucket(prompt) {
  const n = Array.from(String(prompt)).length;
  if (n < 200) return 'lt200';
  if (n < 600) return '200-600';
  if (n <= 1200) return '600-1200';
  return 'gt1200';
}

function rstripAscii(points) {
  let end = points.length;
  while (end > 0 && ASCII_WS.has(points[end - 1])) end -= 1;
  return points.slice(0, end);
}

function stripAscii(points) {
  let start = 0;
  while (start < points.length && ASCII_WS.has(points[start])) start += 1;
  return rstripAscii(points.slice(start));
}

function promptHead(prompt) {
  if (typeof prompt !== 'string') throw new Error('prompt must be a string');
  const points = Array.from(prompt);
  if (points.length <= PROMPT_HEAD_CODEPOINTS) return { head: prompt, truncated: false };
  let head = points.slice(0, PROMPT_HEAD_CODEPOINTS);
  const windowStart = PROMPT_HEAD_CODEPOINTS - CUT_WINDOW;
  let cut = -1;
  for (let i = head.length - 1; i >= windowStart; i -= 1) {
    if (ASCII_WS.has(head[i])) { cut = i; break; }
  }
  if (cut >= windowStart) head = head.slice(0, cut);
  return { head: rstripAscii(head).join(''), truncated: true };
}

function skillName(skillId) {
  if (typeof skillId !== 'string' || !SKILL_ID.test(skillId)) throw new Error('invalid skill id');
  const rest = skillId.slice('skill:'.length);
  return rest.slice(rest.lastIndexOf('/') + 1);
}

function criterionText(skillId, description) {
  const name = skillName(skillId);
  let desc = description === undefined || description === null ? '' : description;
  if (typeof desc !== 'string') throw new Error('description must be a string or null');
  const collapsed = [];
  let inRun = false;
  for (const ch of Array.from(desc)) {
    if (ASCII_WS.has(ch)) {
      if (!inRun) collapsed.push(' ');
      inRun = true;
    } else {
      collapsed.push(ch);
      inRun = false;
    }
  }
  const text = rstripAscii(stripAscii(collapsed).slice(0, DESCRIPTION_CODEPOINTS)).join('');
  return text ? `${name}: ${text}` : name;
}

// candidates: [{skillId, description}] (1..MAX_CANDIDATES, unique ids).
// Returns {request, keyMap, truncated, promptLengthBucket, criteriaSha256, instrumentSha256}.
function buildChoiceRequest(prompt, candidates) {
  if (!Array.isArray(candidates) || candidates.length < 1 || candidates.length > MAX_CANDIDATES) {
    throw new Error('candidate count out of range');
  }
  const ids = [];
  for (const item of candidates) {
    if (!item || typeof item !== 'object' || Array.isArray(item) || !('skillId' in item) ||
        Object.keys(item).some((k) => k !== 'skillId' && k !== 'description')) {
      throw new Error('invalid candidate');
    }
    skillName(item.skillId);
    ids.push(item.skillId);
  }
  if (new Set(ids).size !== ids.length) throw new Error('duplicate candidate');
  const { head, truncated } = promptHead(prompt);
  const criteria = {};
  const keyMap = {};
  candidates.forEach((item, index) => {
    const key = `s${index}`;
    criteria[key] = criterionText(item.skillId, item.description);
    keyMap[key] = item.skillId;
  });
  criteria[NONE_KEY] = NONE_CRITERION;
  const request = {
    model: MODEL,
    state: { request: head },
    questions: { [QUESTION_ID]: { type: 'choice', instructions: QUESTION, criteria } },
  };
  return {
    request, keyMap, truncated,
    promptLengthBucket: lengthBucket(prompt),
    criteriaSha256: sha256Hex(canonicalJson(criteria)),
    instrumentSha256: instrumentSha256(),
  };
}

// Validates a /v1/systemone response. Returns {choice: skillId|'none',
// probabilities: [p per shortlist key in order..., p_none]}; throws
// Error('invalid_response') on any contract violation.
function decodeChoiceResponse(response, keyMap) {
  const fail = () => { throw new Error('invalid_response'); };
  if (!response || typeof response !== 'object' || !response.routing || typeof response.routing !== 'object') fail();
  if (response.routing.model !== MODEL) fail();
  const answers = response.answers;
  if (!answers || typeof answers !== 'object' || Array.isArray(answers)) fail();
  const answerKeys = Object.keys(answers);
  if (answerKeys.length !== 1 || answerKeys[0] !== QUESTION_ID) fail();
  const answer = answers[QUESTION_ID];
  if (!answer || typeof answer !== 'object' || answer.type !== 'choice') fail();
  const n = Object.keys(keyMap || {}).length;
  const keys = [];
  for (let i = 0; i < n; i += 1) {
    if (!Object.prototype.hasOwnProperty.call(keyMap, `s${i}`)) fail();
    keys.push(`s${i}`);
  }
  keys.push(NONE_KEY);
  if (!keys.includes(answer.choice)) fail();
  const probs = answer.probabilities;
  if (!probs || typeof probs !== 'object' || Array.isArray(probs)) fail();
  const probKeys = Object.keys(probs);
  if (probKeys.length !== keys.length || probKeys.some((k) => !keys.includes(k))) fail();
  const values = keys.map((k) => {
    const p = probs[k];
    if (typeof p !== 'number' || !Number.isFinite(p) || p < 0 || p > 1) fail();
    return p;
  });
  return { choice: answer.choice === NONE_KEY ? NONE_KEY : keyMap[answer.choice], probabilities: values };
}

module.exports = {
  INSTRUMENT, MODEL, PROMPT_HEAD_CODEPOINTS, CUT_WINDOW, DESCRIPTION_CODEPOINTS, MAX_CANDIDATES,
  QUESTION_ID, QUESTION, NONE_KEY, NONE_CRITERION,
  canonicalJson, sha256Hex, instrumentSha256, lengthBucket, promptHead, skillName, criterionText,
  buildChoiceRequest, decodeChoiceResponse,
};
