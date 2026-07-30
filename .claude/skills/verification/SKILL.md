---
name: verification
description: Verify a change is genuinely correct — run the test suite, read the diff, and confirm no test was weakened just to make things pass. Reports PASS or FAIL with the evidence attached. Use after finishing an edit, before committing, or whenever the user asks to "verify", "check", or "make sure this passes honestly".
---

# Verification

Confirm that a change actually works — not that it merely turned the bar green. The core risk this skill guards against is a green suite bought by gutting the tests: deleted assertions, `xfail`/`skip` slapped on failing cases, tolerances loosened, expected values edited to match buggy output, mocks that swallow the thing under test.

## Procedure

Run these steps in order. Do not stop early on a failure — collect all the evidence, then report.

### 1. Establish the diff

Capture what changed. Prefer the working diff against the base branch:

```
git diff --stat $(git merge-base HEAD main)...HEAD
git diff $(git merge-base HEAD main)...HEAD
```

Also capture uncommitted work:

```
git status --short
git diff            # unstaged
git diff --cached   # staged
```

Read the full diff, not just the stat. You need the actual line changes to judge step 3.

### 2. Run the tests

Run the full suite from the repo root:

```
uv run pytest -v
```

Capture the complete output — pass/fail counts, skips, xfails, warnings, and any tracebacks. If the suite is large, still run all of it; a targeted subset is not sufficient evidence for a PASS verdict. Note the exit code.

### 3. Audit the diff for weakened tests

Go through every change under `tests/` (and any inline/doctest assertions) and flag anything that reduces what the suite proves. Look specifically for:

- **Deleted or commented-out assertions** — fewer checks than before.
- **New `@pytest.mark.skip`, `@pytest.mark.xfail`, `pytest.skip(...)`, or `return` early** in a test that previously ran.
- **Loosened comparisons** — `==` → `approx` with a wide tolerance, tightened bounds relaxed, `assert x` → `assert True`, ranges widened.
- **Expected values edited to match new output** — legitimate only when the spec changed; suspicious when the change is to production logic and the expectation was simply rewritten to whatever the code now emits.
- **Mocks/patches that stub out the code under test**, or fixtures changed so a path is no longer exercised.
- **Tests deleted entirely**, or renamed so they no longer collect (e.g. dropped `test_` prefix).
- **Reduced parametrization** — cases removed from `@pytest.mark.parametrize`.
- **Assertions moved into unreachable branches** or wrapped in `try/except: pass`.

For each production-code change, ask: is there a test that would fail if this change were wrong? If a behavior changed but no test covers it, that is a coverage gap worth noting even when the suite is green.

A test change is legitimate when it reflects a real, intended spec change and still asserts the new correct behavior meaningfully. Judge intent from the diff and the user's stated goal — when unclear, flag it rather than assume.

### 4. Report

Emit a verdict with evidence. Use this shape:

```
## Verification: PASS | FAIL

**Tests:** <N passed, M failed, K skipped/xfailed> (exit code <n>)
**Diff reviewed:** <files touched, key test files>

### Test evidence
<the pytest summary line(s) and any failing tracebacks — verbatim>

### Test-integrity audit
<for each flagged item: file:line, what changed, why it may weaken coverage>
<or: "No weakened tests found.">

### Verdict
<one-paragraph justification>
```

**FAIL if any of these hold:**
- Any test fails, or the suite errors on collection.
- A test was weakened (per step 3) in a way not justified by an intended spec change.
- A production behavior changed with no test covering it, when the change's correctness depends on that behavior.

**PASS only when** the full suite is green AND every test change is justified AND the change is meaningfully covered.

Do not soften a FAIL. Report failing output and weakened-test findings plainly, with file:line references so they're clickable. Attach the raw pytest output as evidence rather than paraphrasing counts.
