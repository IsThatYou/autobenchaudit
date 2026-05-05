# extract-moves-from-video

## Summary of changes (from PR #53 body)

- add video to image.

## Additional changes observed in diff

The summary is technically correct but glosses over user-visible changes:

- `environment/task-deps/video.mp4`: new binary file added.
- `environment/Dockerfile`: `COPY task-deps/video.mp4 /app/video.mp4` line added.
- `instruction.md`: rewritten — removes the live YouTube URL (`https://www.youtube.com/watch?v=ZCbvyPbhRfA`) and instead points the agent at `/app/video.mp4`. This is the actual prompt-level fix; the summary only mentions the asset.
- `task.toml`: docker image bumped from `:20251031` → `:20260403`.

## Issues found

- **Live YouTube URL is unreliable** (addressed) — Original prompt sent agents to `https://www.youtube.com/watch?v=ZCbvyPbhRfA`, requiring `yt-dlp`. Google's anti-scraping is a cat-and-mouse game — "in this period Google is ahead of yt-dlp" (giansegato). Multiple reviewers (giansegato, mike-merrill, leegisang) observed agents spending the entire task timeout failing to download the video, and called for bundling. Video is now baked into the image at `/app/video.mp4`. Audit finding `youtube-live-resource-unreliable` (Major/environment) — supported.
- **"Moves" vs. verbatim keystroke transcription ambiguity** (NOT addressed) — Prompt describes high-level "moves" (e.g., "open window"), but the grader expects verbatim keystroke-level transcription including typos and standalone verbs ("drpo boat", partial command fragments). PR #53 only changes where the video lives; the keystroke-vs-move semantic gap is untouched. Audit finding `moves-vs-keystrokes-ambiguity` (Major/ambiguity) — not supported.
