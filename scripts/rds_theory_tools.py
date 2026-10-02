"""Retrieve preloaded, conditional theory tool cards; never execute their backends."""
import argparse
import hashlib
import json
from pathlib import Path
import re

CATALOGUE = Path(__file__).resolve().parents[1] / "references" / "theory-tools.json"
MAX_BYTES = 20 * 1024
SIGNALS = frozenset(("trajectory_degradation", "local_global_gap", "step_sensitivity",
                     "structured_residual", "equation_unknown", "proof_bottleneck", "execution_mismatch"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _load():
    with CATALOGUE.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "Theory catalogue exceeds 20 KiB")
    catalogue = json.loads(raw)
    require(catalogue.get("schema") == 1, "Unknown theory catalogue schema")
    cards = catalogue["cards"]
    require(isinstance(cards, list) and 1 <= len(cards) <= 64, "Expected 1..64 bounded theory cards")
    require(len({card["id"] for card in cards}) == len(cards), "Duplicate theory card id")
    for card in cards:
        require(set(card["tags"]) <= SIGNALS and card["tags"], "Unknown theory card tags")
        require(all(card.get(key) for key in ("title", "required_inputs", "conditions", "diagnostic",
                                            "limitations", "capability", "sources")), "Incomplete theory card")
    return cards, {"schema": "rds-theory-tools-v1", "catalogue_sha256": hashlib.sha256(raw).hexdigest(),
                   "catalogue_locator": str(CATALOGUE.resolve()), "selection": "TAG_MATCH_ONLY",
                   "available_on": catalogue["available_on"],
                   "prerequisites": "NOT_ASSESSED", "scientific_assurance": "UNKNOWN"}


def _locator(index):
    return "references/theory-tools.json#/cards/" + str(index)


def shortlist(signals, limit=3):
    """Match explicit signals; count matches only, with catalogue order breaking ties."""
    require(isinstance(signals, (list, tuple)) and 1 <= len(signals) <= 32, "Expected 1..32 signal strings")
    require(all(isinstance(signal, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", signal)
                for signal in signals), "Signals must be bounded lowercase identifiers")
    require(type(limit) is int and 1 <= limit <= 5, "Limit must be an integer in 1..5")
    requested = set(signals)
    cards, result = _load()
    matches = [(index, card, sorted(requested.intersection(card["tags"]))) for index, card in enumerate(cards)]
    matches = sorted((item for item in matches if item[2]), key=lambda item: (-len(item[2]), item[0]))[:limit]
    result["cards"] = [{"id": card["id"], "title": card["title"], "reason": "Matched: " + ", ".join(tags),
                        "matched_tags": tags, "required_inputs": card["required_inputs"], "locator": _locator(index)}
                       for index, card, tags in matches]
    result["unmatched_signal_count"] = len(requested - SIGNALS)
    return result


def get_card(card_id):
    require(isinstance(card_id, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", card_id), "Invalid theory card id")
    cards, result = _load()
    for index, card in enumerate(cards):
        if card["id"] == card_id:
            return {**result, "locator": _locator(index), "card": card}
    raise ValueError("Unknown theory card id: " + card_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--signals", nargs="+")
    mode.add_argument("--id")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    try:
        require(1 <= args.limit <= 5, "Limit must be an integer in 1..5")
        result = get_card(args.id) if args.id else shortlist(args.signals, args.limit)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({"status": "INVALID_INPUT", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
