#!/usr/bin/env bash
# Write the retrieval gate's report to the job summary and to one sticky PR comment (plan step
# 4.7b). action.yml calls it with the gate's outcome and the run's details in the environment:
# OUTCOME, CONFIG, PR, HEAD_SHA, RUN_URL, POST_COMMENT (true or false) and GH_TOKEN, plus the
# runner's own RUNNER_TEMP, GITHUB_STEP_SUMMARY and GITHUB_REPOSITORY.
#
# The comment is found again by the marker on its first line, among the comments this workflow's
# token wrote, and edited in place: a PR keeps one gate comment however often it is pushed.
set -euo pipefail

marker='<!-- ragcalibrate-retrieval-gate -->'
report="$RUNNER_TEMP/gate-report.md"
body="$RUNNER_TEMP/gate-comment.md"

case "$OUTCOME" in
  pass) headline='Pass' note='' ;;
  fail) headline='Fail' note='The check fails.' ;;
  inconclusive)
    headline='Inconclusive'
    note='Neutral: the check passes. The interval is too wide to tell; see the report.' ;;
  none)
    headline='No outcome'
    note='Neutral: the check passes. The two runs use different chunkers, and which metric gates
a chunker change is still open (decision D8).' ;;
  *) headline='Could not run' note='The check fails. The job log has the reason.' ;;
esac

{
  echo "$marker"
  echo "## Retrieval gate: $headline"
  echo
  if [ -n "$note" ]; then echo "$note"; echo; fi
  echo "\`$CONFIG\` on all of CUAD dev: the base branch with this PR merged in (candidate) against"
  echo "the base branch without it (baseline, their merge base). PR head ${HEAD_SHA:0:12},"
  echo "[workflow run]($RUN_URL)."
  echo "Retrieval only: no LLM calls, no API cost."
  echo
  if [ -s "$report" ]; then cat "$report"; fi
} > "$body"

cat "$body" >> "$GITHUB_STEP_SUMMARY"

if [ "$POST_COMMENT" != true ]; then
  echo "No PR comment: a fork's token cannot write one. The report is in the job summary."
  exit 0
fi
comments="repos/$GITHUB_REPOSITORY/issues/$PR/comments"
ids=$(gh api --paginate "$comments" --jq \
  ".[] | select(.user.login == \"github-actions[bot]\" and (.body | startswith(\"$marker\")))
  | .id")
id=${ids%%$'\n'*} # the first, if there are several
if [ -n "$id" ]; then
  gh api --method PATCH "repos/$GITHUB_REPOSITORY/issues/comments/$id" -F body=@"$body" >/dev/null
  echo "Updated the gate comment $id."
else
  gh api --method POST "$comments" -F body=@"$body" >/dev/null
  echo "Posted the gate comment."
fi
