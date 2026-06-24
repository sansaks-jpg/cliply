#!/usr/bin/env bash
# Check GitHub Actions build status for cliply v0.1.2
# Exit 0 = success (nothing to report), non-zero = failure (output goes to user)

set -euo pipefail

OWNER="sansaks-jpg"
REPO="cliply"
REF="v0.1.2"
GH_API="https://api.github.com/repos/${OWNER}/${REPO}/actions/runs"

# Fetch latest run for the tag
RUN_JSON=$(curl -sf "${GH_API}?event=push&branch=${REF}&per_page=1" 2>/dev/null || echo "")

if [ -z "$RUN_JSON" ]; then
  echo "⚠️  Could not fetch build status for ${REF} — GitHub API unreachable or no runs yet."
  exit 0
fi

TOTAL_COUNT=$(echo "$RUN_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total_count',0))" 2>/dev/null || echo "0")

if [ "$TOTAL_COUNT" -eq 0 ]; then
  echo "⏳ No build run found for tag ${REF} yet."
  exit 0
fi

LATEST_RUN=$(echo "$RUN_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
runs = data.get('workflow_runs', [])
if not runs:
    sys.exit(0)
r = runs[0]
print(f\"{r['id']}|{r['status']}|{r['conclusion'] or 'pending'}|{r['html_url']}\")
" 2>/dev/null || echo "")

if [ -z "$LATEST_RUN" ]; then
  exit 0
fi

IFS='|' read -r RUN_ID STATUS CONCLUSION URL <<< "$LATEST_RUN"

if [ "$STATUS" = "completed" ]; then
  if [ "$CONCLUSION" = "success" ]; then
    # Silent — all good
    exit 0
  else
    echo "❌ Build ${REF} FAILED (${CONCLUSION})"
    echo "   ${URL}"
    exit 1
  fi
else
  echo "🔄 Build ${REF} is still ${STATUS}..."
  echo "   ${URL}"
  exit 0
fi
