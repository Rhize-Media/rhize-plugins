#!/usr/bin/env node
// Usage: node run_router.js <route-core.js> <index.json> <rows.json> <out.json>
//
// Runs the real routeFromIndex()/tokenize() from the given route-core.js over every
// row's prompt against a router index (a full skill-map.indexes.json or a resolved
// index; either {router:{...}} or the bare router object). rows.json is a list of
// rows or {rows:[...]}. Writes [{id, top, score, signals}] in input order, with no
// timestamps or paths, so identical inputs give byte-identical output.
'use strict';
const fs = require('fs');
const path = require('path');

const [, , corePath, indexPath, rowsPath, outPath] = process.argv;
if (!corePath || !indexPath || !rowsPath || !outPath) {
  console.error('usage: node run_router.js <route-core.js> <index.json> <rows.json> <out.json>');
  process.exit(2);
}
const core = require(path.resolve(corePath));
const idx = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
const router = idx.router || idx;
const doc = JSON.parse(fs.readFileSync(rowsPath, 'utf8'));
const rows = Array.isArray(doc) ? doc : doc.rows;

const out = rows.map((r) => {
  const best = core.routeFromIndex(router, core.tokenize(r.prompt), r.prompt);
  return {
    id: r.id,
    top: best ? best.skillId : null,
    score: best ? best.score : null,
    signals: best ? best.signals.map((s) => s.label) : [],
  };
});
fs.writeFileSync(outPath, JSON.stringify(out, null, 1) + '\n');
