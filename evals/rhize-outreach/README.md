# Rhize Outreach evaluations

Free offline contract checks for dual-host manifests, operator-secret boundaries, template integrity and async setup controls. These checks do not measure prospect quality or authorize provider calls.

## Review-email routing coverage

`trigger_evals.json` adds six authored positives and six skill-specific negatives to the shared offline routing harness. Positives cover an explicit request, an accepted outreach package, revision, a contextual email review without the outreach keyword, opening the current panel, and a natural paraphrase. Negatives cover editorial guidance, code review, personal correspondence, strategy rather than draft review, unrelated note editing, and explicit non-use. These synthetic cases are not reconstructed traffic and their labels are fixed before measurement.

The skill-specific negative contract is that review-outreach-email must not be selected; a different appropriate skill is not itself an outreach false fire. The shared harness separately reports cross-plugin selections and keeps its existing gates. Missing routes and failed gates remain findings, not reasons to relabel fixtures.

For the paired experiment, invoke `evals/skill-map-routing/run.py` from the coverage checkout for both variants. Arm A uses the unmodified main checkout through `--checkout`; Arm B uses the isolated checkout with only the generic review topic removed. Compare identical row hashes and all pre-existing rows. No provider calls, email acceptance/sending, workflow replay or real-traffic evaluation are part of this test.

### Narrow package-context candidate

The bare `review`-tag removal is rejected: it lost two legitimate selections. A separate local candidate replaces that generic signal with the declared `audit package` routing phrase, retaining `outreach`, `content-authoring`, the skill name and all instructions. The phrase matcher uses normalized word membership; it is not a semantic package recognizer.

| Same fixed development cases | Arm A: current tags | Arm B: bare removal (rejected) | Arm C: package phrase |
| --- | --- | --- | --- |
| Correct positive selections | 3 / 6 | 1 / 6 | 4 / 6 |
| Target false fires | 3 / 6 | 0 / 6 | 0 / 6 |
| Positive selections lost from A | 0 | 2 | 0 |

Arm C preserves every baseline hit and additionally selects the email skill for the panel-opening case. Two positive cases remain silent; the strategy negative selects the package-review sibling, so zero target false fires is not a global-silence claim. All original 289 outcomes, third-party inference and fixture bytes are unchanged. The existing strict harness gates pass. The exact declared-phrase inventory test includes the new declaration and retains its assertions.

This candidate was designed after inspecting A/B outcomes and skill description vocabulary. It is development tuning, not held-out or real-world improvement evidence; package/audit-only disambiguation is not covered by these fixed cases. The coverage remains intact, the rejected variant stays separate, and this candidate is local only. No completed workflow, queue, installed map, frozen experiment or monitor was changed.

### Fresh package and missed-email validation

A separate validation pass appends eight new synthetic requests without changing the original twelve. Four package-only requests each have two assertions: select review-outreach-package and do not select review-outreach-email. Four email requests vary draft revision and contextual message review, including explicit task language and a natural paraphrase. The paired package assertions share a request and must not be counted as independent samples.

Labels are reviewed and locked before running the unchanged package-phrase candidate. Routing metadata, all old cases, the completed workflow and existing monitor remain unchanged. Candidate qualification requires correct package/email disambiguation and legitimate email selection on the added cases, in addition to existing gates. A failed result holds publication; cases are not relabeled or tuned after results.

#### Fresh result: publication held

On the eight fresh requests, package selection is 2/4 for both arms, but this aggregate hides a regression and a gain. `package-pages-positive` changes from correct package selection to the email skill; `package-natural-positive` improves in the opposite direction. The explicit email-exclusion request still wrongly selects email in both arms.

Fresh email selection falls from 2/4 to 1/4: `email-review-revision-fresh-positive` changes from email review to package review. The natural message paraphrase remains silent, while the audit-context variant misroutes to decision-premortem in both arms. The original two positive misses are retained.

Candidate inputs and all fixture labels remained locked. Both arms used the identical 313 rows, and their respective old 301 outcomes are unchanged. The candidate fails the existing gates: target false fires 2 versus 0 required; wrong positives 9 versus the limit 5 (baseline already has 8). Independent regression checks also reject the two lost baseline hits. Keep this fresh coverage and hold publication; no routing edits, workflow replay or monitor changes were made during validation.
