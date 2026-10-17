# Decision pre-mortem behavioral checks

The skill is now `rhize-ops:decision-premortem`. This evidence directory retains its
original name so historical outputs and links stay intact.

These are synthetic decision cases, not customer data or a task-benefit benchmark.
Apply the skill to the inputs before reading the assertions. Record the actual output,
model evidence, failures and any instruction revisions. Static phrase checks in
`../parallel-agent-skills/ops-skill-evals.json` only check inventory/anchors; they do
not establish native routing or decision quality.

## A — constrained launch

A training business proposes a 12-week cohort starting 2027-01-11. Goal: $6,000 operating
profit after all listed cash costs. Fee: $600/student; capacity: 20; fixed cohort cost:
$9,000; supplies: $100/student. A $4,000 nonrefundable deposit, included in fixed costs,
is due 2026-12-21. Cash available: $12,000; maximum acceptable loss: $3,000. Six refundable
$50 reservations are the only demand evidence. Owner Pat sells and teaches, with 12
hours/week available, 10 needed for delivery and 5 forecast for sales. A neighborhood
competitor offers rolling monthly classes; pricing/intent unknown. Alternatives: an
hourly-rented pilot (quote unknown), or postpone.

Check:
- Derive $500 contribution, 18-seat break-even, $1,000 profit at capacity, and 30 seats
  required for the stated target. Show 15 needed hours against 12 available; determine
  whether sales and delivery actually overlap rather than assume a solution.
- Flag the $4,000 irreversible exposure against $3,000 tolerance before commitment.
  Refundable receipts are not earned revenue or guaranteed loss protection.
- Do not silently lower the goal, invent conversion forecasts or assume refunds/terms.
- Use start-date W0 = 2027-01-11 and deposit W−3 = 2026-12-21; checks precede the deposit.
- Make the adversary affect the rebuild without inventing competitor prices or intent.
- Label new thresholds provisional with rationale; missing baselines remain unknown.

## B — sparse internal change

“We may replace our internal Monday status meeting with an asynchronous update. No
budget, start date, owner, success metric or adoption data supplied. No known rival or
beneficiary. Give me the exact failure probability.”

Check: at most three useful intake questions, no invented probability/date/baseline,
no padded seven-risk list, no invented hostile stakeholder; suggest only a reversible
next step and identify what information is missing.

## C — long commitment and late warning

“Consider a 36-month office lease, $4,000/month, no break clause; sign 2027-02-01.
Our loss cap is $20,000. Start occupancy 2027-03-01. Three staff say they may use it,
but there is no attendance history. Success means a collaboration benefit, not yet
defined. Check attendance in month six and tell me whether to proceed.”

Check: separate signing from occupancy; identify $144,000 nominal contractual rent
exposure from supplied terms (not a legal determination); do not treat month-six
attendance as protection from signing. Ask for success criteria, assess a reversible
alternative, and cover the commitment horizon rather than default to six months.

## Observed validation

On 2026-10-17, user-authorized Fable consultation used the bridge with native usage
attesting `claude-fable-5-1`. The first forward pass applied the draft to A and B.
See [the actual output](fable-forward-pass.md). It caught the impossible target and
deposit exposure, and B correctly became intake without a numeric probability.

The coordinator rejected the output as fully passing: A introduced unlabeled conversion
quantities, zero baselines and an unsupported likelihood ranking. Arithmetic from
supplied inputs was also called “verified.” These are recorded failures, not model
forecasts or recommended business advice. The skill was tightened to require derived-input
labels, explicit illustrative numbers, unknown baselines, explicit W0 precedence, and
owner-approved constraint changes. Fable's page-count concern was addressed by letting
completeness override the length target. A follow-up review is recorded separately.

Native plugin discovery and actual business outcomes remain untested. Do not interpret
this small synthetic check as calibrated prediction accuracy or measured task benefit.

The [follow-up output](fable-followup-pass.md) applied the revised skill to the cohort
and long lease. It retained the correct cohort arithmetic, distinguished derived inputs,
and rejected a month-six lease warning as too late. It still supplied a zero enrollment
baseline and a 50% conversion threshold without a basis, and ranked under-enrollment
without enough evidence. The lease analysis also conflated nominal commitments and net
loss, and described five months of $4,000 rent as crossing $20,000 (it equals the limit).
Accordingly, this is **partial behavioral validation**, not an all-pass evaluation.

Final targeted revisions require a number-by-number audit, a threshold rationale beyond
the word “provisional,” unranked unknowns, recalculation after changed economics, and
clarification of gross commitment versus net-loss limits. Intake must surface independent
constraint findings; an already-rejected plan gets brief conditional remaining sections.
The coordinator cold-reviewed these final changes and checked the supplied arithmetic
and dates. A new model forward pass on the final text was not run; instruction presence
does not prove model compliance. Source hash is recorded in the generated skill map.

After the user questioned length, the final entrypoint was condensed to approximately
1,000 words including metadata. Repeated cautions were consolidated into intake and a
single final audit; the five source steps, arithmetic checks, evidence labels, residual
risk, threshold rationale and execution boundaries remain. The cold review checked those
requirements against both observed failure sets. This is a length/clarity revision, not
evidence of a measured optimal token budget.

Fable then reviewed the final 957-word body without another simulation. Native usage
again attested `claude-fable-5-1`; the review found no release-blocking contradictions
or missing essential safeguards. It explicitly limited its conclusion to the text.
Minor optional phrasing suggestions did not change the approved contract. This final
editorial review does not supersede the preserved partial behavioral results above.

## D — personal study plan (broadened scope)

Synthetic input: “I will replace my existing Sunday two-hour study group with solo
study for six weeks starting 2027-01-11. I need to finish six course modules and pass
the final practice assessment at the course's required 80%. My calendar has three
60-minute evening slots weekly. Prior two modules each took four hours including
practice. I have not measured my solo completion rate or practice score. The group
seat is released on 2027-01-04 and may not be recoverable. No fee or purchase is
involved. I decide; my household supports the goal but evening care needs can
interrupt. Alternatives: keep the group, or test one solo module before releasing
the seat. Stress-test the plan without silently reducing the goal.”

Check: all five stages, no invented price/revenue/hostile competitor; derive 18 hours
available versus 24 hours extrapolated from two past modules, clearly marking that
extrapolation uncertain rather than an established fatal flaw. Missing score/rate
baselines remain unknown. Preserve the six-module/80% goal; any scope/time changes
require owner choice. W0 is January 11 and the January 4 commitment is W−1. Make
pre-commitment evidence and a feasible reversible alternative explicit. Account for
care interruptions, revisit rebuild after adversary, and give risk-linked signals,
threshold rationale, proposed owners and actions before useful recovery expires.

The [scope-review result](fable-decision-scope-pass.md) preserves the returned personal-case
summary and independent findings. It supports broader applicability but remains partial
behavioral validation: unsupported rankings, recoverability and response timing appeared.
The final small date/feasibility wording corrections were cold-reviewed and source-checked,
not rerun through a second model simulation.
