'use strict';

const fs = require('node:fs');
const study = require('../hooks/lib/skill-study');

{
  try {
    const data = JSON.parse(fs.readFileSync(0, 'utf8'));
    if (data.hook_event_name !== process.argv[2]) return;
    if (data.hook_event_name === 'SessionStart') study.enroll(data);
    if (data.hook_event_name === 'PostToolUse') study.invoked(data);
    if (data.hook_event_name === 'Stop') study.stop(data);
  } catch (_) { /* A missing, duplicate or invalid receipt never interrupts Claude. */ }
}
