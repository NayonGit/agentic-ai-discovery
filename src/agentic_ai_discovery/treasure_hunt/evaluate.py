import asyncio
import json
import os
import statistics
import time

from .agent import run_treasure_hunt

DEFAULT_TRIALS = 5


def _stats(values: list[float]) -> dict:
    return {"mean": statistics.mean(values), "median": statistics.median(values)}


async def run_evaluation(trials: int) -> dict:
    """Run the single-agent treasure hunt `trials` times, unattended
    (interactive=False - no dashboard rendering, no approval/step prompts),
    and return per-trial summaries plus aggregate stats. Sequential on
    purpose: simplest to reason about for a first version, and costs the
    same in tokens as running in parallel would."""
    runs = []
    for i in range(trials):
        print(f"[{i + 1}/{trials}] running...")
        started = time.monotonic()
        summary = await run_treasure_hunt(interactive=False)
        summary["duration_s"] = round(time.monotonic() - started, 1)
        runs.append(summary)
        found = "treasure found" if summary["treasure_found"] else "NOT found"
        print(
            f"  -> {summary['outcome']} ({found}), {summary['total_turns']} turns, "
            f"${summary['total_cost_usd']:.4f}, {summary['duration_s']}s"
        )

    # "treasure_found" is read directly off the game state - the ground truth.
    # The SDK's outcome=="success" only means the session ended without
    # tripping a guardrail; it's recorded too (as outcome_counts) because the
    # gap between the two is itself a real signal (e.g. a thrashing-autocompact
    # abort reports outcome="success" having never found the treasure).
    successes = [r for r in runs if r["treasure_found"]]
    turns = [r["total_turns"] for r in runs]
    costs = [r["total_cost_usd"] for r in runs if r["total_cost_usd"] is not None]
    cache_reads = [r["cache_read_input_tokens"] for r in runs]
    compactions = [r["compactions"] for r in runs]
    outcome_counts: dict[str, int] = {}
    for r in runs:
        outcome_counts[r["outcome"]] = outcome_counts.get(r["outcome"], 0) + 1

    return {
        "trials": trials,
        "runs": runs,
        "aggregate": {
            "success_rate": len(successes) / trials,
            "outcome_counts": outcome_counts,
            "turns": _stats(turns),
            "cost_usd": _stats(costs) if costs else None,
            "cache_read_input_tokens": _stats(cache_reads),
            "compactions": _stats(compactions),
            "compaction_rate": sum(1 for c in compactions if c > 0) / trials,
        },
    }


def _print_summary(results: dict) -> None:
    agg = results["aggregate"]
    print("\n=== Evaluation summary ===")
    print(f"Trials: {results['trials']}")
    print(f"Success rate (treasure actually found): {agg['success_rate'] * 100:.0f}%")
    print(f"SDK outcomes: {agg['outcome_counts']}")
    print(f"Turns: mean {agg['turns']['mean']:.1f}, median {agg['turns']['median']:.1f}")
    if agg["cost_usd"]:
        print(f"Cost: mean ${agg['cost_usd']['mean']:.4f}, median ${agg['cost_usd']['median']:.4f}")
    cache = agg["cache_read_input_tokens"]
    print(f"Cache-read tokens: mean {cache['mean']:,.0f}, median {cache['median']:,.0f}")
    comp = agg["compactions"]
    print(f"Compactions: mean {comp['mean']:.1f}, median {comp['median']:.1f} ({agg['compaction_rate'] * 100:.0f}% of trials)")


async def main_async() -> None:
    trials = int(os.environ.get("EVAL_TRIALS", DEFAULT_TRIALS))
    results = await run_evaluation(trials)
    _print_summary(results)

    out_path = os.environ.get("EVAL_OUTPUT", "transcripts/eval/baseline-scaled-map.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {out_path}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
