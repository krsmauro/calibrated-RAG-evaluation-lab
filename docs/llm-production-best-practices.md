# Running LLM systems in production: best practices

2026-10-19

## Core principles

Most production failures in LLM systems come from six gaps. Each practice below closes one of them.

1. **Every change is a version you can turn off.** Prompts, rules, model choice and settings get an ID, and rollback is a pointer flip, not a deploy.
2. **One change at a time.** If a prompt change and a scaling change ship together, you can't tell which one broke things.
3. **Limits belong to the fleet, not the instance.** Provider rate limits and database connections are shared budgets, so size them for all workers at once.
4. **Model output is untrusted input.** Check why it stopped, validate its shape, and have a fallback for when it's wrong or empty.
5. **Log the decision, then the outcome.** Without a decision ID that joins to what happened later, the system can't learn and you can't debug it.
6. **Decide on evidence you defined in advance.** Write success and stop criteria before a test, and compare versions with confidence intervals.

| Situation | Sections that cover it |
| --- | --- |
| Turning a rules engine into a learning loop | Shipping changes safely; Capturing outcomes |
| Latency, spend and the queue blow up after a deploy | Capacity and concurrency; Handling model output; Incident playbook |
| Proving the loop helps without hurting cost or latency | Proving a change helps; Observability and alerting |

## Shipping changes safely

- **Version everything that changes behavior.** Keep the source in git and review changes in pull requests. On deploy, register each version as immutable with a content hash, and keep a pointer to the active version in the database.
- **Stamp versions on every decision:** prompt version, rules version, model snapshot and settings. Without them you can't tell which change caused a regression.
- **Gate on cost and speed, not only quality.** The offline eval should report tokens in and out per call and p95 latency against the current version. A prompt that triples output length should fail here, before any user sees it.
- **Shadow before you act.** Run the candidate on live traffic without using its answer. Shadowing doubles LLM spend for that slice, so sample it if volume is high.
- **Canary by entity, then ramp.** Start with a few percent of customers, assigned by a stable hash of their ID so each one always sees the same version. Ramp in steps (for example 5, 25, 50, 100 percent) and hold each step long enough to check the guardrails.
- **Rollback is a pointer flip,** with no build and no deploy. Practice it before you need it.
- **Keep a kill switch:** one flag that sends all traffic back to the safe path (the rules or the last good version). Test it in staging before launch.
- **Ship one change per rollout.** Never pair a prompt change with a scaling, model or infrastructure change. If both have to happen, ship them hours apart and check in between.
- **Pin dated model snapshots.** An alias that points to the latest model can change under you. Treat a model upgrade as a change that goes through the same stages.

## Capacity and concurrency

Scaling workers multiplies every per-worker limit. Budget rate limits, retries and connection pools for the whole fleet, or adding workers makes things worse.

**Provider rate limits**

- Providers usually cap requests per minute and tokens per minute. Check your provider's docs for how input and output tokens are counted.
- Use one shared limiter for all workers, such as a token bucket in Redis or Postgres, set below the provider limit with headroom. Separate limiters per worker don't work: 10 workers, each under the limit, can together send 10 times the limit.
- Cap in-flight LLM calls separately from the worker count. When the limiter says no, the job waits in the queue instead of getting a 429.

**Retries and timeouts**

- Retry at one layer only. Many provider SDKs retry by default, so either turn that off or don't retry in your queue as well.
- Use exponential backoff with jitter, and honor the Retry-After header when the provider sends one.
- Set a retry budget, for example no more than 10 percent of calls. Add a circuit breaker that stops calling the provider and falls back after sustained 429s or 5xx errors.
- Don't retry errors that can never succeed, such as invalid requests or a context that's too long.
- Size client timeouts from the p99 duration of the current prompt version. A call that times out may still be billed, so a timeout followed by a retry can mean paying twice.

**Database connections**

- Budget connections: instances times pool size has to fit under Postgres max_connections, with headroom for admin work and migrations. Recompute it every time you scale.
- Never hold a connection or an open transaction during an LLM call. Read what you need, release the connection, call the model, then write the result in a short transaction.
- Put a pooler such as PgBouncer in front when the number of instances changes. LISTEN/NOTIFY doesn't work through PgBouncer in transaction mode, so check whether your queue library uses it.
- Lots of sessions showing "idle in transaction" in pg_stat_activity means connections are being held while slow work runs.

**Job queues**

- Make the job lease (visibility timeout) longer than the slowest job, or extend it with a heartbeat. Otherwise a slow job gets handed to a second worker while the first is still running it.
- Give each unit of work an idempotency key, such as decision ID plus prompt version. Check for an existing result before calling the model, and write results as an upsert on that key.
- After a set number of attempts, move the job to a dead-letter table with its error stored, and alert when that table grows.
- Watch the age of the oldest job, not just queue depth. Depth can look normal while one job type starves.
- If the provider is the bottleneck, more workers won't drain the queue faster. They only add 429s.

## Handling model output

- **Check the stop reason on every response.** Anthropic returns `stop_reason: "max_tokens"` and OpenAI returns `finish_reason: "length"` when output is cut off. Treat a cut-off answer as a failure, not a result.
- **Set the output cap on purpose:** high enough for the longest valid answer, low enough to bound cost and latency. Track how output length is distributed for each version.
- **Validate structure even when you use structured outputs.** Run a schema check on every response (zod in TypeScript, Pydantic in Python).
- **Repair once, then fall back.** On a validation failure, allow at most one retry that sends the error back to the model. Count each path: valid, repaired, fallback.
- **Never return empty silently.** An empty string, a null or a missing field is an error, with a metric and a fallback.
- **Decide fallbacks before launch.** What users get when the model fails (the rules decision, the previous version, a human review queue) is a product decision.
- **Log raw output with the decision ID,** redacted, so you can see exactly what changed between versions.
- **Watch output drift.** Output length, refusal rate and schema-failure rate for each version are usually the first signs that a prompt or model change went wrong.

## Capturing outcomes and closing the loop

- **Log one append-only row per decision:** decision ID, entity ID, time, input snapshot, versions, model, raw output, final decision, the path taken (rules, LLM or fallback), latency, tokens and cost.
- **Snapshot the inputs instead of referencing them.** The underlying data changes over time, so if you store only IDs you can't replay a decision later.
- **Store outcomes in their own append-only table,** keyed by decision ID, with a source and the time each was observed. Ingest them idempotently by webhook or batch import, so the same outcome sent twice becomes one row.
- **Give each decision a label state:** pending, observed, or expired after a set window. Report coverage (the share of decisions with an outcome) and label lag (how long outcomes take to arrive).
- **Use a proxy when real outcomes are slow,** but first check on historical data that it actually tracks the real outcome.
- **Count human signals as labels.** Overrides, corrections and review verdicts are often your fastest signal. Record who made each one and a reason code.
- **Keep a small randomized holdout.** You only see outcomes for the actions you took. Without a holdout, you can't compare against the old system or learn what another choice would have done.
- **Guard against self-reinforcing loops.** A system that learns from its own decisions can amplify its own mistakes. Have a person approve rule and prompt changes, and watch metrics by segment.
- **Redact before you store.** Remove or tokenize personal data in inputs and outputs, and set a retention period.

The lean loop has three parts, and every change it produces still goes through the stages in Shipping changes safely:

1. Find similar past cases that had good outcomes and add them to the prompt as examples.
2. Group bad outcomes in a review queue, have an LLM draft candidate fixes, and let a person decide.
3. Add every labeled case to the eval set.

## Proving a change helps

- **Write the hypotheses with the business.** One primary metric has to improve by at least an agreed amount. Cost and latency are guardrails that may not get worse by more than an agreed margin.
- **Replay history offline first.** Run recent decisions through the candidate. Where it agrees with the current system, you already know the outcome. Label the cases where they disagree first, because that's where the difference shows up.
- **Label blind, against a written rubric.** Labelers shouldn't know which system made which call. Have two people label the same subset and measure how often they agree.
- **Check an LLM judge before trusting it.** Measure its agreement with human labels using Cohen's kappa rather than raw agreement, and test for position and verbosity bias. Where you can, use a different model family from the one being judged.
- **Compare paired results with confidence intervals.** A bootstrap works. Cluster by customer when one customer contributes many decisions, or the intervals will come out too narrow.
- **Allow three outcomes: win, lose or inconclusive.** Inconclusive means you keep the current system; it doesn't mean ship.
- **Online, randomize by entity.** Use a stable hash of the customer ID so each customer stays in one group, and keep a small permanent holdout on the old system.
- **Choose segments in advance,** just a handful, such as new versus returning customers, so you aren't fishing for one that happens to win.
- **Fix the duration up front.** Size it with a power calculation and cover at least one full week. Checking the primary metric repeatedly and stopping on a good day inflates false wins. If you need to look early, use a sequential test.

| Signal | When it's checked | Action |
| --- | --- | --- |
| A guardrail breaks: p95 latency, cost per decision, fallback rate or empty outputs over threshold | Continuously | Roll back automatically with the kill switch |
| A segment you chose in advance is harmed beyond its margin | At each ramp step | Hold the ramp, or roll back for that segment |
| Primary metric wins, the interval excludes zero, guardrails hold | At the planned end | Move to the next ramp step |
| Primary metric loses | At the planned end | Roll back |
| Inconclusive | At the planned end | Keep the current system and iterate |

## Observability and alerting

- **Trace by decision ID.** With OpenTelemetry, give each step its own span: rules, retrieval, the LLM call, queue wait, database writes. Tag the spans with prompt version and model.
- **Make decisions replayable** from the input snapshot, versions, model and settings. Sampling and changes on the provider's side mean a replay won't match word for word, so compare behavior across many cases, not single outputs.
- **Put deploy markers on every chart,** so a jump in latency lines up with the change behind it.
- **Make version a filter on every dashboard.**

| Layer | What to measure | Break down by |
| --- | --- | --- |
| System | p50, p95 and p99 latency; error rate; queue depth; oldest job age; DB connections in use; idle-in-transaction count | Service, job type |
| LLM | Calls; 429 and 5xx rate; retries per call; tokens in and out per call; cost per decision; timeouts; stop reasons; schema failures; fallback rate | Prompt version, model |
| Decisions | Decision mix; shadow agreement with the current system; human override rate | Version, segment |
| Outcomes | Coverage; label lag; outcome rate | Version, segment |

Page on symptoms people actually feel:

- p95 latency over the SLO for several minutes
- Spend per hour over budget, backed by a hard spending limit at the provider
- A spike in the fallback or empty-output rate
- Sustained 429s
- Oldest job age over its threshold
- DB connections above about 80 percent of the maximum
- No outcomes ingested for longer than usual

A sudden shift in the decision mix should open a ticket rather than page someone.

## Incident playbook

Stop the damage first and find the cause second. Undo the most recent change, then confirm what happened with a few targeted checks.

1. **Assign roles.** One person mitigates and one investigates, even on a team of two. Keep a running timeline.
2. **Ask what changed:** deploys, prompt versions, model snapshots, scaling, config, traffic, and the provider's status page.
3. **Pull the cheapest lever you can undo.** Flip the prompt pointer back, revert the scaling, or use the kill switch. Pause non-critical async work (shadow runs, evals, backfills) to free up rate limit and connections.
4. **Stabilize.** Cap concurrency, turn off any duplicate retry layer, and let the queue drain, skipping duplicates by idempotency key.
5. **Confirm the cause** with the checks in the table below.
6. **Bring changes back one at a time,** watching the dashboards after each.
7. **Write a blameless postmortem:** the timeline, the root cause, and why no guardrail caught it. Add one check per gap, such as an eval gate or an alert.

| Symptom | Fastest check | Likely cause |
| --- | --- | --- |
| Slow 200s and higher spend | Tokens in and out per call, by prompt version | The new prompt or model generates more |
| Empty or cut-off answers | Stop reasons by version | Hitting the output cap; the parser fails on a new format |
| Spikes of 429s | In-flight calls and request and token rates against the provider limit; retries per call | Concurrency above the limit; a retry storm |
| Spend rising faster than traffic | LLM calls per decision ID | Duplicate work: retries after timeouts, or jobs handed out twice |
| DB connections near the maximum | pg_stat_activity by state and application; pool size times instances | Scaling multiplied the pools; connections held during LLM calls |
| Queue keeps growing | Oldest job age, lease expiries, dead-letter growth | Throughput capped upstream; jobs redelivered in a loop |

## Pre-launch checklist

- [ ] The change has a version ID, and rolling it back is a tested pointer flip.
- [ ] The kill switch works in staging.
- [ ] This rollout contains exactly one change.
- [ ] The offline eval passed on quality, tokens per call and p95 latency against the current version.
- [ ] The output cap is set, and cut-off or invalid output goes to a fallback.
- [ ] The fleet-wide rate limit and concurrency cap are sized for the new worker count.
- [ ] Only one layer retries, with backoff, jitter and Retry-After.
- [ ] Instances times pool size fits under Postgres max_connections, with headroom.
- [ ] No database connection is held during an LLM call.
- [ ] Job leases outlast the p99 job duration, and LLM calls carry an idempotency key.
- [ ] Dashboards filter by version, a deploy marker is in place, and alerts cover latency, cost, fallbacks, 429s, queue age and DB connections.
- [ ] Success and stop criteria are written down.

## Further reading

- [Handling Overload](https://sre.google/sre-book/handling-overload/), chapter 21 of Google's *Site Reliability Engineering*
- [Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/), chapter 22 of the same book
- [Timeouts, retries, and backoff with jitter](https://builder.aws.com/content/3EumjoZascWd1oZiEgL8ORlv3qE/timeouts-retries-and-backoff-with-jitter), Marc Brooker, Amazon Builders' Library
- [PgBouncer features](https://www.pgbouncer.org/features.html): which SQL features work in each pooling mode
- [Trustworthy Online Controlled Experiments](https://experimentguide.com/), Kohavi, Tang and Xu
- [Patterns for Building LLM-based Systems & Products](https://eugeneyan.com/writing/llm-patterns/), Eugene Yan
