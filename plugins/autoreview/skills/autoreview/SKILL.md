---
name: autoreview
description: Use this skill to review staged code changes before a commit when the autoreview pre-commit gate has blocked a `git commit` and asked you to run it, or when the user asks to "review my staged changes", "autoreview", "review before commit", or "pre-flight review". It spawns parallel perspective reviewers (correctness, security, conventions) over the staged diff, aggregates findings into a verdict (PASS / PASS_WITH_ISSUES / FAIL), and drives a fix-or-dispute loop before writing a pass-marker and re-committing.
---

# Autoreview

Review the staged change from multiple perspectives, address real defects, then let the commit proceed.

This skill is normally triggered by the autoreview gate: a `PreToolUse` hook blocked your `git commit` (exit 2) with a directive to run autoreview. Follow these steps exactly. `${ROOT}` below means `${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}` (this plugin's install dir).

---

## When to run

- The gate blocked a commit and the stderr directive told you to invoke this skill, OR
- The user explicitly asks for a pre-commit/staged review.

If the gate said the commit mode is unsupported (`-a`/`-am`/`--amend`/pathspec), do NOT review — stage your changes explicitly (`git add ...`) and run a plain `git commit`. No marker is written for those forms.

## Inputs

- The **staged diff**: `git diff --cached`. For a merge the directive references the conflict scope — also gather `HEAD`, the `MERGE_HEAD` parent OIDs, the conflicted-path list from `MERGE_MSG`, and `git diff AUTO_MERGE` when available.
- The **reviewers** in this plugin's `agents/*.md`. Each is a Claude Code native subagent definition (frontmatter `name`/`description`/`model`/`tools` + a prompt body). In v1 all reviewers run and cannot be disabled. The reviewer ID is the filename stem.

## Procedure

1. **Gather the diff.** Run `git diff --cached` and capture the changed file paths. If empty, report nothing is staged and stop.
2. **Detect the host tool.** Run `python3 "${ROOT}/scripts/detect_tool.py"`. It prints a JSON object including `supportsCustomSubagents`.
3. **Spawn the reviewers in parallel**, one per `agents/*.md`, each in its own isolated context:
   - **If `supportsCustomSubagents` is true** (Claude Code): invoke the bundled native subagents by name — `autoreview:correctness`, `autoreview:security`, `autoreview:conventions` — via the Agent/Task tool, all in one message so they run concurrently. The native `model:` field applies automatically.
   - **Else** (Codex / Gemini / generic): for each `agents/<id>.md`, read the file and spawn a generic/worker subagent with the **full file content inline**, prefixed with:

     > "This is a subagent definition. Ignore the YAML frontmatter between the `---` markers; treat the prompt body below it as your instructions."

     Choose the spawn model from this neutral guidance: **security and correctness → your strongest reasoning model; conventions → your fastest model.**
4. **Pass the diff by value, fenced and labeled.** Give each reviewer the scoped diff inline in a delimited block: `<staged_diff>...</staged_diff>` (and for merges a separate `<conflict_scope_diff>...</conflict_scope_diff>`). Never hand a reviewer a path to read the diff. If the diff exceeds the context budget, truncate or batch by file **explicitly** with a visible `[diff truncated: N hunks omitted]` marker — never clip silently.
5. **Collect findings.** Each reviewer returns Findings (severity, file:line, title, why, suggestedFix) and a `VERDICT:` line. Discard anything that is style/docstring polish (those are Suggestions, not Findings).
6. **Derive the verdict mechanically:**
   - `FAIL` if any finding is `critical`. Before accepting a `critical`, re-verify that single finding once with your strongest model; drop it if the re-verify does not confirm a real, exploitable/breaking defect.
   - else `PASS_WITH_ISSUES` if any findings remain
   - else `PASS`
7. **Act on findings (≤2 rounds; 3 for substantive bugs):** fix, dispute-in-writing (state why it is a false positive), or defer-with-TODO. Keep a short dismissed-findings memo (file:line + reason) so re-runs don't re-raise the same item. If after round 3 substantive findings remain, tell the user the change is too large and should be split, and stop without committing.
8. **Re-stage** any fixes (`git add ...`).
9. **Write the marker and re-commit.** Run:

   ```sh
   python3 "${ROOT}/scripts/gate.py" mark --payload '<JSON>'
   ```

   where `<JSON>` is `{"verdict":"...","counts":{...},"disputed":[...],"deferred":[...]}`. Then complete the commit with a **plain `git commit`** — re-issue the original command only if it was already a plain staged commit. **Never** re-issue an `-a`/`-am`/`--amend`/pathspec form: those are unsupported modes that never reach this skill, and re-issuing one would just be blocked again — stage explicitly and use a plain `git commit`. The gate finds the matching marker (keyed to the staged tree, plus merge parents for merges) and allows the commit. Print a concise summary before committing when the verdict is not `PASS`.

## Output contract

```
Verdict: PASS | PASS_WITH_ISSUES | FAIL
Summary: <=3 sentences, imperative — what you fixed / disputed / deferred.
Counts: critical/high/medium/low/info
Findings: [ {reviewer, severity, file:line, title, why, suggestedFix} ... ]   # appendix
```

`Summary` is the primary thing the user reads; findings are an appendix. Severity → SARIF mapping (future export): critical/high → error, medium → warning, low/info → note.

## Validation

- Dry-run the gate without committing:

  ```sh
  echo '{"cwd":"'"$PWD"'","tool_input":{"command":"git commit -m test"}}' | python3 "${ROOT}/scripts/gate.py"; echo "exit=$?"
  ```

  Exit 0 = would allow; exit 2 = would block (directive on stderr).
- Check tool detection: `python3 "${ROOT}/scripts/detect_tool.py"`.
- Run the gate's tests: `sh "${ROOT}/scripts/run_tests.sh"`.

## Anti-Patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Manufacturing findings to look thorough | Trains everyone to ignore the gate (review theater) | Apply the quality bar; return CLEAN when clean |
| Passing the diff as a file path | Reintroduces a runtime-read failure mode | Pass the diff by value, fenced and labeled |
| Silently truncating an oversized diff | Hidden blind spot in the review | Truncate/batch explicitly with a visible marker |
| Writing the marker before fixes are staged | Marker keys to a tree that won't match the commit → re-review loop | Stage fixes first, then `mark`, then commit |
| Using `--no-verify` to escape the loop | Bypasses review silently | Address or dispute findings instead |
| Reviewing an unsupported commit mode | Marker won't match the effective commit content | Stage explicitly and use a plain `git commit` |
