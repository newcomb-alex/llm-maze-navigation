#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


# Ensure project root import works when running from scripts/
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.simulator import MazeSimulator


ALLOWED_MAP_CHARS = set("#-ABXW0123456789")


class BuiltinWaitController:
    def decide(self, observation: Any) -> dict:
        return {"action": "WAIT", "message": ""}


class BuiltinRandomController:
    def decide(self, observation: Any) -> dict:
        valid = getattr(observation, "valid_actions", None) or [
            "MOVE_NORTH", "MOVE_SOUTH", "MOVE_EAST", "MOVE_WEST", "SEND_MESSAGE", "WAIT"
        ]
        action = random.choice(valid)
        if action == "SEND_MESSAGE":
            return {"action": "SEND_MESSAGE", "message": "Exploring current area."}
        return {"action": action, "message": ""}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run one maze simulation.")
    p.add_argument("--map", dest="map_path", required=True, help="Path to map txt, e.g. maps/easy_01.txt")
    p.add_argument("--battery", type=int, default=120, help="Initial battery for both drones")
    p.add_argument("--time-limit", type=int, default=300, help="Max timesteps")
    p.add_argument(
        "--controller-a",
        default="builtin:random",
        help='Controller spec for drone A. builtin:random | builtin:wait | "module.path:ClassName"',
    )
    p.add_argument(
        "--controller-b",
        default="builtin:random",
        help='Controller spec for drone B. builtin:random | builtin:wait | "module.path:ClassName"',
    )
    p.add_argument("--seed", type=int, default=7, help="Random seed")
    return p.parse_args()


def load_map_lines(map_path: Path) -> list[str]:
    if not map_path.exists():
        raise FileNotFoundError(f"Map file not found: {map_path}")

    lines: list[str] = []
    for raw in map_path.read_text(encoding="utf-8").splitlines():
        # Remove whitespace so both "###" and "# # #" styles can work
        line = "".join(ch for ch in raw if not ch.isspace())
        if not line:
            continue
        lines.append(line)

    if not lines:
        raise ValueError("Map is empty after removing whitespace/blank lines.")

    width = len(lines[0])
    for i, line in enumerate(lines, start=1):
        if len(line) != width:
            raise ValueError(f"Map must be rectangular. Line {i} has length {len(line)} vs expected {width}.")
        bad = [ch for ch in line if ch not in ALLOWED_MAP_CHARS]
        if bad:
            raise ValueError(f"Invalid char(s) on line {i}: {bad}. Allowed: {sorted(ALLOWED_MAP_CHARS)}")

    joined = "".join(lines)
    if joined.count("A") != 1:
        raise ValueError("Map must contain exactly one 'A'.")
    if joined.count("B") != 1:
        raise ValueError("Map must contain exactly one 'B'.")

    return lines


def build_controller(spec: str):
    if spec == "builtin:wait":
        return BuiltinWaitController()
    if spec == "builtin:random":
        return BuiltinRandomController()

    if ":" not in spec:
        raise ValueError(f'Invalid controller spec "{spec}". Use builtin:* or "module.path:ClassName".')

    module_name, class_name = spec.split(":", 1)
    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    return cls()


def write_outputs(run_id: str, result: Any) -> tuple[Path, Path]:
    runs_dir = PROJECT_ROOT / "logs" / "runs"
    summaries_dir = PROJECT_ROOT / "logs" / "summaries"
    runs_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = runs_dir / f"{run_id}.jsonl"
    summary_path = summaries_dir / f"{run_id}.json"

    with jsonl_path.open("w", encoding="utf-8") as f:
        for step in result.log:
            f.write(json.dumps(step, ensure_ascii=False) + "\n")

    summary = {
        "run_id": run_id,
        "status": result.status,
        "reason": result.reason,
        "steps": result.steps,
        "next_goal": result.next_goal,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return jsonl_path, summary_path


def main() -> None:
    args = parse_args()
    random.seed(args.seed)

    map_path = PROJECT_ROOT / args.map_path
    map_lines = load_map_lines(map_path)

    controller_a = build_controller(args.controller_a)
    controller_b = build_controller(args.controller_b)

    sim = MazeSimulator(
        map_lines=map_lines,
        controller_a=controller_a,
        controller_b=controller_b,
        initial_battery=args.battery,
        time_limit=args.time_limit,
    )
    result = sim.run()

    run_id = datetime.now().strftime("single_%Y%m%d_%H%M%S")
    jsonl_path, summary_path = write_outputs(run_id, result)

    print(f"Run ID: {run_id}")
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Steps: {result.steps}")
    print(f"Next goal: {result.next_goal}")
    print(f"Step log: {jsonl_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()