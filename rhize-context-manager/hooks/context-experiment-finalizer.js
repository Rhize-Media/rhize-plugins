#!/usr/bin/env node
'use strict';

// Thin, fail-silent Stop adapter. Interrupted real-provider selections get an explicit
// incomplete receipt without consuming their armed run.

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

function main() {
  try {
    const input = fs.readFileSync(0, 'utf8');
    const pluginRoot = process.env.CLAUDE_PLUGIN_ROOT || path.resolve(__dirname, '..');
    const runner = path.join(pluginRoot, 'scripts', 'context_experiments', 'runner.py');
    const result = spawnSync('python3', [runner, 'hook-finalize'], {
      input,
      encoding: 'utf8',
      env: process.env,
      timeout: 5000,
    });
    if (result.status === 0 && result.stdout) process.stdout.write(result.stdout);
  } catch (_error) {
    // Finalization must never block session shutdown.
  }
  process.exit(0);
}

main();
