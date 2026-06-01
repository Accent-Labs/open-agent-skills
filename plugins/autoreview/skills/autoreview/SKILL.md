---
name: autoreview
description: Use this skill to review staged code changes before committing when the autoreview pre-commit gate blocks a plain `git commit`, or when the user asks for "autoreview", "review my staged changes", "review before commit", "pre-flight review", or a multi-agent pre-commit review. It launches the bundled reviewer profiles over staged diff and staged context, requires strict JSON reviewer results with `APPROVED`, `COMMENTED`, `CHANGES_REQUESTED`, or `NEEDS_CONTEXT`, fixes or resolves blocking feedback, writes an authorizing marker only for non-blocking final outcomes, and then retries a plain staged commit.
---

# Autoreview

Review the staged change from multiple perspectives, resolve blocking feedback, then allow one plain staged commit.

This skill is normally triggered by the deterministic gate: a `PreToolUse` hook blocked a plain `git commit` with exit 2 and asked you to run autoreview. Follow this workflow exactly.

Resolve `${ROOT}` before running plugin scripts. Prefer the absolute plugin path printed in the gate directive. If that is absent, use the nearest ancestor directory that contains `scripts/gate.py` and `agents/`.

---

## When To Run

- The gate blocked a commit and its directive told you to invoke this skill.
- The user explicitly asks for a staged/pre-commit autoreview.

If the gate says the commit mode is unsupported, do not review yet. Stage changes explicitly with `git add ...`, then run a plain `git commit`. Unsupported forms include `-a`, `-am`, `--amend`, `--patch`, `--interactive`, pathspec commits, repo/cwd/index redirects, nested shell execution, and compound commands that change what gets committed.

## Inputs

- Staged diff from `git diff --cached`.
- Changed paths from staged index commands such as `git diff --cached --name-only`.
- Staged file context, gathered from the index with commands such as `git show :path`, not from live working-tree reads.
- For merges, include the conflict scope from staged index data plus merge parent identifiers when available.
- Reviewer profiles from `${ROOT}/agents/*.md`; the filename stem is the reviewer id.

## Procedure

1. **Gather staged material.**
   Run `git diff --cached` and collect changed paths. If nothing is staged, tell the user and stop.

2. **Gather staged context by value.**
   For each relevant changed source file, collect focused excerpts from the staged index. Prefer:

   ```sh
   git show :path
   ```

   Use staged/base commands only. Do not ask reviewers to inspect live files. If context is too large, batch by file and insert explicit markers such as `[staged context truncated: 4 hunks omitted]`.

3. **Launch reviewers in parallel.**
   Start one isolated worker per file in `${ROOT}/agents/*.md`. Use the host tool's available worker or subagent mechanism. Pass each worker:
   - the full reviewer profile content,
   - `<staged_diff>...</staged_diff>`,
   - `<staged_context>...</staged_context>`,
   - any explicit truncation markers.

4. **Require strict reviewer JSON.**
   Each reviewer must return exactly one JSON object with:

   ```json
   {
     "reviewer": "correctness",
     "outcome": "APPROVED | CHANGES_REQUESTED | COMMENTED | NEEDS_CONTEXT",
     "summary": "one sentence",
     "feedback": [
       {
         "severity": "critical | high | medium | low | info",
         "path": "relative/path",
         "line": 1,
         "title": "one line",
         "impact": "concrete effect",
         "evidence": "staged diff or staged context that proves it",
         "recommendation": "minimal fix or precise instruction",
         "blocking": true
       }
     ]
   }
   ```

   Treat invalid JSON as `NEEDS_CONTEXT`. Treat `APPROVED` with feedback, `COMMENTED` with blocking or medium/high/critical feedback, and `CHANGES_REQUESTED` without blocking feedback as invalid reviewer output.

5. **Aggregate mechanically.**
   - Any `CHANGES_REQUESTED` means the final outcome is `CHANGES_REQUESTED`.
   - Else any `NEEDS_CONTEXT` means refresh staged context and rerun that reviewer once. If it still needs context, stop without committing.
   - Else any `COMMENTED` means the final outcome is `COMMENTED`.
   - Else the final outcome is `APPROVED`.

6. **Resolve blocking feedback.**
   Fix true defects and re-stage fixes. If a blocking item is false positive, record a short dispute with staged evidence and rerun the reviewer. If blocking feedback remains after three rounds, stop and tell the user the change should be split or handled manually.
   Track each reviewer feedback item you addressed and the corresponding fixes; the follow-up commit message must list them when review feedback caused code or test changes.

7. **Write an authorizing marker only for non-blocking final outcomes.**
   Only `APPROVED` and non-blocking `COMMENTED` may proceed. Run:

   ```sh
   python3 "${ROOT}/scripts/gate.py" mark --payload '<JSON>'
   ```

   The payload must be the aggregate JSON object:

   ```json
   {
     "outcome": "APPROVED",
     "counts": { "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0 },
     "feedback": [],
     "reviewers": [
       { "reviewer": "correctness", "outcome": "APPROVED" }
     ]
   }
   ```

   The marker writer rejects `CHANGES_REQUESTED`, `NEEDS_CONTEXT`, old verdict names, malformed JSON, mismatched counts, and blocking feedback.

8. **Retry the commit.**
   Run one plain `git commit` for the staged tree. Do not retry unsupported command forms. The marker is keyed to the staged tree and is consumed once.
   If this autoreview cycle included fixes for reviewer feedback, include a commit message body that lists the concrete feedback and fixes made. Keep the original commit subject if one was already intended, and add a short body such as:

   ```text
   Autoreview:
   - correctness: feedback about missing nil handling; fixed by guarding the parsed value before use.
   - security: feedback about unescaped HTML; fixed by rendering through the existing sanitizer.
   ```

## Output Contract

Report:

```text
Verdict: APPROVED | COMMENTED | CHANGES_REQUESTED | NEEDS_CONTEXT
Summary: <=3 sentences
Counts: critical/high/medium/low/info
Feedback: [ {reviewer, severity, path, line, title, impact, evidence, recommendation, blocking} ... ]
```

Keep the user-facing summary concise. Include full feedback only when there are comments or requested changes.

## Validation

- Dry-run the gate:

  ```sh
  echo '{"cwd":"'"$PWD"'","tool_input":{"command":"git commit -m test"}}' | python3 "${ROOT}/scripts/gate.py"; echo "exit=$?"
  ```

- Run deterministic tests and eval fixtures:

  ```sh
  sh "${ROOT}/scripts/run_tests.sh"
  ```

## Anti-Patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Manufacturing findings to look thorough | Review theater hides real defects | Return `APPROVED` when there is no concrete issue |
| Passing only a path to the diff | Reviewers can read the wrong state | Pass staged diff and staged context by value |
| Reading live working-tree files | Unstaged edits can contaminate the review | Use staged index commands such as `git show :path` |
| Silently truncating context | Hidden blind spot in review evidence | Insert explicit truncation markers and use `NEEDS_CONTEXT` if necessary |
| Writing a marker for blocking feedback | The next commit can ship unresolved defects | Write markers only for `APPROVED` or non-blocking `COMMENTED` |
| Retrying an unsupported commit mode | The marker does not authorize that command shape | Stage explicitly and run one plain `git commit` |
