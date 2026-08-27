#!/usr/bin/env node
'use strict';

// Thin, fail-silent UserPromptSubmit adapter. The Python selector emits only for a
// healthy real provider, a current snapshot, and an explicitly armed repository.

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

function main() {
  try {
    const input = fs.readFileSync(0, 'utf8');
    const pluginRoot = process.env.CLAUDE_PLUGIN_ROOT || path.resolve(__dirname, '..');
    const runner = path.join(pluginRoot, 'scripts', 'context_experiments', 'runner.py');
    const result = spawnSync('python3', [runner, 'hook-select'], {
      input,
      encoding: 'utf8',
      env: process.env,
      timeout: 5000,
    });
    if (result.status === 0 && result.stdout) process.stdout.write(result.stdout);
  } catch (_error) {
    // Advisory experiment selection must never block a user prompt.
  }
  process.exit(0);
}

main();
