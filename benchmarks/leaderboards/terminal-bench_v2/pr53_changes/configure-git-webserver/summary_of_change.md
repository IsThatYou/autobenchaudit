# configure-git-webserver

## Summary of changes (from PR #53 body)

- Fix oracle solution: Task description promised to handle auth, but tests assumed a specific format (updated tests so it's now as promised)

Related PRs: [PR #39](https://github.com/harbor-framework/terminal-bench-2/pull/39).

## Additional changes observed in diff

The summary is somewhat understated. The actual changes:

- `solution/solve.sh`: switched the user from `git` (with password `password`) to `user` (no password set, key-only). Removed all `~git/.ssh/authorized_keys` setup from solve.sh (now done in verify.sh).
- `tests/verify.sh`: rewrote test from an `expect`-based password-auth flow to an SSH-key flow. Verifier now generates an ed25519 key, drops it into `/home/user/.ssh/authorized_keys`, and uses standard `git clone user@localhost:...`. Also removed the wget fallback branch and `expect` package install.
- Net effect: removes ambiguity around how auth must be configured (no longer relies on a specific password), and the verifier no longer prescribes `expect`.

## Issues found

- **Prompt vs. test contract mismatch on auth** (addressed by tb2#39) — Prompt stated "I'll set up login, you don't have to worry about that", but the grader silently required password-based SSH to user `git` with password `password`. Any agent that configured a different (even better) auth scheme would fail. Verifier now provisions its own ed25519 key and connects as `user` via SSH-key. Audit finding `configure-git-webserver-1` (Major/ambiguity) — supported.
- **Oracle user vs. prompt user mismatch** (addressed by tb2#39) — Prompt says `user@server:/git/server`; oracle was using `git` account. Oracle now uses `user`.
- **Verifier doesn't reset web root before `curl` check** (NOT addressed) — Test can pass on the agent's own leftover self-test deployment at `http://localhost:8080/hello.html` even if the grader's SSH push never succeeds. PR #53's rewrite addresses auth but the leftover-state pitfall is independent and untouched. Audit finding `configure-git-webserver-2` (Major/test_quality) — not supported.
