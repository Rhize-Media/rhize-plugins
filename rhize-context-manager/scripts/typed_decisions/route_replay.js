#!/usr/bin/env node
'use strict';
// route_replay.js: replay prompts through the CURRENT router (route-core.js) for the typed-decision
// backfill (plan §4.5). One long-lived process, prompts over stdin only; nothing is written to disk.
//
//   node route_replay.js <index.json> <map.json>            JSON lines in, JSON lines out
//   node route_replay.js <index.json> <map.json> --hashes   print the version hashes and exit
//
// stdin line:  {"id": <any JSON scalar>, "prompt": "<text>"}
// stdout line: {"id", "incumbent": {"skillId","score"}|null, "explicit": bool, "shortlist": [skillId...],
//               "descriptions": {skillId: description|null}, "indexSha256", "routerSourceSha256"}
//              or {"id": <id|null>, "error": "invalid_request"} for a malformed line.
//
// incumbent = routeFromIndex(router, tokenize(prompt), prompt); shortlist =
// lexicalShortlist(router, tokens, incumbent?.skillId, 5). "explicit" marks an incumbent produced by an
// explicit skill request ("use <skill>"), for which the live router skips Laya.
// indexSha256 = sha256Hex(JSON.stringify(router object)) for the object handed to routeFromIndex (the file may
// hold {"router": {...}} or the bare router object); routerSourceSha256 = sha256Hex(utf8 text of route-core.js +
// skill-router.js + laya-instrument.js, concatenated in that order).
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const HOOKS = path.join(__dirname, '..', '..', 'hooks');
const { routeFromIndex, lexicalShortlist, tokenize } = require(path.join(HOOKS, 'lib', 'route-core.js'));
const { sha256Hex } = require(path.join(HOOKS, 'lib', 'laya-instrument.js'));

const SOURCE_FILES = [
  path.join(HOOKS, 'lib', 'route-core.js'),
  path.join(HOOKS, 'skill-router.js'),
  path.join(HOOKS, 'lib', 'laya-instrument.js'),
];
const SHORTLIST_K = 5;
const EXPLICIT_LABEL = 'explicit skill request';

function fail(message) {
  process.stderr.write(`route_replay: ${message}\n`);
  process.exit(2);
}

function loadJson(file, what) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (_err) {
    return fail(`cannot read ${what}`);
  }
}

function routerOf(doc) {
  const router = doc && typeof doc === 'object' && doc.router && typeof doc.router === 'object' ? doc.router : doc;
  if (!router || typeof router !== 'object' || !router.signals || typeof router.signals !== 'object') {
    fail('index has no router signals');
  }
  return router;
}

function descriptionsOf(mapDoc) {
  const out = new Map();
  for (const node of (mapDoc && Array.isArray(mapDoc.nodes)) ? mapDoc.nodes : []) {
    if (node && node.kind === 'skill' && typeof node.id === 'string') {
      out.set(node.id, typeof node.description === 'string' ? node.description : null);
    }
  }
  return out;
}

function main() {
  const args = process.argv.slice(2);
  const hashesOnly = args.includes('--hashes');
  const files = args.filter((arg) => arg !== '--hashes');
  if (files.length !== 2) fail('usage: route_replay.js <index.json> <map.json> [--hashes]');
  const router = routerOf(loadJson(files[0], 'index'));
  const descriptions = descriptionsOf(loadJson(files[1], 'map'));
  const indexSha256 = sha256Hex(JSON.stringify(router));
  const routerSourceSha256 = sha256Hex(SOURCE_FILES.map((file) => fs.readFileSync(file, 'utf8')).join(''));
  if (hashesOnly) {
    process.stdout.write(`${JSON.stringify({ indexSha256, routerSourceSha256 })}\n`);
    return;
  }

  const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  rl.on('line', (line) => {
    if (!line.trim()) return;
    let request;
    try {
      request = JSON.parse(line);
    } catch (_err) {
      request = null;
    }
    let out;
    if (!request || typeof request !== 'object' || typeof request.prompt !== 'string' || request.prompt === '') {
      out = { id: request && typeof request === 'object' && 'id' in request ? request.id : null, error: 'invalid_request' };
    } else {
      const tokens = tokenize(request.prompt);
      const match = routeFromIndex(router, tokens, request.prompt);
      const incumbent = match ? { skillId: match.skillId, score: match.score } : null;
      const explicit = Boolean(match && Array.isArray(match.signals) &&
        match.signals.some((signal) => signal && signal.label === EXPLICIT_LABEL));
      const shortlist = lexicalShortlist(router, tokens, incumbent ? incumbent.skillId : null, SHORTLIST_K);
      const known = {};
      for (const skillId of shortlist) known[skillId] = descriptions.has(skillId) ? descriptions.get(skillId) : null;
      out = { id: request.id === undefined ? null : request.id, incumbent, explicit, shortlist,
        descriptions: known, indexSha256, routerSourceSha256 };
    }
    if (!process.stdout.write(`${JSON.stringify(out)}\n`)) {
      rl.pause();
      process.stdout.once('drain', () => rl.resume());
    }
  });
}

main();
