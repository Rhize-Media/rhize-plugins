import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const FORMAT_ASSERTION = 'https://json-schema.org/draft/2020-12/vocab/format-assertion';
const FORMAT_ASSERTION_META = 'https://rhize.media/schemas/rhize-tasks/format-assertion-2020-12.meta.json';
const DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const DATE_TIME = /^(\d{4})-(\d{2})-(\d{2})T([01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9](?:\.\d{1,9})?)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$/;

async function schema(name) {
  return JSON.parse(await readFile(new URL(`../../schemas/${name}.schema.json`, import.meta.url), 'utf8'));
}

async function metaSchema() {
  return JSON.parse(await readFile(new URL('../../schemas/format-assertion-2020-12.meta.json', import.meta.url), 'utf8'));
}

function realDate(value) {
  const match = DATE.exec(value);
  if (!match) return false;
  const [, year, month, day] = match;
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  return date.getUTCFullYear() === Number(year) && date.getUTCMonth() === Number(month) - 1 && date.getUTCDate() === Number(day);
}

function assertFormatRejects(rule, value) {
  assert.equal(rule.format === 'date' || rule.format === 'date-time', true);
  assert.equal(rule.format === 'date' ? realDate(value) : DATE_TIME.test(value) && realDate(value.slice(0, 10)), false);
}

test('every persisted v1 schema opts into JSON Schema format assertion', async () => {
  const meta = await metaSchema();
  assert.equal(meta.$vocabulary[FORMAT_ASSERTION], true);
  for (const name of ['profile', 'task', 'today-view', 'operation', 'delegation-v1']) {
    assert.equal((await schema(name)).$schema, FORMAT_ASSERTION_META, name);
  }
});

test('schema URL constraints reject credentials as runtime validation does', async () => {
  const profile = await schema('profile');
  const task = await schema('task');
  const delegation = await schema('delegation-v1');
  const credentialed = 'https://user:pass@example.test';
  for (const rule of [profile.$defs.httpsUrl, task.properties.jiraUrl, delegation.properties.jira.allOf[0].then.properties.value]) {
    assert.doesNotMatch(credentialed, new RegExp(rule.pattern));
  }
});

test('schema date and timestamp fields reject impossible calendar values', async () => {
  const task = await schema('task');
  const today = await schema('today-view');
  const operation = await schema('operation');
  assertFormatRejects(task.properties.dueDate, '2026-02-30');
  assertFormatRejects(task.$defs.estimate.properties.confirmedAt, '2026-02-30T10:00:00Z');
  assertFormatRejects(today.properties.generatedAt, '2026-08-14T24:00:00Z');
  assertFormatRejects(operation.properties.createdAt, '2026-08-14T12:00:00+24:00');
});
