# Rhize Outreach evaluations

Free offline contract checks for dual-host manifests, operator-secret boundaries, template integrity and async setup controls. These checks do not measure prospect quality or authorize provider calls.

## Review-email routing coverage

`trigger_evals.json` adds six authored positives and six skill-specific negatives to the shared offline routing harness. Positives cover an explicit request, an accepted outreach package, revision, a contextual email review without the outreach keyword, opening the current panel, and a natural paraphrase. Negatives cover editorial guidance, code review, personal correspondence, strategy rather than draft review, unrelated note editing, and explicit non-use. These synthetic cases are not reconstructed traffic and their labels are fixed before measurement.

The skill-specific negative contract is that review-outreach-email must not be selected; a different appropriate skill is not itself an outreach false fire. The shared harness separately reports cross-plugin selections and keeps its existing gates. Missing routes and failed gates remain findings, not reasons to relabel fixtures.

For the paired experiment, invoke `evals/skill-map-routing/run.py` from the coverage checkout for both variants. Arm A uses the unmodified main checkout through `--checkout`; Arm B uses the isolated checkout with only the generic review topic removed. Compare identical row hashes and all pre-existing rows. No provider calls, email acceptance/sending, workflow replay or real-traffic evaluation are part of this test.
