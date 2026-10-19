# F-006: master-code-skill points at files that do not exist; the best-practices doc is mostly for a different system

- **Status:** open
- **Date:** 2026-10-19
- **Found by:** Claude, while writing the plan
- **Evidence level:** measured (file listing on 2026-10-19)
- **Affects:** 0.4, 1.11, 2.11, 4.9, 5.9; `.claude/skills/master-code-skill/SKILL.md`

## Finding
1. `SKILL.md` maps many files under `references/python/` and `references/eval/`. Only `references/karpathy-mindset.md` exists. An agent that follows the map hits missing files. It also cites section numbers of `docs/project-plan.md` that now live in `docs/design/project-design.md`.
2. `docs/llm-production-best-practices.md` is written for a production system that turns a rules engine into a learning loop (customers, canaries, queues, outcomes). This project is an eval harness and a small service. Roughly these parts apply: pin dated model snapshots; retry at one layer with backoff, jitter and Retry-After; check the stop reason; validate structure, repair once, then fall back; do not hold a DB connection during an LLM call; stamp versions on every record; paired bootstrap clustered by entity, three outcomes; blind labeling and checking a judge with κ. These parts do not apply now: shadow runs, canary ramps, kill switch, job-queue leases, outcome capture and holdouts, incident playbook. They become relevant only under "what changes at 100 times the corpus size".

## Evidence
`ls .claude/skills/master-code-skill/references/`; reading both documents.

## Consequence
Step 0.4 fixes the pointers and marks unwritten files. Each phase writes the reference file it needs (1.11, 2.11, 4.9, 5.9), derived from what was built. Phase 5 lists the applicable best-practices constraints inline so an agent does not need the whole document.

## Resolution
