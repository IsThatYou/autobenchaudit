# rstan-to-pystan

## Summary of changes (from PR #53 body)

- Fix oracle: The oracle created Python 3.10 venv at /opt/py310 but then called python 3 which resolved to system python (3.13). Changed to python to use the venv Python.

## Additional changes observed in diff

- The `python3` → `python` change is in the diff, as described.
- **Undocumented**: A new line `pip install "setuptools<71"` is also added before the `python` invocation. Not mentioned in the summary.

## Issues found

- **Oracle venv activation broken** (addressed) — Oracle created a Python 3.10 venv at `/opt/py310`, but then invoked `python3`, which PATH-resolved to the system Python 3.13 outside the venv. Switched to `python` so it resolves to the venv's interpreter.
- **Stale curl APT pin broke oracle toolchain** (addressed during PR #53 review) — Reviewer (giansegato) observed `curl=8.5.0-2ubuntu10.6` was removed from Ubuntu repos, so `apt install curl` failed, cascading to `add-apt-repository: command not found` (never installed). Fixed in commit `53ff2b8` during the PR.
- **Undocumented `setuptools<71` pin** — Added to solve.sh as a follow-up dependency fix surfaced during further testing, per PR review thread. Not mentioned in the per-task summary.
- **Memory tight; high flakiness unrelated to capability** (NOT addressed) — Reviewer profiled 11.2G peak vs. 8G declared; 57% of OOMs were models that passed on a separate attempt. Oracle uses a memory-saving refactor (moving NxN matrices to local scope so Stan doesn't store them per-draw) that agents porting R code faithfully wouldn't know to apply. Memory not bumped; prompt doesn't tell agents memory efficiency is part of the challenge.
- **Posterior-mean tolerances narrow** (NOT addressed) — Tight bands (sigma ~0.01, beta[2] ~0.04, rho[1] ~0.87) make MCMC variance-driven failures likely. Audit finding `rstan-to-pystan-narrow-test-tolerances` (Minor/test_quality) — not supported.
- **PyStan 3 hyperparameter mapping unspecified** (NOT addressed) — Prompt says "functionally equivalent hyperparameters" without specifying the `num_warmup`/`num_samples`/`num_thin` mapping from rstan. Audit finding `rstan-to-pystan-num-samples-ambiguity` (Minor/ambiguity) — not supported.
