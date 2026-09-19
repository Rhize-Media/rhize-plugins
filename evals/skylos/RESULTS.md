# Recorded local evaluation

Run on 2026-09-19 (host clock), macOS, Python 3.12.14, Skylos 4.38.0.
[Machine-readable results](results.json) bind the corpus and adapter hashes. All 13 Arm A inventories
and 13 sandboxed Arm B scans ran; every consumed packet was accepted and every source tree stayed
unchanged. The separate isolation sentinel passed source-read, outside-content denial, source-write
denial, network denial and scratch-write checks.

| Fixture | Arm B status | Exact expected signals |
|---|---|---|
| python-clean | no_findings | No seeded target |
| python-phantom | findings | SKY-L012: detected |
| python-stub | findings | SKY-L026: missed |
| python-disabled-tls | findings | SKY-L011: detected |
| python-missing-timeout | findings | SKY-L031: detected |
| python-swallowed-error | findings | SKY-L030: detected |
| python-weakened-test | findings | SKY-A101: detected |
| python-no-regression-test | incomplete | SKY-A102: missed |
| python-unrelated-test | incomplete | SKY-A102: missed |
| python-dynamic-reference | incomplete | No seeded target |
| typescript-clean | no_findings | No seeded target |
| typescript-missing-export | findings | SKY-L023: missed |
| typescript-clean-change | incomplete | No seeded target |

The strict rule-and-line scorer matched **5 of 9** predeclared targets. Two mismatches were corpus
expectation errors retained transparently: the stub was flagged at line 2 rather than declared line 1;
the missing TypeScript export was flagged as SKY-L012 rather than declared SKY-L023. Manual inspection
confirms those two intended defects were identified. Neither no-regression-test nor unrelated-test
produced SKY-A102. These are missed targets; do not use the test-impact heuristic as coverage proof.

The unchanged Python/TypeScript controls had no findings. The changed TypeScript and dynamic Python
cases remained incomplete. Seven cases had findings, four were incomplete and two had no findings.
Unresolved behavior reasons remained present alongside static findings. No static result became a
test-execution verdict, deletion instruction or release approval.

Arm A has no Skylos defect detector, so all nine matching-rule targets are absent by design. This
comparison establishes that the optional adapter provides additional static signals; it does not
establish superiority to complete Devflow review, precision on real repositories, productivity gains
or statistically meaningful timing improvement. Durations are recorded observations from one local
run, partly overlapping unit-test execution. Re-run on a new adapter or scanner version.
