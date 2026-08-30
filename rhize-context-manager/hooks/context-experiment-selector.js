#!/usr/bin/env node
'use strict';

// Thin, fail-silent UserPromptSubmit adapter. The Python selector emits only for a
// healthy real provider, a current snapshot, and an explicitly armed repository.

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

function selectorTimeoutMs() {
  try {
    const configPath = process.env.RHIZE_CONTEXT_EXPERIMENT_CONFIG
      || path.join(process.env.HOME || '', '.claude', 'rhize-context-manager', 'context-experiments.json');
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    const experiments = Object.values(config.experiments || {});
    const durations = experiments
      .filter((item) => item && item.enabled && item.armedRuns > 0)
      .map((item) => item.maxDurationSeconds)
      .filter((value) => Number.isInteger(value) && value >= 1 && value <= 300);
    const seconds = durations.length ? Math.max(...durations) : 30;
    return (seconds + 5) * 1000;
  } catch (_error) {
    return 35000;
  }
}

function main() {
  try {
    const input = fs.readFileSync(0, 'utf8');
    const pluginRoot = process.env.CLAUDE_PLUGIN_ROOT || path.resolve(__dirname, '..');
    const runner = path.join(pluginRoot, 'scripts', 'context_experiments', 'runner.py');
    const result = spawnSync('python3', [runner, 'hook-select'], {
      input,
      encoding: 'utf8',
      env: process.env,
      timeout: selectorTimeoutMs(),
    });
    if (result.status === 0 && result.stdout) process.stdout.write(result.stdout);
  } catch (_error) {
    // Advisory experiment selection must never block a user prompt.
  }
  process.exit(0);
}

main();
