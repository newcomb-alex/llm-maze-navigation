# scripts/run_single.py
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
    p.add_argument("--battery", type=int, default=30, help="Initial battery for both drones")
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
    p.add_argument("--seed", type=int, default=None, help="Random seed (optional)")
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


def _format_local_view(local_view: list[list[str]]) -> str:
    if not local_view:
        return "      <empty>"
    return "\n".join(f"      {' '.join(row)}" for row in local_view)


def _format_drone_block(label: str, payload: dict) -> str:
    obs = payload.get("observation", {})
    act = payload.get("action", {})
    st = payload.get("state", {})
    feedback = obs.get("last_action_feedback")

    lines: list[str] = [
        f"{label}:",
        "  1) Observation at start of step",
        f"    position={obs.get('position')} battery={obs.get('battery')} "
        f"incoming_message={obs.get('incoming_message')!r}",
        f"    next_goal={obs.get('next_goal')} goals_found={obs.get('goals_found')} "
        f"inspection_wait_remaining={obs.get('inspection_wait_remaining')}",
        "    local_view:",
        _format_local_view(obs.get("local_view", [])),
        f"    Action feedback (from previous/action resolution context): ",
        f"    {feedback}",
        "  2) Decision",
        f"    action={act.get('action')} message={act.get('message', '')!r}",
        "  4) State at end of step",
        f"    row={st.get('row')} col={st.get('col')} battery={st.get('battery')} "
        f"inspection_wait_remaining={st.get('inspection_wait_remaining')}",
    ]
    return "\n".join(lines)

def _build_base_grid(map_lines: list[str]) -> list[list[str]]:
    """
    Reconstruct the static terrain grid the way MazeSimulator does:
    parse the map and replace the 'A'/'B' start markers with empty cells '-'.
    Walls, goals, restricted ('X'), and wind ('W') cells are preserved.
    """
    grid = [list(row) for row in map_lines]
    for r, row in enumerate(grid):
        for c, val in enumerate(row):
            if val in ("A", "B"):
                grid[r][c] = "-"
    return grid


def _render_maze_ascii(base_grid: list[list[str]], step: dict) -> str:
    """
    Render the full maze for a single timestep as ASCII.

    The base_grid supplies static terrain (walls/goals/zones); the drones'
    end-of-step positions are read from the log step and overlaid as 'A'/'B'
    (or '*' if they share a cell, e.g. on a collision step).
    """
    if not base_grid:
        return "    <empty maze>"

    rows = len(base_grid)
    cols = len(base_grid[0])

    a_state = step.get("drone_A", {}).get("state", {})
    b_state = step.get("drone_B", {}).get("state", {})
    a_pos = (a_state.get("row"), a_state.get("col"))
    b_pos = (b_state.get("row"), b_state.get("col"))

    # Build an overlay copy so we never mutate the static base grid.
    overlay = [row[:] for row in base_grid]
    if a_pos == b_pos and None not in a_pos:
        r, c = a_pos
        overlay[r][c] = "*"  # both drones share a cell (e.g. collision)
    else:
        if None not in a_pos:
            overlay[a_pos[0]][a_pos[1]] = "A"
        if None not in b_pos:
            overlay[b_pos[0]][b_pos[1]] = "B"

    # Column header (0-indexed to match simulator coordinates).
    col_header = "        " + " ".join(f"{c:>2}" for c in range(cols))
    lines = [
        "  Maze state (end of step):",
        "    Legend: A/B=drones  *=both(collision)  #=wall  -=empty  "
        "X=restricted  W=wind  digit=goal",
        col_header,
    ]
    for r in range(rows):
        cells = " ".join(f"{overlay[r][c]:>2}" for c in range(cols))
        lines.append(f"    r{r:>2} {cells}")
    return "\n".join(lines)


def write_outputs(run_id: str, result: Any, seed: int, map_lines: list[str]) -> tuple[Path, Path, Path]:
    runs_dir = PROJECT_ROOT / "logs" / "runs"
    summaries_dir = PROJECT_ROOT / "logs" / "summaries"
    runs_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = runs_dir / f"{run_id}.jsonl"
    readable_log_path = runs_dir / f"{run_id}.readable.log"
    summary_path = summaries_dir / f"{run_id}.json"

    # Machine-readable
    with jsonl_path.open("w", encoding="utf-8") as f:
        for step in result.log:
            f.write(json.dumps(step, ensure_ascii=False) + "\n")

    # Static terrain layer used to render the full maze each step.
    base_grid = _build_base_grid(map_lines)

    # Human-readable
    with readable_log_path.open("w", encoding="utf-8") as f:
        for step in result.log:
            f.write(
                f"[t={step.get('timestep')}] status={step.get('status')} "
                f"reason={step.get('reason', '')!r} next_goal={step.get('next_goal')}\n"
            )
            f.write(_format_drone_block("drone_A", step.get("drone_A", {})) + "\n")
            f.write(_format_drone_block("drone_B", step.get("drone_B", {})) + "\n")
            # Full maze state, shown at the END of the step after both drones' blocks.
            f.write(_render_maze_ascii(base_grid, step) + "\n")
            f.write("-" * 72 + "\n")

    summary = {
        "run_id": run_id,
        "seed": seed,
        "status": result.status,
        "reason": result.reason,
        "steps": result.steps,
        "next_goal": result.next_goal,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return jsonl_path, readable_log_path, summary_path


def main() -> None:
    args = parse_args()
    used_seed = args.seed if args.seed is not None else random.SystemRandom().randrange(0, 2**32)
    random.seed(used_seed)

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
    jsonl_path, readable_log_path, summary_path = write_outputs(run_id, result, used_seed, map_lines)

    print(f"Run ID: {run_id}")
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Steps: {result.steps}")
    print(f"Next goal: {result.next_goal}")
    print(f"Step log (jsonl): {jsonl_path}")
    print(f"Step log (readable): {readable_log_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()