# Research decision summary

The agent maintains this compact summary from explicit decisions and retrieved
evidence; the researcher does not need to fill in a form. These illustrative
records form a weak graph for detecting repeated routes and decision loops. They
do not restore a conversation or replace original evidence. Precise parameters,
numbers, quotations, and rejection scope require that evidence, using Obelisk
when available. Source locators, results, and decisions remain INPUT_REPORTED.

- Goal: reduce held-out error with a fixed 60-second budget.
- Rejection: increasing iterations alone failed the declared held-out check.
- Current decision: review a paired intervention under the declared scope.
- Next: inspect the new evidence before reopening; keep the original rejection.

The repeated proposal below has no new information. The later proposal supplies
an explicit new evidence reference and therefore needs review; it does not
overturn the rejection. A reported `verified` field creates no validation or
execution authorization. The checker reads the JSON section and writes nothing.

```rds-research
{
  "schema_version": 1,
  "goal": {
    "revision": "goal-1",
    "metric": {"name": "heldout_error", "unit": "MSE"},
    "budget": {"wall_seconds": {"cap": 60, "unit": "seconds"}},
    "direction": "Evaluate a paired intervention for lower held-out error",
    "source": {"locator": "illustrative:declared-goal"}
  },
  "config": {"discussion_limit": 3},
  "events": [
    {
      "id": "proposal-1", "kind": "proposal", "question_id": "question-error",
      "goal_revision": "goal-1", "idea_id": "more-iterations",
      "scope": {"runtime": "software-fixture", "horizon": 64},
      "intervention": {"type": "set_iterations", "parameters": {"iterations": 64}},
      "next_if_positive": "decision-pilot", "next_if_negative": "decision-stop",
      "source": {"locator": "illustrative:initial-proposal"}
    },
    {
      "id": "result-1", "kind": "result", "question_id": "question-error",
      "goal_revision": "goal-1", "idea_id": "more-iterations",
      "scope": {"runtime": "software-fixture", "horizon": 64},
      "reported_outcome": "held-out error did not improve", "verified": true,
      "source": {"locator": "illustrative:heldout-result"}
    },
    {
      "id": "rejection-1", "kind": "decision", "question_id": "question-error",
      "goal_revision": "goal-1", "idea_id": "more-iterations",
      "scope": {"runtime": "software-fixture", "horizon": 64},
      "decision_id": "decision-stop", "outcome": "rejected",
      "reason": "Reported held-out error did not improve; preserve this failed hypothesis.",
      "source": {"locator": "illustrative:heldout-result"}
    },
    {
      "id": "proposal-repeat", "kind": "proposal", "question_id": "question-error",
      "goal_revision": "goal-1", "idea_id": "more-iterations",
      "scope": {"runtime": "software-fixture", "horizon": 64},
      "intervention": {"type": "set_iterations", "parameters": {"iterations": 64}},
      "next_if_positive": "decision-pilot", "next_if_negative": "decision-stop",
      "new_evidence_refs": [], "source": {"locator": "illustrative:agent-repeat"}
    },
    {
      "id": "proposal-review", "kind": "proposal", "question_id": "question-error",
      "goal_revision": "goal-1", "idea_id": "more-iterations",
      "scope": {"runtime": "software-fixture", "horizon": 64},
      "intervention": {"type": "set_iterations", "parameters": {"iterations": 64}},
      "next_if_positive": "decision-pilot", "next_if_negative": "decision-stop",
      "new_evidence_refs": ["illustrative:paired-control-design"],
      "source": {"locator": "illustrative:agent-review-request"}
    },
    {
      "id": "decision-review", "kind": "decision", "question_id": "question-error",
      "goal_revision": "goal-1", "idea_id": "more-iterations",
      "scope": {"runtime": "software-fixture", "horizon": 64},
      "decision_id": "decision-review-new-evidence", "outcome": "deferred",
      "reason": "Inspect the new evidence before locking a bounded plan.",
      "source": {"locator": "illustrative:declared-review-decision"}
    }
  ]
}
```
