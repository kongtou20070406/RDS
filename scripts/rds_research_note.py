"""Retired bare-note API; research decisions belong in the existing ledger."""

def _retired(*args, **kwargs):
    raise ValueError("Standalone research-note review is retired. Use checkpoint save --decision <decision.json> and advise --research-context <context.json>.")

load_research_note = review_research_note = _retired
