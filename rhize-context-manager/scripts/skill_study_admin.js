#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const study = require('../hooks/lib/skill-study');
const { sha256Hex, instrumentSha256 } = require('../hooks/lib/laya-instrument');
const { readIndexes } = require('../hooks/lib/route-core');
const { defaultRoot } = require('../hooks/lib/typed-decisions');
const { readDecisionConfig } = require('../hooks/lib/decision-registry');

function start(population, end, validationSession) {
  if (!['validation', 'live'].includes(population) || !(Date.parse(end) > Date.now())) throw Error('invalid population/end');
  if (population === 'validation' && (!process.env.RHIZE_SKILL_STUDY_ROOT || !study.UUID.test(validationSession || ''))) {
    throw Error('validation requires a separate root and an exact native session UUID');
  }
  if (population === 'live' && (validationSession || process.env.RHIZE_SKILL_STUDY_ROOT)) throw Error('live uses the default private root');
  const root = study.root();
  if (population === 'validation' && path.resolve(root) === study.productionRoot()) throw Error('validation requires separate storage');
  const config = readDecisionConfig('skill-fit');
  const modelRevision = JSON.parse(fs.readFileSync(path.join(defaultRoot(), 'laya-runtime.json'), 'utf8')).revision;
  const index = readIndexes();
  if (!index || !/^[0-9a-f]{40}$/.test(modelRevision) || config.mode !== 'shadow' || config.pinned
      || !config.registryRevision || config.endpoint !== 'http://127.0.0.1:8000') throw Error('unsupported registry, model or index');
  study.privateDir(root);
  const result = { study: study.STUDY, population, enabled: true, start: new Date().toISOString(),
    end: new Date(end).toISOString(), allocation: 'sha256-session-50-50', runtime: study.fingerprints(),
    index: sha256Hex(JSON.stringify(index)), modelRevision, registryRevision: config.registryRevision,
    instrument: instrumentSha256(), ...(validationSession ? { validationSession } : {}) };
  study.write(path.join(root, 'config.json'), result);
  return result;
}

if (require.main === module) {
  try {
    const [action, ...args] = process.argv.slice(2);
    const file = path.join(study.root(), 'config.json');
    if (action === 'start') console.log(JSON.stringify(start(...args)));
    else if (action === 'stop') {
      const cfg = JSON.parse(fs.readFileSync(file, 'utf8'));
      study.write(file, { ...cfg, enabled: false, stopped: new Date().toISOString() }, true);
      console.log('Study stopped. Evidence retained.');
    } else throw Error('use start live END | start validation END SESSION | stop');
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
