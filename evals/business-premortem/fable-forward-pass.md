# First forward pass — preserved failures

Synthetic input; draft skill, before corrections. This is an observed model output,
not a recommended decision memo. See README.md for coordinator findings and revisions.
Native model usage: `claude-fable-5-1`; observed 2026-10-17.

FORWARD TEST — skill followed as written on both cases. No tools used; all arithmetic is hand-derived from supplied numbers.

=== CASE A memo (12-week cohort) ===
Decision frame. Run one 12-week cohort, W0 = Mon 2027-01-11, ends ~2027-04-05. Goal: $6,000 operating profit. Alternatives: hourly-rented pilot (quote unknown), postpone. Last reversible date: $4,000 nonrefundable deposit due Mon 2026-12-21 (W−3). Owner: Pat. All inputs are supplied facts (not independently verified); the arithmetic below is verified from them. Competitor pricing/intent: unknown.

Feasibility arithmetic (verified from supplied numbers): contribution = $600 − $100 = $500/student. Break-even = 18 students. Max profit at capacity 20 = $1,000. $6,000 requires 30 students (150% of capacity). Loss cap ($3,000) is breached below 12 students if all $9,000 is committed; the deposit alone ($4,000) already exceeds the cap.

1. Autopsy (hypothetical, not a forecast). "At 2027-04-05 this plan failed to earn $6,000."
- F1 Goal unreachable by construction. Sold out, profit was $1,000. Hidden assumption: nobody checked capacity × margin. Confidence: high (verified).
- F2 Demand shortfall. Six refundable $50 holds converted to ~3–4 paid; cohort ran at 8–10; loss $4–5k. First warning: holds not converting by early December; recovery impossible after W−3. Hidden assumption: refundable holds predict paid seats. Likelihood: unknown, evidence thin. Shares cause with F3/F4.
- F3 Deposit paid before demand known; $4k > $3k loss tolerance, irreversible at W−3. Most dangerous.
- F4 Incumbent's rolling monthly classes absorbed late deciders unwilling to commit 12 weeks; pricing unknown (hypothetical, no evidence of intent).
- F5 Single-owner capacity: Pat sells and teaches; delivery 10 of 12 h/wk; sales 5 h/wk fits only before W0; prep/admin/illness unaccounted; no backup instructor.
- F6 Cash timing unknown: if the $5k balance and $2k supplies fall due before fees, buffer is $12k − $11k = $1k. Non-fatal if fees collected first; unknown.
Unknowns to test: cancellability of the $5k balance; fee collection date; hourly quote; competitor price; hold→paid conversion rate.

2. Verdict. Fatal flaw: F1 — cited capacity and price defeat the stated goal even if everything else works. Most likely failure: F2. Most dangerous: F3 (turns F2 into a loss above tolerance before enrolment is known). Biggest hidden assumption: holds ≈ paid students; cheapest falsifier: ask the six to pay a nonrefundable deposit now. Evidence that would change the verdict toward proceed: owner resets goal to ≤$1,000 or changes economics, and ≥12 nonrefundable paid seats before W−3. Cost of delay: January start slips; seasonality unknown. Provisional recommendation: decline as framed; pause-to-test a restructured version.

3. Rebuild (requires owner to change goal or economics — proposed, not assumed accepted).
- F1 → reset goal to ≤$1,000, or fee ≥$850 at 20 seats, or fixed cost ≤$4,000 (hourly rental) at $600 — estimates; tradeoff: price sensitivity unknown. Avoid otherwise.
- F3 → reduce: no deposit until nonrefundable paid seats ≥12 (loss-cap floor, provisional) by 2026-12-14 (W−4). Residual: −$3k at 12 seats.
- F2 → reduce: convert holds to paid; 5 h/wk selling from now to W−1.
- F5 → accept (owner Pat, proposed); name a backup instructor.
Checks: C1 hourly quote + confirm whether $5k balance is cancellable and fee collection timing, Pat, by 2026-11-16 (W−8); fail → revise economics. C2 ≥4/6 holds paid nonrefundable by 2026-11-30 (W−6); fail → pause. C3 ≥12 paid by 2026-12-14 (W−4); fail → walk away before deposit. C4 owner records competitor's public price by 2026-11-16 (can't be done here).

4. Adversary. Incumbent with rolling monthly classes: incentive to retain local students; capability to start any month and undercut on commitment length; plausible January promo (hypothetical). Overlooked response to the rebuilt plan: a shorter sales window with a hard W−4 gate pushes late deciders to the incumbent's next monthly start → maps to F2/F4, no new ID. Consequence: move C2 earlier is not possible without more data; instead add a "commitment-light" offer (e.g., 4-week module) as a C1 option. Verdict unchanged.

5. Tripwires (W0 = 2027-01-11; owners proposed, unassigned unless Pat).
| F2/F3 | Nonrefundable paid seats, enrolment ledger | 0 → 12 (loss cap, provisional) | 2026-11-30, weekly | Pat | <12 at W−4: no deposit, postpone |
| F4 | Competitor price/promo, public listing | unknown → any price <$600-equivalent | W−8, biweekly | Pat | revise price/offer at C1 |
| F5 | Hours logged vs 12 h cap | 0 → >12 h in any week | W−9, weekly | Pat | cut sales scope; name backup |
| F6 | Cash balance vs dated outflows | $12k → <$3k projected | W−8, biweekly | Pat | defer balance or walk away |
Final: Decline as stated. Decisive reason: 20 × $500 − $9,000 = $1,000 maximum, and the deposit alone exceeds the loss cap. Next: (1) owner resets goal/economics; (2) get hourly quote and balance cancellability by W−8; (3) convert the six holds to paid. Open unknowns: competitor price, fee timing, hold conversion.

=== CASE B memo (async status update) ===
Decision frame (supplied): replace Monday status meeting with an asynchronous update. No budget, start date, owner, success metric, adoption data, rival or beneficiary supplied. Per the skill, there is no concrete plan or failure definition, so this is an intake request, not an autopsy.
Exact failure probability: cannot be given. There is no baseline, metric or adoption data; any number would be invented. I will give a qualitative judgment once a failure definition exists.
Defensible provisional work only: alternatives are keep the meeting, hybrid (async + shorter sync), or pilot for a fixed window. No credible adversary in the evidence; the realistic threat is inertia (updates unread or unwritten) and conflicting incentives (people who use the meeting for decisions, not status). Reversible: yes — the meeting can be reinstated, so a bounded pilot is low-cost.
Questions (max three): 1) What does success look like at the end of a pilot (e.g., decisions not delayed, update completion rate) and what would make you reinstate the meeting? 2) Who owns the decision and the pilot, and what is the start date? 3) What does the meeting currently do besides status (decisions, escalation, social) that the async format must replace?
Provisional recommendation: pause to test — a time-boxed pilot with a stated reinstatement condition — once Q1–Q3 are answered.

=== Skeptical skill review (summary) ===
The skill is coherent and produced a useful result on A; its arithmetic-feasibility and fatal-flaw framing caught the decisive issue. On B it correctly routed to intake and refused the probability. Weaknesses are mostly scope/ambiguity: length budget vs required content, W0 anchor ambiguity when decision and start dates differ, verification instruction in no-tool contexts, and rebuild constraint when the objective itself is the flaw. Details in findings.
