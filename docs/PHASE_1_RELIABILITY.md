# Phase 1 — Workflow reliability

## Durable job processing

RFQ and COA uploads are persisted as workflow runs and durable `workflow_jobs` rows before the API returns `202 Accepted`. A worker started by the FastAPI application claims jobs from the database. The queue is stored in the same SQL database as the workflow state, so pending work survives an API process restart.

Each job has a unique workflow-run constraint, attempt count, availability timestamp, worker lease, status and last error. Enqueue is idempotent for a workflow run. Claiming uses a conditional database update, so two application workers cannot both claim the same queued row. A worker lease expires after 30 minutes; a replacement worker can reclaim an abandoned job after a process crash.

## Retry and failure semantics

- A worker crash or unexpected exception outside the workflow processor releases the job back to the queue with bounded exponential delay (1, 2, 4 seconds; capped at 5 minutes).
- The maximum number of claims is three.
- A workflow processor that completes with a domain status such as `needs_info`, `pending_approval`, or `completed` marks its job completed.
- A workflow processor that records a terminal `failed` workflow marks the job failed. Domain failures are not automatically replayed because repeating partially committed business side effects would be unsafe without a dedicated compensation/idempotency strategy.
- Stale jobs at their maximum attempt count must be moved to terminal failure by the queue maintenance path.

## Operations

- `GET /api/jobs/{job_id}` returns job state to the workflow owner (or an admin).
- Dashboard metrics include queued, running, completed and failed job counts.
- The worker is started and stopped with the FastAPI lifespan.

## Current scope and limitations

This is a database-backed single-process worker loop per API process, not a separate horizontally scalable worker deployment. The conditional claim operation prevents duplicate claims across multiple app instances, but production scale-out should move the worker into a separate service and add periodic lease renewal for jobs that can exceed 30 minutes. A job is not marked successful merely because it was dequeued; the worker checks the final workflow status first.
