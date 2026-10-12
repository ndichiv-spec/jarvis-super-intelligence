# Ruff debt baseline

Measured with Ruff 0.16.1 using `python -m ruff check . --statistics`:
**15,820 findings** at the archived pre-recovery `HEAD` and **14,964 findings**
after the recovery changes (Ruff exits 1 while findings remain). The reported
historical count of 15,803 was not reproduced in either measurement.

All configured findings are lint diagnostics; Ruff does not assign separate
severity levels. The largest rule groups were:

| Rule | Count |
|---|---:|
| W293 | 4,720 |
| UP006 | 3,729 |
| UP045 | 1,673 |
| F401 | 955 |
| UP035 | 572 |
| I001 | 547 |
| B008 | 449 |
| ARG001 | 243 |
| RUF100 | 224 |
| ARG002 | 169 |
| UP037 | 123 |
| UP017 | 111 |
| F841 | 104 |

The largest file groups included `jarvis_backend/routers/browser.py` (402),
`jarvis_backend/routers/control_plane.py` (364),
`frontend/dashboard/searchable_index.py` (270), and
`drive_engine/automated_testing.py` (259). The full local Ruff JSON report is
kept outside the repository; no generated report is checked in.

Correctness rules such as undefined names and unused imports take priority
over formatting and modernization. Remediation proceeds by changed backend
and security files first, then high-count maintained modules in small batches.
Do not auto-format the whole repository or suppress whole directories.

CI runs `scripts/check_ruff_debt.py` against each pull request's base revision.
It compares Ruff finding counts per rule for each changed Python file; existing
files may not increase their debt, and new Python files must be Ruff-clean. If
the base version of a file has a syntax error, the gate checks the changed
lines instead, so correcting that syntax error does not misclassify latent
findings elsewhere in the file as newly introduced. The repository-wide
baseline is reported honestly and is not treated as clean; lower it through
reviewed fixes, not ignore rules.
