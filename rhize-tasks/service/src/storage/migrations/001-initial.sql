create table if not exists preferences (
  key text primary key,
  value_json text not null,
  updated_at text not null
);

create table if not exists tasks (
  id text primary key,
  data_json text not null,
  manual_lock integer not null default 0 check (manual_lock in (0, 1)),
  updated_at text not null
);

create table if not exists task_sources (
  task_id text not null references tasks(id) on delete cascade,
  source_type text not null,
  external_id text not null,
  source_revision text not null,
  primary key (task_id, source_type, external_id),
  unique (source_type, external_id)
);

create table if not exists plans (
  revision integer primary key check (revision >= 1),
  data_json text not null,
  created_at text not null
);

create table if not exists plan_blocks (
  id text primary key,
  plan_revision integer not null references plans(revision) on delete cascade,
  task_id text not null,
  data_json text not null
);

create table if not exists operations (
  id text primary key,
  plan_revision integer not null references plans(revision),
  idempotency_key text not null unique,
  approval text not null,
  retry_state text not null,
  attempt_count integer not null default 0 check (attempt_count >= 0),
  data_json text not null,
  result_json text,
  updated_at text not null
);

create table if not exists approvals (
  id integer primary key,
  operation_id text not null references operations(id) on delete cascade,
  approval text not null,
  actor text,
  created_at text not null
);

create table if not exists audit_log (
  id integer primary key,
  occurred_at text not null,
  event text not null,
  entity_type text not null,
  entity_id text not null,
  data_json text not null
);

create table if not exists routine_runs (
  id text primary key,
  routine text not null,
  state text not null,
  started_at text not null,
  completed_at text,
  data_json text not null
);
