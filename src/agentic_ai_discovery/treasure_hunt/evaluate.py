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
        print(
            f"  -> {summary['outcome']}, {summary['total_turns']} turns, "
            f"${summary['total_cost_usd']:.4f}, {summary['duration_s']}s"
        )

    successes = [r for r in runs if r["outcome"] == "success"]
    turns = [r["total_turns"] for r in runs]
    costs = [r["total_cost_usd"] for r in runs if r["total_cost_usd"] is not None]
    cache_reads = [r["cache_read_input_tokens"] for r in runs]

    return {
        "trials": trials,
        "runs": runs,
        "aggregate": {
            "success_rate": len(successes) / trials,
            "turns": _stats(turns),
            "cost_usd": _stats(costs) if costs else None,
            "cache_read_input_tokens": _stats(cache_reads),
        },
    }


def _print_summary(results: dict) -> None:
    agg = results["aggregate"]
    print("\n=== Evaluation summary ===")
    print(f"Trials: {results['trials']}")
    print(f"Success rate: {agg['success_rate'] * 100:.0f}%")
    print(f"Turns: mean {agg['turns']['mean']:.1f}, median {agg['turns']['median']:.1f}")
    if agg["cost_usd"]:
        print(f"Cost: mean ${agg['cost_usd']['mean']:.4f}, median ${agg['cost_usd']['median']:.4f}")
    cache = agg["cache_read_input_tokens"]
    print(f"Cache-read tokens: mean {cache['mean']:,.0f}, median {cache['median']:,.0f}")


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
