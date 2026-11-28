'use strict';

// Private, opt-in Claude skill trial. No call to Laya and no registry/label writes.
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { instrumentSha256 } = require('./laya-instrument');

const { formatSkillRef } = require('./route-core');

const STUDY = 'claude-skill-advice-v1';
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;
const sha = data => crypto.createHash('sha256').update(data).digest('hex');
const productionRoot = () => path.join(os.homedir(), '.local/share/rhize/skill-advice-study');
const root = () => process.env.RHIZE_SKILL_STUDY_ROOT || productionRoot();
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
const join = path.join;

function privateDir(dir) {
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  const s = fs.lstatSync(dir);
  if (!s.isDirectory() || s.uid !== process.getuid() || (s.mode & 0o077)) throw Error('unsafe study directory');
}

// Publish complete files. link is first-writer-wins for immutable receipts; rename advances the active turn.
function write(file, value, replace = false) {
  const tmp = file + '.' + crypto.randomUUID();
  fs.writeFileSync(tmp, JSON.stringify(value) + '\n', { flag: 'wx', mode: 0o600 });
  try {
    if (replace) fs.renameSync(tmp, file);
    else fs.linkSync(tmp, file);
  } finally {
    if (fs.existsSync(tmp)) fs.unlinkSync(tmp);
  }
}

function fingerprints() {
  const files = ['hooks.json', '../scripts/skill_study_hook.js', 'skill-router.js', 'lib/skill-study.js', 'lib/laya-instrument.js', 'lib/route-core.js',
    'lib/decision-registry.js', 'lib/laya-client.js', 'lib/typed-decisions.js'];
  return sha(Buffer.concat(files.map(f => fs.readFileSync(join(__dirname, '..', f)))));
}

function config() {
  const stat = fs.lstatSync(root());
  if (!stat.isDirectory() || stat.uid !== process.getuid() || (stat.mode & 0o077)) return null;
  const cfg = read(join(root(), 'config.json'));
  if (cfg.study !== STUDY || cfg.enabled !== true || !['validation', 'live'].includes(cfg.population)
      || !(Date.parse(cfg.start) <= Date.now() && Date.now() < Date.parse(cfg.end))
      || !/^[0-9a-f]{64}$/.test(cfg.index) || cfg.runtime !== fingerprints()
      || !Number.isSafeInteger(cfg.registryRevision) || cfg.instrument !== instrumentSha256()
      || !/^[0-9a-f]{40}$/.test(cfg.modelRevision)
      || (cfg.population === 'live') !== (path.resolve(root()) === productionRoot())
      || (cfg.population === 'validation' && !UUID.test(cfg.validationSession))) return null;
  return cfg;
}

function sessionDir(data) {
  if (!UUID.test(data.session_id || '') || data.agent_id || data.agent_type || data.thread_id) return null;
  const base = join(process.env.CLAUDE_CONFIG_DIR || join(os.homedir(), '.claude'), 'projects');
  const file = data.transcript_path || '';
  if (path.dirname(path.dirname(file)) !== base || path.basename(file) !== data.session_id + '.jsonl') return null;
  return join(root(), 'sessions', sha(data.session_id));
}

function enroll(data) {
  if (data.source !== 'startup') return;
  const dir = sessionDir(data);
  if (!dir) return;
  const cfg = config();
  if (!cfg || (cfg.population === 'validation' && cfg.validationSession !== data.session_id)) return;
  // Headless verification is admitted only by exact session ID in its own validation store.
  if (cfg.population === 'live' && process.env.CLAUDE_CODE_ENTRYPOINT !== 'cli') return;
  for (const p of [root(), join(root(), 'sessions'), dir]) privateDir(p);
  const group = sha(STUDY + ':' + data.session_id);
  write(join(dir, 'assignment.json'), { study: STUDY, population: cfg.population, session: sha(data.session_id),
    config: sha(JSON.stringify(cfg)), arm: parseInt(group.slice(0, 2), 16) < 128 ? 'control' : 'live',
    at: new Date().toISOString() });
}

function startTurn(data) {
  const dir = sessionDir(data);
  if (!dir || !fs.existsSync(join(dir, 'assignment.json'))) return null;
  // Invalidate an unanswered earlier offer even when this prompt cannot produce a suggestion.
  const token = crypto.randomBytes(16).toString('hex');
  write(join(dir, 'current.json'), { token }, true);
  const assignment = read(join(dir, 'assignment.json'));
  let cfg;
  try { cfg = config(); } catch (_) { /* keep a retired assignment outside legacy research */ }
  const inPopulation = assignment.population === 'validation' || process.env.CLAUDE_CODE_ENTRYPOINT === 'cli';
  const active = Boolean(inPopulation && cfg && assignment.config === sha(JSON.stringify(cfg)));
  return { dir, token, cfg: active ? cfg : null, arm: assignment.arm,
    reason: active ? null : 'window_source_or_population_changed', promptHash: sha(data.prompt || '') };
}

function prepare(turn, state, plan, laya, record, payloadFor) {
  const { dir, token, cfg, arm } = turn;
  const compatible = Boolean(cfg && record && plan.config.mode === 'shadow' && !plan.config.pinned
    && plan.config.registryRevision === cfg.registryRevision && !process.env.RHIZE_LAYA_ENDPOINT
    && plan.config.endpoint === 'http://127.0.0.1:8000' && plan.config.model === 'typed-decisions'
    && record.indexSha256 === cfg.index && record.layaRevision === cfg.modelRevision
    && record.instrumentSha256 === cfg.instrument && record.promptHash === turn.promptHash);
  const wouldOffer = Boolean(compatible && state.incumbentShown && laya.status === 'ok'
    && laya.choice !== 'none' && laya.choice !== state.incumbentShown && plan.shortlist.includes(laya.choice));
  const line = wouldOffer && arm === 'live' ? 'Laya suggests ' + formatSkillRef(laya.choice) + '. You can follow, challenge, choose neither, or abstain. '
    + 'If you respond, finish this turn with one line: Laya ' + token
    + ' <follow|challenge|neither|abstain> <fit|wrong_choice|missing_candidate|wrong_question|uncertain>. '
    + 'You may append incumbent or unlisted after a challenge. Use your judgment and continue the task normally.' : null;
  const receipt = { token, session: sha(state.sessionId), promptHash: turn.promptHash, at: state.ts,
    eligible: state.eligible, compatible, wouldOffer, hold: turn.reason, arm, incumbent: state.incumbentShown,
    record: record || null, offered: Boolean(line), messageHash: line ? sha(line) : null,
    payloadHash: line ? sha(payloadFor(state.incumbentMessage + '\n' + line)) : null };
  write(join(dir, token + '.turn.json'), receipt);
  return line;
}

function delivered(turn, payload) {
  write(join(turn.dir, turn.token + '.delivered.json'), { token: turn.token, payloadHash: sha(payload || '') });
}

function current(data) {
  const dir = sessionDir(data);
  if (!dir || !fs.existsSync(join(dir, 'current.json'))) return null;
  const { token } = read(join(dir, 'current.json'));
  if (!/^[a-f0-9]{32}$/.test(token)) return null;
  const turn = read(join(dir, token + '.turn.json'));
  if (turn.session !== sha(data.session_id) || turn.token !== token) return null;
  return { dir, token, turn };
}

function invoked(data) {
  if (data.tool_name !== 'Skill' || !data.tool_use_id || typeof data.tool_input?.skill !== 'string') return;
  const active = current(data);
  if (!active) return;
  const { dir, token, turn } = active;
  const invoked = data.tool_input.skill;
  const match = (turn.record?.shortlist || []).find(id => formatSkillRef(id) === invoked);
  const id = sha(data.tool_use_id);
  write(join(dir, token + '.' + id + '.skill.json'), { token, session: turn.session,
    skill: match || 'unlisted', toolUseHash: id, at: new Date().toISOString() });
}

// Confirm the most recent native user request and its hook attachment. A truncated or unflushed
// transcript leaves feedback unverified; never search an earlier turn for a convenient match.
function boundOffer(data, turn) {
  const fd = fs.openSync(data.transcript_path, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
  try {
    const stat = fs.fstatSync(fd);
    if (!stat.isFile() || stat.uid !== process.getuid()) return false;
    const bytes = Buffer.alloc(Math.min(stat.size, 512 * 1024));
    const n = fs.readSync(fd, bytes, 0, bytes.length, stat.size - bytes.length);
    const lines = bytes.subarray(0, n).toString('utf8').split('\n');
    if (stat.size > bytes.length) lines.shift();
    let request = false, offered = false;
    for (const line of lines) {
      if (!line.trim()) continue;
      const row = JSON.parse(line);
      if (row.sessionId !== data.session_id || row.isSidechain || row.isMeta) continue;
      const content = row.message?.content;
      if (row.type === 'user') {
        if (Array.isArray(content) && content.some(x => x.type === 'tool_result')) continue;
        const text = Array.isArray(content) ? content.filter(x => x.type === 'text').map(x => x.text).join('') : content;
        request = typeof text === 'string' && sha(text) === turn.promptHash;
        offered = false;
      }
      const a = row.attachment;
      if (request && a?.type === 'hook_additional_context' && a.hookEvent === 'UserPromptSubmit'
          && Array.isArray(a.content) && a.content.some(x => typeof x === 'string'
            && sha(x.split('\n').at(-1)) === turn.messageHash)) offered = true;
    }
    return request && offered;
  } finally { fs.closeSync(fd); }
}

function stop(data) {
  const active = current(data);
  if (!active) return;
  const { dir, token, turn } = active;
  const delivery = read(join(dir, token + '.delivered.json'));
  try {
    write(join(dir, token + '.stop.json'), { token, at: new Date().toISOString() });
  } catch (err) { if (err.code !== 'EEXIST') throw err; }
  if (!turn.offered || turn.arm !== 'live' || delivery.token !== token || delivery.payloadHash !== turn.payloadHash || turn.session !== sha(data.session_id)) return;
  const last = (data.last_assistant_message || '').trim().split('\n').pop().trim();
  const m = /^Laya ([a-f0-9]{32}) (follow|challenge|neither|abstain) (fit|wrong_choice|missing_candidate|wrong_question|uncertain)(?: (incumbent|unlisted))?$/.exec(last);
  if (!m || m[1] !== token || (m[4] && m[2] !== 'challenge')) {
    if ((data.last_assistant_message || '').includes('Laya ' + token)) {
      write(join(dir, token + '.malformed.json'), { token });
    }
    return;
  }
  let bound = false;
  try { bound = boundOffer(data, turn); } catch (_) { /* insufficient native evidence */ }
  if (!bound) {
    write(join(dir, token + '.unverified.json'), { token });
    return;
  }
  const file = join(dir, token + '.feedback.json');
  try {
    write(file, { token, session: turn.session, promptHash: turn.promptHash,
    messageHash: turn.messageHash, payloadHash: delivery.payloadHash, response: m[2], reason: m[3], alternative: m[4] || null,
    at: new Date().toISOString(), basis: 'native_claude_stop' });
  } catch (err) {
    if (err.code !== 'EEXIST') throw err;
    const first = read(file);
    if (first.response !== m[2] || first.reason !== m[3] || first.alternative !== (m[4] || null)) {
      write(join(dir, token + '.conflict.json'), { token, response: m[2], reason: m[3] });
    }
  }
}

module.exports = { STUDY, UUID, productionRoot, root, privateDir, write, fingerprints, enroll, startTurn, prepare, delivered, invoked, stop };
