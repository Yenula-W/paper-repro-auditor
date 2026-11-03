# Ship bar (on top of ADOPTION_BAR.md)

A tool ships when all of these hold on its final commit:

1. **Two untouched rounds in a row pass.** Each round uses new real inputs, none used in any earlier round. Hand-judge 50+ findings and record the first-run numbers before changing anything. Each round needs ≥90% overall precision, no check type below 80%, 0 crashes and 0 overstated claims.
2. **No code change between those two rounds.** If a round fails, fix the problem at its root and add a regression test. The streak then restarts at zero.
3. **Clean install on the final commit.** Install from GitHub in fresh venvs on Python 3.9, 3.12 and 3.13. Run the README quickstart word for word.
4. **Tests pass both with and without optional extras installed.** Tests for optional extras skip cleanly when the package is missing.
5. **CI is green, and EVALUATION.md records every round.**

Cap: 3 more rounds per tool. If a check type still fails after that, make it opt-in or remove it. Do not ship it on by default.
