# Task: two independent fixes

Fix both failing domains under `workspace/`:

1. `src/pricing.py` must apply a percentage discount correctly.
2. `src/labels.py` must produce lowercase hyphenated slugs and collapse repeated whitespace.

The write surfaces are disjoint. Run each focused test and the full suite. Parallel agents are
explicitly authorized when useful, with at most two nested agents at once.
