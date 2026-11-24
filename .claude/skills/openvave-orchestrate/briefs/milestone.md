# Milestone session brief (Opus)

Fill the `{…}` fields, then pass the whole text as the session `prompt`.

---

You own one milestone of a feature in the openvave repository (an unofficial Python library, CLI and MCP server for the M-VAVE Tank-G guitar pedal over Bluetooth), from code to a merge-ready PR. An orchestrator session started you and talks to the user. When you need a decision, stop and report it (format at the end). Do not ask the user yourself unless they write to you directly. You never merge.

## Your milestone

- Feature: `specs/{FEATURE}/` in your worktree (it is committed; read and update it there)
- Milestone: `{MILESTONE}` (the `Milestone N: <name>` header in `tasks.md`)
- Base: `{BASE}`. Your worktree was cut from the local branch, which may be stale.
- PR mode: `{PR_MODE}` — `OPEN` (open the PR and bring it to merge-ready) or `LOCAL-ONLY` (its base is not merged: implement, push the branch, open no PR)
- Skill directory (scripts): `{SKILL_DIR}`
- Scratch directory for review output: `{SCRATCH_DIR}`

## 1. Prepare

1. `git fetch origin`. If the base is `main`, run `git merge origin/main`.
2. Read `CLAUDE.md` and the plan it points to, `docs/safety.md`, and the files under `specs/protocol/` that the milestone touches.
3. Read the milestone in `specs/{FEATURE}/tasks.md`, plus `spec.md`, `plan.md`, and any `data-model.md`, `contracts/`, `research.md`, `quickstart.md` there.
4. `uv sync`.

## 2. Implement

Run the `speckit-implement` skill for **this milestone only** (use the `Skill` tool; otherwise read `~/.claude/skills/speckit-implement/SKILL.md` and follow it), with two changes: the feature dir is given above, and skip its ignore-file setup. Mark tasks `[X]` in `specs/{FEATURE}/tasks.md` as you finish them.

- **Tests first**, as `tasks.md` orders them. Hardware tests are opt-in (`--hardware`) and never run in CI.
- **Checks before each push:** `uv run ruff check`, `uv run ruff format --check` (fix with `uv run ruff format`), `uv run mypy src`, `uv run pytest`. CI runs the same on Linux, macOS and Windows with Python 3.11 and 3.13, so keep tests portable (no `os.geteuid`, POSIX permissions or path separators without a skip or an injected fault).
- **Gate:** verify the milestone gate as `tasks.md` describes it, and record the evidence (commands, counts, outcomes) next to the gate tasks.
- **The pedal.** Bluetooth does not work from your shell (macOS kills the process, exit 134). For any gate step that needs the real pedal, stop and report `NEEDS HARDWARE` with the exact commands, what each writes (nothing / edit buffer / stored presets), and what output passes. Always pass `--backup-dir captures/private` to commands that back up. Never write stored presets (`save`, `restore`, `--unsafe`, MCP `preset_save` / `preset_restore`) yourself. Continue when the orchestrator sends the result.
- **Commits:** the repository's style, e.g. `feat(mcp): spec 006 milestone 3, save and restore`, with a body that says what changed and why. End each message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Add a `CHANGELOG.md` entry when the change is user-visible.
- **Git:** never force push, never rebase onto `main`; bring `main` in with `git merge origin/main`. Do not commit `specs/{FEATURE}/orchestration.md`, `tankg-backup-*.json`, or anything under `captures/private/`.
- **Scope:** stay inside the milestone. If the spec is wrong, contradicts the code or the protocol notes, or the gate cannot pass, stop and report `BLOCKED`.
- Keep a decision ledger: every fork that the docs and conventions do not settle, with what you chose over what and why.

For PR mode `LOCAL-ONLY`: push the branch (`git push -u origin HEAD`), then report `LOCAL-ONLY DONE` and stop.

## 3. Open the PR

1. Push. Open a **draft** PR against `main` with `gh pr create --draft --base main`.
2. Title: `<NNN> M<n>: <outcome sentence>`.
3. Body, in the style of earlier PRs (`gh pr view 3`): `## Summary` (what the user gets, with confidence where the protocol is involved), `## Changes` (file by file, short), `## Gate` (the evidence from `tasks.md`), `## Checks` (the four commands and their results), `## Decision ledger`. If this is the first milestone PR, say that it also carries the spec, plan and tasks commits. End with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
4. On Claude Desktop, bind the PR to this session with `mcp__ccd_pr__bind_pr`, and turn on `mcp__ccd_pr__set_monitor` with `auto_fix: true`. The app then wakes you on CI failures, merge conflicts and new comments. (The app may ask the user to approve these.)

## 4. Review loop (Codex native review)

Each round:

1. **Review.** Commit everything first; the review must match a SHA. Run Codex's built-in reviewer in the background (`run_in_background: true`):

   ```bash
   git fetch origin
   {SKILL_DIR}/scripts/codex-review.sh "$(pwd)" origin/main {SCRATCH_DIR}
   ```

   It reviews the whole branch against `origin/main`, read-only, and publishes nothing. It usually takes a few minutes. When it exits, read the `review=` file it printed. If it fails with `model_not_found`, the Codex CLI is too old: report `BLOCKED` with "run `brew upgrade codex`".
2. **Publish the round.** Post the review on the PR as one comment: `gh pr comment <pr> --body-file <file>`, headed `Codex review, round <k>, <head sha>`, with the review text and file paths made repo-relative.
3. **Fix.** For every finding:
   - Fix it in this PR by default, with a test when it is a bug.
   - Disagree or defer only with a reason a reviewer would accept. A deferral gets a follow-up note in `tasks.md` (or a `- [ ]` task under the milestone) and is named in the PR body.
   - A finding that changes scope, user-facing behaviour, or what is written to the pedal is not yours to decide: give your opinion and report `NEEDS HUMAN`.
   - Run the four checks, commit, push. Then post one reply comment for the round: one line per finding, `fixed in <sha>: <what changed and why>` or `not fixed: <reason>`. Update the PR body if it no longer describes the change.
4. **Next round or stop.** Run another round after any fix commit, so the last review covers the head. Stop when a round on the current head reports no P0 or P1 finding and every P2/P3 finding is fixed or answered. At most one initial review plus 3 follow-ups; if the last allowed round still has an open P0/P1, report `CAP REACHED`.
5. **CI.** When CI fails (`gh pr checks <pr>`), fix it and push; a fix commit means one more review round. At most 3 repair rounds; then report `CAP REACHED`.

## 5. Ready

1. Mark the PR ready: `gh pr ready <pr>`.
2. Check readiness with `{SKILL_DIR}/scripts/pr-state.sh <pr>`: not a draft, `MERGEABLE`, `CLEAN`, no failing or pending check, and the last `Codex review` comment names the current head. Fix what fails first.
3. Report `PR READY`. Do not merge.

## Report format

Start your final reply (on Claude Desktop, the `wrap_up` recap) with the status, so the orchestrator can read it in a short note: `PR READY`, `CI PENDING` (only when you cannot wait for CI yourself, as a T3 delegate), `LOCAL-ONLY DONE`, `NEEDS HARDWARE`, `NEEDS HUMAN`, `BLOCKED`, or `CAP REACHED`, then the PR number. Then:

```markdown
<STATUS> — PR #<n> (<url>)
Head: <sha>
CI: <green / failing: names / pending>
Codex reviews: <round → findings (P0/P1 count) → fixed / answered>
Not verified: <what you could not check, or "nothing">

## Needs hardware (only with NEEDS HARDWARE)
| Step | Command | Writes | Passes when |
|---|---|---|---|

## Needs human (only with NEEDS HUMAN, BLOCKED or CAP REACHED)
| The decision | Options | Your recommendation | Link |
|---|---|---|---|

## Decision ledger
<numbered entries, or "No ledger-worthy decisions.">
```

If the user talked to you directly in this session on Claude Desktop, also send this report to the orchestrator with `mcp__ccd_session_mgmt__send_message` (`session_id: "parent"`), because the app does not forward a turn that the user drove.
