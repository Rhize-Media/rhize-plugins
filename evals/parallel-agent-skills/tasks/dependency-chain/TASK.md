# Task: contract change followed by consumer update

Change the `UserRecord` contract in `workspace/src/schema.py` from `display_name` to `full_name`,
then update `workspace/src/renderer.py` to consume the new contract. This is a dependency chain:
the contract must be correct before its consumer is verified. Run `tests.test_schema`,
`tests.test_renderer`, and the full suite. Parallel read-only investigation is allowed, but writes
must follow the dependency order.
