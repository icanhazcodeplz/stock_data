#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash) — block any `git push` that would land on main.
#
# Reads the tool-call JSON on stdin and, if the command is a git push targeting
# the main branch, emits a PreToolUse "deny" decision so the push never runs.
# Any other command exits 0 (allow) immediately.
set -euo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')

# Fast path: not a git push -> allow.
if ! printf '%s' "$cmd" | grep -Eq 'git[[:space:]]+push'; then
  exit 0
fi

deny() {
  jq -n --arg reason "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
  exit 0
}

MSG="Pushing to 'main' is blocked. Create a feature branch and open a PR instead."

# Rule 1 (any branch): an explicit `main` destination token, e.g.
#   git push origin main | git push origin HEAD:main | git push origin main:main
# `main` must be bounded by start/space/colon on the left and space/end on the
# right, so `main-feature`, `mymain`, and `feature/main` do NOT match.
if printf '%s' "$cmd" | grep -Eq '(^|[[:space:]:])main([[:space:]]|$)'; then
  deny "$MSG"
fi

# Rule 2 (only when currently on main): a bare push or an explicit HEAD push
# resolves to main.
current=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [ "$current" = "main" ]; then
  # First non-flag, non-remote token after `git push` is the refspec (if any).
  rest=$(printf '%s' "$cmd" | sed -E 's/.*git[[:space:]]+push//')
  refspec=$(printf '%s' "$rest" | tr ' ' '\n' \
    | grep -vE '^-' | grep -vE '^(origin|upstream)$' | grep -vE '^$' \
    | head -n1 || true)
  if [ -z "$refspec" ] || [ "$refspec" = "HEAD" ]; then
    deny "$MSG"
  fi
fi

exit 0
