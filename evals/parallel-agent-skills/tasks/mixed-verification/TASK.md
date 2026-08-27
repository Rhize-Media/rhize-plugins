# Task: parallel focused verification, sequential final gate

Run `tests.test_math` and `tests.test_text`; they are independent and may run in parallel. After
both complete, run the full suite as the dependent integration gate. Do not edit the workspace.
Parallel agents are explicitly authorized when useful, with at most two nested agents at once.
