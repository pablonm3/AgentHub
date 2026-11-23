---
name: fix_ai_comments
description: Rewrite or remove unhelpful AI-style ("claudy") code comments introduced in the current branch relative to a user-provided baseline, or only in uncommitted changes. Use for comment cleanup regardless of which coding agent or person wrote them.
---

# Fix AI comments

Edit eligible comments directly. Judge usefulness from the code; do not claim to detect authorship. Preserve behavior and useful explanations of constraints, tradeoffs, and failure modes.

## Choose the scope

Use the mode specified in the request. A supplied baseline implies baseline mode; a request for uncommitted changes implies uncommitted mode. If neither is specified, ask the user to choose:

- **Baseline branch:** committed changes introduced on the current branch since its merge base with a user-provided baseline.
- **Uncommitted changes:** the current working-tree changes relative to HEAD, including staged and unstaged changes plus non-ignored untracked source files.

If baseline mode lacks a baseline, ask for it. Do not guess a branch, combine modes, or begin edits before the scope is resolved. Respect any additional file restrictions.

## Identify eligible comments

Read applicable repository instructions, then inspect Git status and capture the initial diff so existing user edits can be distinguished from your edits. Run commands from the repository root. Use zero-context diffs to locate changed lines and read surrounding code separately.

### Baseline branch

Resolve the supplied ref as a commit using `git rev-parse --verify --end-of-options "${baseline}^{commit}"`, then compute `git merge-base "$baseline_commit" HEAD`. Treat the baseline as data: quote it, and never interpolate it into executable shell text. If the ref is unavailable or there is no merge base, ask for a valid baseline; do not substitute another comparison.

Inspect `git diff --no-ext-diff --no-textconv --find-renames --unified=0 "$merge_base" HEAD --`. This excludes baseline-only changes and uncommitted changes. Read the candidate code from HEAD to avoid accidentally reviewing local edits as branch changes.

Apply cleanup to the working tree. Map candidate comments to their current locations before editing. Leave uncommitted-only comments out of scope. If local edits overlap a candidate comment or alter the behavior its explanation depends on, skip that candidate and report the conflict. Never overwrite those edits or check out files to make them match HEAD.

### Uncommitted changes

Inspect `git diff --no-ext-diff --no-textconv --find-renames --unified=0 HEAD --` for the net tracked changes, and enumerate non-ignored untracked files with `git ls-files --others --exclude-standard -z`. Read untracked source files directly; all their comments are new. If HEAD does not exist yet, treat tracked and non-ignored untracked source files as new.

Review the current working-tree contents. A staged change subsequently undone in the working tree is not part of this net scope. Do not edit a hidden staged version or change the index; report that distinction if relevant to the request.

### Candidate boundaries

- Review every eligible source file, including inline comments, block comments, and documentation comments/docstrings. Skip generated, vendored, binary, and ignored content; report exclusions that affect coverage. Do not follow symlinks outside the repository or traverse submodule repositories without an explicit request.
- Compare comment text with the old side. A comment is eligible only if its own text is new or changed. An unchanged comment beside changed code, a pure file rename, or a moved unchanged comment is not a cleanup target.
- Review a changed multiline comment as a unit. You may rewrite that entire comment, but do not sweep adjacent unchanged comments into the edit.
- Deleted comments need no action. Read unchanged code for context without expanding the cleanup scope.
- Keep ordinary string literals, prompts, README prose, and standalone documentation out of scope unless the user explicitly includes them. If included, apply the same changed-text restriction and editing criteria.

## Decide whether to remove, rewrite, or keep

Remove comments whose entire content is already clear from nearby code. Rewrite comments that contain useful information mixed with narration or filler. Keep accurate comments that explain something a maintainer needs to know, even when their style sounds agent-written.

Look for:

- References to the chat, an earlier implementation, or the reviewer’s instructions.
- Vague claims that something fixes a bug without explaining the failure mechanism.
- Tutorials for ordinary syntax or step-by-step narration of straightforward code.
- File inventories, copied counts, and other details better obtained from maintained artifacts.
- Unnecessary lists of rejected alternatives or things the implementation does not do.
- Unsupported assurances and locally invented terminology that obscure the actual behavior.

Use direct, concise language grounded in the implementation. Prefer one sentence when sufficient; retain detail needed to explain a real constraint. Do not invent reasons, issue numbers, or links. Preserve existing useful references. If the reason cannot be established, leave the comment and report the uncertainty.

Preserve legally or mechanically significant comments: license notices, attribution, lint/type/coverage directives, formatter controls, build annotations, shebangs, encoding declarations, and documentation consumed by tooling. Retain repository-required test annotations, including `Constraint:`, `Input:`, and `Expected output:` where mandated. Their prose may be tightened only while preserving required information and format. Avoid removing the sole statement in a Python body when editing a docstring, and preserve whitespace needed to keep surrounding tokens separate.

## Examples

These examples illustrate editing decisions; they are not phrase-matching rules. Each rewrite assumes the stated behavior has been verified in the code.

**Iteration history — remove:**

```python
# Use the version we settled on after the previous review.
send_report(report)
```

Keep the call and delete the comment.

**Obvious narration — remove:**

```python
# Add the item to the list.
items.append(item)
```

Keep the statement and delete the comment.

**A real failure mechanism — rewrite:**

```python
# Fix the reconnect bug here.
# becomes:
# Clear the cached socket so retries open a new connection.
```

**File inventory — remove the inventory; retain useful selection behavior:**

```python
# The readers folder contains csv.py, xml.py, and json.py.
# becomes, if useful at this location:
# Choose the reader from the uploaded file's media type.
```

**Unnecessary exclusions — express the actual limit:**

```python
# No recursive lookup, no grandparent lookup, and no full ancestry scan.
# becomes:
# Inherit settings from the immediate parent only.
```

**Copied counts — point to maintained information when useful:**

```python
# There are 82 accepted codes and 19 aliases.
# becomes:
# Accepted codes and aliases are defined in codes.json.
```

Delete even the replacement if the adjacent code already makes the source clear.

**Assurance and invented terminology — use the concrete constraint:**

```python
# Production-grade trust envelope for the final persistence phase.
# becomes:
# Commit the balance and ledger entry in the same transaction.
```

**Useful rationale — keep:**

```python
# The device reads this field as little-endian regardless of host byte order.
```

Also keep a meaningful limitation such as `# Retry only before the server acknowledges the write.` Negative wording alone is not a defect.

## Apply and verify

Make focused comment edits in the working tree; leave staging and commits to the user unless requested. Preserve unrelated changes and executable code. Avoid broad formatting passes.

Compare your edits with the captured starting state. Confirm every edit belongs to an eligible comment and preserves behavior, required annotations, and useful rationale. Check whitespace and syntax where comment removal or docstring edits could affect parsing; use relevant existing checks when needed. Do not add unit tests merely to enforce comment wording.

The final response must report every comment modified during this cleanup, grouped by file. For each comment, include its file and line location, whether it was rewritten or removed, the original text, and the replacement text (or “Removed”). For removed comments, use the original line location and label it as such. Report your own changes relative to the captured starting state, not pre-existing user changes.

Also report the selected mode and baseline, totals removed and rewritten, and verification performed. Mention skipped candidates, unreadable files, and unresolved conflicts. If no comments were modified, state that explicitly.

## Reference

Criteria inspired by [citelao's claudy-comment-detector](https://github.com/citelao/dotfiles/blob/main/dotfiles/.chezmoitemplates/skills/claudy-comment-detector/SKILL.md). This skill supplies original examples and adds scoped Git comparisons and direct editing.
