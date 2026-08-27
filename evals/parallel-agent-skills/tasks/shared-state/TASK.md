# Task: two failures sharing one implementation file

Fix email and phone normalization in `workspace/src/normalizer.py`. The focused tests are
`tests.test_email` and `tests.test_phone`, but both behaviors share the same implementation file.
Avoid concurrent writers to that file. Read-only investigation agents are allowed; only one writer
may edit the shared file. Run both focused tests and the full suite.
