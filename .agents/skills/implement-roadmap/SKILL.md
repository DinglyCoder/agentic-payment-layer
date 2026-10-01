---
name: implement-roadmap
description: Implement the next coherent milestone from this repository's docs/roadmap.md, verify it, reconcile durable project documentation, and commit and push the result. Use when continuing roadmap work in a fresh implementation session; do not use for an explicitly scoped bug fix or documentation-only request.
---

# Implement Roadmap

Carry one roadmap milestone from repository evidence to a pushed commit. The
skill invocation authorizes the implementation, its necessary documentation,
one or more focused commits, and a push of the current branch. It does not
authorize deployments, purchases, secret changes, or other irreversible
external operations.

## Establish the milestone

1. Read `AGENTS.md`, all of `docs/roadmap.md`, and all of `handoff.md` before
   choosing work. Then inspect the current branch, worktree, recent commits,
   and the code and documentation relevant to likely candidates.
2. Reconcile roadmap language with repository evidence. Treat `handoff.md`,
   tests, and current code as stronger evidence of completed work than an
   unchecked or stale roadmap bullet. Do not reimplement completed work.
3. If the user named a roadmap item, use that scope. Otherwise select the
   highest-priority unfinished item that forms a coherent, reviewable vertical
   slice and can be completed in the current repository. Prefer one finished
   slice over partial work across several bullets.
4. State the selected milestone and any consequential assumption before making
   large edits. Ask only when equally plausible choices would produce
   materially different products or when required authority is missing.
5. Preserve unrelated user changes. If they overlap the milestone and cannot
   be safely separated, stop and explain the conflict.

## Implement and verify

- Trace every affected boundary before editing. Follow the repository's
  architecture, security constraints, dependency managers, and testing rules.
- Implement the complete slice, including migrations or compatibility logic,
  API/type/ABI updates, and focused tests where the changed behavior requires
  them. Do not broaden the session into adjacent roadmap work.
- Run the smallest relevant checks while iterating, then run the verification
  required by `AGENTS.md` for the final change. Fix failures caused by the
  implementation. Report unrelated pre-existing failures accurately rather
  than hiding them.
- Inspect the final diff and status for secrets, generated output, accidental
  files, and unrelated edits. Never stage changes merely because they are
  present.

## Reconcile durable documentation

After behavior and verification are settled, update documentation from the
observed result:

- `handoff.md`: keep entries newest first; record the delivered behavior,
  verification results, deployment or external-operation state, and concrete
  follow-up work. Use `This commit` when a single commit contains its own
  handoff entry; do not invent the commit hash.
- `AGENTS.md`: change only durable guidance future agents need because the
  architecture, invariants, commands, ownership, or limitations changed. Do
  not add a session log or restate the handoff.
- `docs/roadmap.md`: mark, move, or rewrite only the items whose status or
  design changed. Preserve longer-term direction and make remaining work
  unambiguous. Do not claim a deployment, audit, or integration occurred
  without evidence.
- Update other operator or architecture documentation only when the
  implementation would otherwise leave it false or incomplete.

## Commit and push

1. Review the exact diff and rerun any check invalidated by documentation or
   generated-boundary edits.
2. Stage only the milestone and its documentation. Create a concise functional
   commit; use multiple small commits only when they make the result materially
   easier to review and each commit is internally coherent.
3. Confirm the commit exists and the worktree contains no uncommitted changes
   from this task. Do not absorb unrelated existing changes into the commit.
4. Push the current branch to its configured upstream. A normal push is in
   scope; force-push is not. If the push is rejected or authentication is
   unavailable, preserve the local commit and report the exact recovery step
   instead of rewriting history or changing remotes.
5. Finish with the selected milestone, commit hash, pushed branch, checks run,
   and any intentionally deferred external operation or remaining blocker.
