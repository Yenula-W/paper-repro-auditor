# Adoption-ready bar (applies to all 5 tools)

A tool is "ready for lab adoption" only when every item below is met and written up in its `EVALUATION.md`
with numbers. If an item can't be met, say so plainly in `EVALUATION.md`; don't paper over it.

1. **Never crashes on messy input.** Add robustness tests: empty input, binary/non-UTF8 files, malformed
   JSON/XML/YAML/notebooks, corrupt archives/images, huge files, symlink loops, unicode paths, missing
   permissions. Any crash found gets fixed at the root + a regression test.
2. **Installs cleanly from GitHub** (`pip install git+https://github.com/Yenula-W/<repo>`) in a fresh venv on
   Python 3.9 (macOS system Python; support it unless a hard dependency forbids it, and document why),
   3.12 and 3.13. Copy-paste the README quickstart in a fresh venv and confirm it works verbatim.
3. **Held-out real-world run.** Run on at least 20 real public inputs that were NOT used during development,
   across several fields/sources. Record crashes, runtime and output size per input. Zero crashes required.
4. **Precision check by hand.** Take a stratified random sample of at least 50 findings/outputs (at least
   3 per check/rule type) from the held-out run and judge each one against the real source as correct /
   wrong / debatable. Target at least 90% correct overall and no check type below 80%. Every wrong one: fix the
   rule or downgrade it, add a regression test, re-run, and re-measure.
5. **Never invents or overstates.** Messages must be accurate and polite enough to send to the author.
   No "error" claims for things that are only recommendations.
6. **CI green on GitHub** (tests on 3.9 or the lowest supported version, and on 3.12).
7. **`EVALUATION.md`** in the repo: what was tested, inputs used (with links), precision table per check,
   crashes found and fixed, known limitations. Commit and push.
