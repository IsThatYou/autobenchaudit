# install-windows-3.11

## Summary of changes (from PR #53 body)

- Update task description to explicitly specify that a QEMU monitor socket needs to be created at the path hardcoded in tests
- Update tests to use `pathlib.Path.is_socket()` to test the QEMU monitor socket rather than a hardcoded list of VGA flags. `test_windows_keys_with_visual_feedback` already verifies the display works via screenshots.

Related PRs: [PR #1400](https://github.com/harbor-framework/terminal-bench/pull/1400), [PR #1395](https://github.com/harbor-framework/terminal-bench/pull/1395).

## Additional changes observed in diff

Beyond what the summary describes, `tests/test_outputs.py` also includes:

- `qemu_pid` fixture: now filters out **zombie/defunct processes** and returns the first PID with a readable `cmdline`. Previously it just returned `pids[0]`.
- `cmdline` fixture: changed assertion from `cmdline_result.returncode == 0` to `assert cmdline_str` (i.e., asserts non-empty cmdline). Stripping whitespace also added.

These hardening changes aren't called out in the per-task summary but they materially affect which test outcomes count as "QEMU running."

## Issues found

- **QEMU monitor socket path hardcoded in test but unspecified in prompt** (addressed by tb#1400) — Test required `/tmp/qemu-monitor.sock`, but the prompt didn't state the path. Agents using any other config format (e.g., `-qmp unix:/path`, `-chardev socket,path=...`) would fail. Prompt now specifies the path; test uses `pathlib.Path.is_socket()`. Audit finding `f1_hardcoded_monitor_socket_path` (Major/ambiguity) — supported.
- **VGA flag requirement hardcoded in test but unspecified in prompt** (addressed by tb#1395) — Test previously required a specific VGA flag (`cirrus`, `std`, or `vga`) in the QEMU command line, but the prompt never mentioned a VGA requirement. Hardcoded flag list replaced with a real socket existence check and coverage via `test_windows_keys_with_visual_feedback` screenshots.
- **`qemu_pid` returned zombie/defunct processes** (addressed) — Previous fixture returned `pids[0]`, which could be a defunct process with no cmdline. Now filters zombies and returns the first PID with a readable `cmdline`.
- **Brittle visual-feedback test coupled to boot timing** (NOT addressed) — `test_windows_keys_with_visual_feedback` still requires one of five hardcoded key events to change ≥10% of VNC pixels within ~2 seconds. This couples pass/fail to boot timing and a hidden key set. PR #53 cites this test as justification for dropping the VGA-flag check but doesn't modify the test itself (no readiness probe, no wider threshold, no prompt mention of the key set). Audit finding `f2_brittle_visual_feedback_test` (Minor/test_quality) — not supported.
