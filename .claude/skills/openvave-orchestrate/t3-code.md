# T3 Code orchestration

Use the shared intake, milestones, state file, gates, and limits in [SKILL.md](SKILL.md). The host instructions here take precedence over the Claude Desktop tool names (`start_session`, `SendMessage`, `wrap_up`, `PushNotification`, `ccd_pr`) in that file and its briefs. A launch for a real feature needs a feature description or an existing feature ID.

## Workers are delegates

Every worker (planner, milestone agent) is a child of this thread, started with `delegate_task`. T3 wakes this thread when a child finishes or stops with a question, so you react to each report without polling. Do not use `t3_thread_launch` for workers: a top-level thread never wakes you, and waiting on it means polling.

- Call `orchestrator_capabilities` once per thread before the first `delegate_task`.
- Start each worker with `mode: "async"`, `isolation: "worktree"`, a `title` (`<short-feature>-plan`, `<NNN>-m<n>`), and `target: {providerInstanceId: "claudeAgent", model: <model>}`: `claude-fable-5-2` for the planner, `claude-opus-5-5` for milestones. Leave `runtimeMode` unset.
- Before each call, write a bold title line and one sentence on what the worker will do. Record its `taskId` and child thread link in `orchestration.md`; mention the thread by its `link`.
- After starting workers, end your turn. Follow the `next` that `delegate_task` returns. Never call `task_status`, `t3_thread_wait`, `sleep` or a watcher to check on a worker.
- When a child's notification arrives, read its final reply with `t3_thread_read` (the first line carries the status) and act as SKILL.md § Phase 1 and § Phase 3 say.
- To answer a worker (planner questions, a hardware result, a decision, a CI result), use `t3_thread_send` to its child thread. A finished child starts a new task in the same thread, with its history; record the new `taskId`. A new review or re-check is never a send: the milestone agent runs Codex itself (§ Review).
- Cancel a worker you replace or no longer need with `task_cancel`, never `t3_thread_interrupt`.

## Workspace and base branch

Resolve the current checkout with `git rev-parse --show-toplevel` and match its exact path to a T3 project's `workspaceRoot` (`t3_project_list`). Record the project ID, the main checkout, and the skill directory in `orchestration.md`.

A delegate's worktree starts from **this checkout's current commit**, on a branch T3 names. You cannot pick the base or the branch name, and this checkout's `main` may be behind `origin/main`. So every brief starts with a branch step that the worker runs first, before reading anything:

```bash
git fetch origin
git switch -c <branch> <base>
```

| Worker | `<branch>` | `<base>` |
|---|---|---|
| Planner | `spec-<short-feature>` | `origin/main` |
| Milestone with base `main` | `<NNN>-m<n>-<slug>` | `origin/main` |
| Milestone on the spec branch or a predecessor | `<NNN>-m<n>-<slug>` | that local branch (branches are shared across worktrees) |

Fill the briefs' path fields with absolute paths:

- `{SKILL_DIR}`: `<main checkout>/.claude/skills/openvave-orchestrate`
- `{SCRATCH_DIR}`: `$HOME/.cache/openvave-orchestrate/<feature>` (outside the repository, so review files never land in a commit)

## Planning

Delegate the [planner brief](briefs/planner.md) on Fable, with `{SPEC_BRANCH}` filled in and the branch step at the top. Omit Claude Desktop session tools and callbacks; the planner returns its status as the first line of its final reply. Relay questions, plan revisions, and the user's approval with `t3_thread_send`. Start development only after the user's plan approval and the planner's `PLAN COMMITTED`.

## Implementation

Delegate the [milestone brief](briefs/milestone.md) on Opus for each milestone, with the branch step at the top and these host changes in the brief:

- Use T3 PR tools (`pull_request_create`, `pull_request_read`, `pull_request_respond`, `pull_request_update`, `ci_logs`) for supported PR operations instead of `gh`. `scripts/pr-state.sh` still uses `gh` for the readiness facts.
- **A delegate never watches a PR or waits for CI** (no `watch_pull_request`, `gh pr checks --watch`, sleep loops or Monitor). Once its review loop is clean and the PR is marked ready, it pushes and ends with the status `CI PENDING`, and its last line is `PR <full URL>, head <SHA>, checks and reviews <state>`.
- Skip Claude Desktop PR tools, notifications, and callbacks. Return the status as the first line of the final reply.

## Review

The milestone agent runs `scripts/codex-review.sh` itself with Bash `run_in_background: true`, then `t3_background_wait` on its task ID before ending the turn. Codex's native reviewer is the only reviewer; the agent does not delegate the review. The agent owns fixing findings and replying on the PR.

## CI (this thread watches)

| Report starts with | Do |
|---|---|
| `CI PENDING` | Record the PR and head. Call `watch_pull_request` on the PR and end your turn. |
| (PR watch wakes you) | Read the checks (`pull_request_read`, `ci_logs` for failures). Green: run SKILL.md's `PR READY` check (`scripts/pr-state.sh`, last Codex review comment on the current head), `unwatch_pull_request`, then **Gate B**. Failing: send the child `CI failed on <head>: <jobs and first error lines>. Fix it, run a Codex review round on the new head, push, and end with CI PENDING.` Keep the watch. After 3 repair rounds, run **Decision needed**. |

Before you end a turn with no worker running and nothing pending, `unwatch_pull_request` every PR you watch.

## Gates

Ask the user in this thread with `AskUserQuestion`, one call per gate. A push notification is optional here.
