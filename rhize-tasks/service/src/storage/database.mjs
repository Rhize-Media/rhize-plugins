import {DatabaseSync} from 'node:sqlite';
import {mkdirSync, readFileSync} from 'node:fs';
import {dirname} from 'node:path';

import {assertOperation, assertTask} from '../domain.mjs';
import {defaultDatabasePath} from './paths.mjs';

const migrations = [
  {version: 1, sql: readFileSync(new URL('./migrations/001-initial.sql', import.meta.url), 'utf8')},
];

function now() { return new Date().toISOString(); }

function assertJson(value, path = 'value', seen = new WeakSet()) {
  if (value === null || ['string', 'boolean'].includes(typeof value)) return;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new TypeError(`${path}: must contain only finite JSON values`);
    return;
  }
  if (typeof value !== 'object' || seen.has(value)) throw new TypeError(`${path}: must be JSON data without cycles`);
  seen.add(value);
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      if (!Object.hasOwn(value, index)) throw new TypeError(`${path}: must not contain sparse arrays`);
      assertJson(value[index], `${path}[${index}]`, seen);
    }
  } else if (Object.getPrototypeOf(value) === Object.prototype) {
    for (const [key, item] of Object.entries(value)) assertJson(item, `${path}.${key}`, seen);
  } else {
    throw new TypeError(`${path}: must be plain JSON data`);
  }
  seen.delete(value);
}

function encodeJson(value, path) {
  assertJson(value, path);
  return JSON.stringify(value);
}

function decodeJson(value, table, column) {
  try { return JSON.parse(value); } catch (error) {
    throw new SyntaxError(`invalid JSON in ${table}.${column}: ${error.message}`);
  }
}

function clone(value, path) {
  return decodeJson(encodeJson(value, path), 'clone', 'value');
}

function plainRows(value) {
  if (Array.isArray(value)) return value.map(plainRows);
  if (value !== null && typeof value === 'object' && Object.getPrototypeOf(value) === null) return Object.fromEntries(Object.entries(value));
  return value;
}

function publicDatabase(db) {
  return new Proxy(db, {
    get(target, property) {
      if (property === 'prepare') return (...args) => {
        const statement = target.prepare(...args);
        return new Proxy(statement, {
          get(statementTarget, statementProperty) {
            if (statementProperty === 'get' || statementProperty === 'all') return (...statementArgs) => plainRows(statementTarget[statementProperty](...statementArgs));
            const value = statementTarget[statementProperty];
            return typeof value === 'function' ? value.bind(statementTarget) : value;
          },
        });
      };
      const value = target[property];
      return typeof value === 'function' ? value.bind(target) : value;
    },
  });
}

function assertPlan(plan) {
  if (plan === null || typeof plan !== 'object' || Array.isArray(plan) || Object.getPrototypeOf(plan) !== Object.prototype) throw new TypeError('plan: must be a plain object');
  if (!Number.isInteger(plan.planRevision) || plan.planRevision < 1) throw new RangeError('plan.planRevision must be an integer >= 1');
  assertJson(plan, 'plan');
  return plan;
}

export function transaction(db, fn) {
  db.exec('begin immediate');
  try {
    const result = fn();
    db.exec('commit');
    return result;
  } catch (error) {
    db.exec('rollback');
    throw error;
  }
}

export function openDatabase(path = defaultDatabasePath(), {Database = DatabaseSync} = {}) {
  if (typeof path !== 'string' || path.length === 0) throw new TypeError('database path must be a nonempty string');
  mkdirSync(dirname(path), {recursive: true});
  const db = new Database(path);
  db.exec('pragma foreign_keys = on');
  db.exec('create table if not exists schema_migrations (version integer primary key, applied_at text not null)');
  const newest = db.prepare('select max(version) as version from schema_migrations').get().version;
  const supported = migrations.at(-1).version;
  if (newest !== null && newest > supported) {
    db.close();
    throw new RangeError(`database has newer schema migration ${newest}; this build supports ${supported}`);
  }
  for (const migration of migrations) {
    if (db.prepare('select 1 from schema_migrations where version = ?').get(migration.version)) continue;
    transaction(db, () => {
      db.exec(migration.sql);
      db.prepare('insert into schema_migrations (version, applied_at) values (?, ?)').run(migration.version, now());
    });
  }
  return publicDatabase(db);
}

function appendAudit(db, entry) {
  if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) throw new TypeError('audit entry must be an object');
  const {event, entityType, entityId, data = {}, occurredAt = now()} = entry;
  if (typeof event !== 'string' || event.length === 0 || typeof entityType !== 'string' || entityType.length === 0 || typeof entityId !== 'string' || entityId.length === 0) throw new TypeError('audit entry requires nonempty event, entityType, and entityId');
  db.prepare('insert into audit_log (occurred_at, event, entity_type, entity_id, data_json) values (?, ?, ?, ?, ?)').run(occurredAt, event, entityType, entityId, encodeJson(data, 'audit.data'));
}

function sourceMapping(task) {
  const externalId = task.sourceType === 'jira' ? task.jiraKey ?? task.jiraUrl : task.delegationId;
  return externalId ? {sourceType: task.sourceType, externalId} : null;
}

export function taskRepository(db) {
  const get = id => {
    const row = db.prepare('select data_json, manual_lock from tasks where id = ?').get(id);
    if (!row) return null;
    const task = assertTask(decodeJson(row.data_json, 'tasks', 'data_json'));
    return {...task, manualLock: Boolean(row.manual_lock)};
  };
  return {
    upsert(task) {
      assertTask(task);
      const copy = clone(task, 'task');
      const mapping = sourceMapping(copy);
      transaction(db, () => {
        db.prepare('insert into tasks (id, data_json, manual_lock, updated_at) values (?, ?, ?, ?) on conflict(id) do update set data_json = excluded.data_json, manual_lock = excluded.manual_lock, updated_at = excluded.updated_at').run(copy.id, encodeJson(copy, 'task'), copy.manualLock ? 1 : 0, now());
        if (mapping) db.prepare('insert into task_sources (task_id, source_type, external_id, source_revision) values (?, ?, ?, ?) on conflict(task_id, source_type, external_id) do update set source_revision = excluded.source_revision').run(copy.id, mapping.sourceType, mapping.externalId, copy.sourceRevision);
        appendAudit(db, {event: 'task_upserted', entityType: 'task', entityId: copy.id, data: {sourceRevision: copy.sourceRevision}});
      });
      return copy;
    },
    get,
    list() {
      return db.prepare('select data_json, manual_lock from tasks order by id').all().map(row => {
        const task = assertTask(decodeJson(row.data_json, 'tasks', 'data_json'));
        return {...task, manualLock: Boolean(row.manual_lock)};
      });
    },
    lock(id, reason) {
      if (typeof id !== 'string' || id.length === 0 || typeof reason !== 'string' || reason.length === 0) throw new TypeError('lock requires a task id and reason');
      const existing = get(id);
      if (!existing) return null;
      const locked = {...existing, manualLock: true};
      transaction(db, () => {
        db.prepare('update tasks set data_json = ?, manual_lock = 1, updated_at = ? where id = ?').run(encodeJson(locked, 'task'), now(), id);
        appendAudit(db, {event: 'task_manual_locked', entityType: 'task', entityId: id, data: {reason}});
      });
      return locked;
    },
    preference(key) {
      const row = db.prepare('select value_json from preferences where key = ?').get(key);
      return row ? decodeJson(row.value_json, 'preferences', 'value_json') : null;
    },
  };
}

export function planRepository(db) {
  const read = row => row ? clone(assertPlan(decodeJson(row.data_json, 'plans', 'data_json')), 'plan') : null;
  return {
    save(plan) {
      assertPlan(plan);
      const copy = clone(plan, 'plan');
      transaction(db, () => {
        const existing = db.prepare('select data_json from plans where revision = ?').get(copy.planRevision);
        const serialized = encodeJson(copy, 'plan');
        if (existing) {
          if (existing.data_json !== serialized) throw new Error(`plan revision ${copy.planRevision} is immutable`);
          return;
        }
        db.prepare('insert into plans (revision, data_json, created_at) values (?, ?, ?)').run(copy.planRevision, serialized, now());
        for (const block of copy.blocks ?? []) {
          if (!block || typeof block !== 'object' || typeof block.id !== 'string' || typeof block.taskId !== 'string') throw new TypeError('plan block requires id and taskId');
          db.prepare('insert into plan_blocks (id, plan_revision, task_id, data_json) values (?, ?, ?, ?)').run(block.id, copy.planRevision, block.taskId, encodeJson(block, 'plan block'));
        }
        appendAudit(db, {event: 'plan_saved', entityType: 'plan', entityId: String(copy.planRevision), data: {planRevision: copy.planRevision}});
      });
      return copy;
    },
    get(revision) { return read(db.prepare('select data_json from plans where revision = ?').get(revision)); },
    latest() { return read(db.prepare('select data_json from plans order by revision desc limit 1').get()); },
  };
}

export function operationRepository(db) {
  const read = row => {
    if (!row) return null;
    const operation = assertOperation(decodeJson(row.data_json, 'operations', 'data_json'));
    if (row.result_json !== null) decodeJson(row.result_json, 'operations', 'result_json');
    return {...operation, retryState: row.retry_state};
  };
  const writeState = (id, state, result = null, event = 'operation_state_changed') => {
    if (!['pending', 'safe_retry', 'reconciliation_required', 'applied', 'failed'].includes(state)) throw new TypeError(`invalid operation state ${state}`);
    transaction(db, () => {
      if (db.prepare('update operations set retry_state = ?, result_json = ?, updated_at = ? where id = ?').run(state, result === null ? null : encodeJson(result, 'operation result'), now(), id).changes !== 1) throw new Error(`operation ${id} does not exist`);
      appendAudit(db, {event, entityType: 'operation', entityId: id, data: {state, result}});
    });
  };
  return {
    save(operation) {
      assertOperation(operation);
      const copy = clone(operation, 'operation');
      transaction(db, () => {
        const existing = db.prepare('select data_json from operations where id = ?').get(copy.id);
        const serialized = encodeJson(copy, 'operation');
        if (existing) {
          if (existing.data_json !== serialized) throw new Error(`operation ${copy.id} already exists with different data`);
          return;
        }
        db.prepare('insert into operations (id, plan_revision, idempotency_key, approval, retry_state, data_json, result_json, updated_at) values (?, ?, ?, ?, ?, ?, null, ?)').run(copy.id, copy.planRevision, copy.idempotencyKey, copy.approval, 'pending', serialized, now());
        db.prepare('insert into approvals (operation_id, approval, updated_at) values (?, ?, ?)').run(copy.id, copy.approval, now());
        appendAudit(db, {event: 'operation_saved', entityType: 'operation', entityId: copy.id, data: {planRevision: copy.planRevision, approval: copy.approval}});
      });
      return this.get(copy.id);
    },
    get(id) { return read(db.prepare('select data_json, retry_state, result_json from operations where id = ?').get(id)); },
    listForPlan(revision) { return db.prepare('select data_json, retry_state, result_json from operations where plan_revision = ? order by id').all(revision).map(read); },
    wasApplied(idempotencyKey) { return Boolean(db.prepare("select 1 from operations where idempotency_key = ? and retry_state = 'applied'").get(idempotencyKey)); },
    markState(id, state, result = null) { writeState(id, state, result); return this.get(id); },
    appendAudit(entry) { transaction(db, () => appendAudit(db, entry)); },
    lockTarget(targetId, reason) {
      const row = db.prepare('select data_json from tasks where id = ?').get(targetId);
      if (!row) return null;
      const task = assertTask(decodeJson(row.data_json, 'tasks', 'data_json'));
      const locked = {...task, manualLock: true};
      transaction(db, () => {
        db.prepare('update tasks set data_json = ?, manual_lock = 1, updated_at = ? where id = ?').run(encodeJson(locked, 'task'), now(), targetId);
        appendAudit(db, {event: 'task_manual_locked', entityType: 'task', entityId: targetId, data: {reason}});
      });
      return locked;
    },
  };
}
