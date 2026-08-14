alter table operations add column attempt_count integer not null default 0 check (attempt_count >= 0);

alter table approvals rename to approvals_v1;

create table approvals (
  id integer primary key,
  operation_id text not null references operations(id) on delete cascade,
  approval text not null,
  actor text,
  created_at text not null
);

insert into approvals (operation_id, approval, actor, created_at)
select operation_id, approval, null, updated_at
from approvals_v1;

drop table approvals_v1;

create index if not exists idx_operations_plan_revision on operations(plan_revision);
create index if not exists idx_approvals_operation_created_at on approvals(operation_id, created_at);
