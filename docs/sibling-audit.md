# Sibling overlap audit

This file records decisions about pairs of dashboard surfaces that are
adjacent in the IA but cover overlapping ground. Each decision is checked
into the repo so future contributors can read the reasoning rather than
re-litigate it.

## Runs vs Traces

- **Runs (`/dashboard/runs`)** lists executions — one row per run.
- **Traces (`/dashboard/traces`)** is the deep view of a single execution.

A pure-IA argument says Traces should be `/dashboard/runs/[id]/trace` since
a trace belongs to a run. We chose to keep them as siblings for now to
preserve parity with `forge traces` in the CLI. To soften the overlap, the
Recent Runs / Run History rows now link directly to
`/dashboard/traces/<run id>`. If the CLI command ever drops, fold the
trace view under `/dashboard/runs/[id]/trace` and remove the sibling.

## Evals vs Compare

- **Evals (`/dashboard/evals`)** runs test cases against expected outputs.
- **Compare (`/dashboard/compare`)** runs a single prompt across multiple
  models and shows side-by-side outputs.

These are different problems. Evals answers "did my agent stay correct
after I changed it?" Compare answers "which model should I run this on?"
We keep both as siblings under Observe and do not rename. A lightweight
Compare panel also lives on `/dashboard/providers` for fast multi-model
spot checks; the dedicated Compare page is the place for the full studio
(system prompt, temperature, max tokens, full results history).

## Prompts vs Marketplace

- **Prompts (`/dashboard/prompts`)** is the user's private prompt-version
  history.
- **Marketplace (`/dashboard/marketplace`)** is the public/shared catalog.

These do not overlap in browse UI. Prompts has no public catalog of its
own; Marketplace is where publishing happens. We keep them as separate
top-level entries. Future work: add a "Publish to Marketplace" CTA on
the Prompts version detail view, routing to the Marketplace publish flow.
That is a separate change, not part of the IA cleanup.

## Knowledge vs Marketplace

Same shape as Prompts vs Marketplace. Knowledge is private knowledge bases
the user owns; Marketplace is where shared knowledge bases would be
published. We keep them as separate top-level entries. The Marketplace
publish flow is also future work.
