# src/simulator.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.types import ActionCommand, ActionName, Observation
from src.controllers.base import DroneController

# ---------- Internal state ----------

VALID_ACTIONS: list[ActionName] = [
    "MOVE_NORTH",
    "MOVE_SOUTH",
    "MOVE_EAST",
    "MOVE_WEST",
    "SEND_MESSAGE",
    "WAIT",
]

MOVE_DELTA: dict[ActionName, tuple[int, int]] = {
    "MOVE_NORTH": (-1, 0),
    "MOVE_SOUTH": (1, 0),
    "MOVE_EAST": (0, 1),
    "MOVE_WEST": (0, -1),
    "SEND_MESSAGE": (0, 0),
    "WAIT": (0, 0),
}


@dataclass
class DroneState:
    drone_id: str
    row: int
    col: int
    battery: int
    controller: DroneController
    goals_found: list[int] = field(default_factory=list) # safe default, each instance has its own empty list
    inspection_wait_remaining: int = 0
    last_action_feedback: dict | None = None


@dataclass
class SimulationResult:
    status: str  # "success" or "failure" or "timeout"
    reason: str
    steps: int
    next_goal: int
    log: list[dict]


class MazeSimulator:
    """
    Minimal 2-drone simulator.
    Rules included:
    - walls '#', empty '-', restricted 'X', wind 'W', goals '1','2',...
    - strict goal order
    - move invalid into wall/out-of-bounds
    - restricted zone entry => next 3 steps forced wait, no send/receive
    - wind cell battery drain -5, otherwise -1
    - message sent at t arrives at t+1
    - collision: same-cell or swap
    """

    def __init__(
        self,
        map_lines: list[str],
        controller_a: DroneController,
        controller_b: DroneController,
        initial_battery: int = 30,
        time_limit: int = 300,
    ) -> None:
        self.grid = [list(row) for row in map_lines] # turns each string row into a list of characters, becomes list of list of chars
        self.rows = len(self.grid)
        self.cols = len(self.grid[0]) if self.rows else 0
        self.time_limit = time_limit
        self.timestep = 0
        self.log: list[dict] = []

        a_pos = self._find_char("A")
        b_pos = self._find_char("B")
        if a_pos is None or b_pos is None:
            raise ValueError("Map must contain both 'A' and 'B' start markers.")

        # Replace start markers with empty cells in base grid
        self.grid[a_pos[0]][a_pos[1]] = "-"
        self.grid[b_pos[0]][b_pos[1]] = "-"

        self.drone_a = DroneState("drone_A", a_pos[0], a_pos[1], initial_battery, controller_a)
        self.drone_b = DroneState("drone_B", b_pos[0], b_pos[1], initial_battery, controller_b)

        self.goal_numbers = self._extract_goals_sorted()
        self.next_goal_idx = 0  # points into self.goal_numbers

        # messages delivered this step
        self.inbox: dict[str, str | None] = {"drone_A": None, "drone_B": None}

    # ---------- Public ----------

    def run(self) -> SimulationResult:
        for _ in range(self.time_limit):
            done, status, reason = self.step()
            if done:
                return SimulationResult(status=status, reason=reason, steps=self.timestep, next_goal=self.current_next_goal(), log=self.log)

        return SimulationResult(
            status="timeout",
            reason="Exceeded time step limit.",
            steps=self.timestep,
            next_goal=self.current_next_goal(),
            log=self.log,
        )

    def step(self) -> tuple[bool, str, str]:
        self.timestep += 1

        # 1) Build observations
        obs_a = self._build_observation(self.drone_a, self.inbox["drone_A"])
        obs_b = self._build_observation(self.drone_b, self.inbox["drone_B"])

        # 2) Controllers decide
        cmd_a = self._safe_decide(self.drone_a, obs_a)
        cmd_b = self._safe_decide(self.drone_b, obs_b)

        # 3) Apply forced wait for restricted inspection
        cmd_a = self._apply_forced_wait_if_needed(self.drone_a, cmd_a)
        cmd_b = self._apply_forced_wait_if_needed(self.drone_b, cmd_b)

        # 4) Resolve movement intents
        old_a = (self.drone_a.row, self.drone_a.col)
        old_b = (self.drone_b.row, self.drone_b.col)

        new_a = self._resolve_single_move(self.drone_a, cmd_a)
        new_b = self._resolve_single_move(self.drone_b, cmd_b)

        # 5) Collision checks (same-cell or swap)
        if new_a == new_b or (new_a == old_b and new_b == old_a):
            self._append_log(obs_a, obs_b, cmd_a, cmd_b, "failure", "Collision occurred.")
            return True, "failure", "Collision occurred."

        # 6) Apply positions
        entered_x_a = self._cell(new_a) == "X" and new_a != old_a
        entered_x_b = self._cell(new_b) == "X" and new_b != old_b
        self.drone_a.row, self.drone_a.col = new_a
        self.drone_b.row, self.drone_b.col = new_b

        if entered_x_a:
            self.drone_a.inspection_wait_remaining = 3
        if entered_x_b:
            self.drone_b.inspection_wait_remaining = 3

        # 7) Goal checks (strict order)
        ok, reason = self._check_goals_ordered()
        if not ok:
            self._append_log(obs_a, obs_b, cmd_a, cmd_b, "failure", reason)
            return True, "failure", reason

        # 8) Battery drain
        self._drain_battery(self.drone_a)
        self._drain_battery(self.drone_b)

        if self.drone_a.battery <= 0 or self.drone_b.battery <= 0:
            self._append_log(obs_a, obs_b, cmd_a, cmd_b, "failure", "Battery depleted.")
            return True, "failure", "Battery depleted."

        # 9) Success check
        if self.next_goal_idx >= len(self.goal_numbers):
            self._append_log(obs_a, obs_b, cmd_a, cmd_b, "success", "All goals reached in order.")
            return True, "success", "All goals reached in order."

        # 10) Message delivery for next step
        next_inbox = {"drone_A": None, "drone_B": None}
        self._queue_message(self.drone_a, cmd_a, receiver=self.drone_b, next_inbox=next_inbox)
        self._queue_message(self.drone_b, cmd_b, receiver=self.drone_a, next_inbox=next_inbox)
        self.inbox = next_inbox

        self._append_log(obs_a, obs_b, cmd_a, cmd_b, "running", "")
        return False, "running", ""

    # ---------- Observation and actions ----------

    def _build_observation(self, d: DroneState, incoming_message: str | None) -> Observation:
        # cannot receive while under inspection
        if d.inspection_wait_remaining > 0:
            incoming_message = None

        return Observation(
            drone_id=d.drone_id,
            timestep=self.timestep,
            position=(d.row, d.col),
            battery=d.battery,
            local_view=self._local_view_3x3(d.row, d.col),
            incoming_message=incoming_message,
            last_action_feedback=d.last_action_feedback,
            valid_actions=VALID_ACTIONS,
            next_goal=self.current_next_goal(),
            goals_found=list(d.goals_found),
            inspection_wait_remaining=d.inspection_wait_remaining,
        )

    def _safe_decide(self, d: DroneState, obs: Observation) -> ActionCommand:
        try:
            out = d.controller.decide(obs)
            if isinstance(out, dict):
                action = out.get("action", "WAIT")
                message = out.get("message", "")
                out = ActionCommand(action=action, message=message)
            if out.action not in VALID_ACTIONS:
                d.last_action_feedback = {"status": "invalid", "reason": "Unknown action.", "attempted_action": str(out.action)}
                return ActionCommand(action="WAIT", message="")
            return out
        except Exception as e:
            d.last_action_feedback = {"status": "error", "reason": f"Controller error: {e}"}
            return ActionCommand(action="WAIT", message="")

    def _apply_forced_wait_if_needed(self, d: DroneState, cmd: ActionCommand) -> ActionCommand:
        if d.inspection_wait_remaining > 0:
            d.inspection_wait_remaining -= 1
            d.last_action_feedback = {
                "status": "forced_wait",
                "reason": "Restricted airspace inspection in progress.",
                "attempted_action": cmd.action,
            }
            return ActionCommand(action="WAIT", message="")
        return cmd

    def _resolve_single_move(self, d: DroneState, cmd: ActionCommand) -> tuple[int, int]:
        if cmd.action in ("SEND_MESSAGE", "WAIT"):
            d.last_action_feedback = {"status": "ok", "reason": "No movement action.", "attempted_action": cmd.action}
            return (d.row, d.col)

        dr, dc = MOVE_DELTA[cmd.action]
        nr, nc = d.row + dr, d.col + dc

        if not self._in_bounds(nr, nc) or self.grid[nr][nc] == "#":
            d.last_action_feedback = {"status": "invalid", "reason": "Blocked by wall/boundary.", "attempted_action": cmd.action}
            return (d.row, d.col)

        d.last_action_feedback = {"status": "ok", "reason": "Move applied.", "attempted_action": cmd.action}
        return (nr, nc)

    # ---------- Rules ----------

    def _check_goals_ordered(self) -> tuple[bool, str]:
        next_goal = self.current_next_goal()
        if next_goal is None:
            return True, ""

        goal_char = str(next_goal)
        a_pos = (self.drone_a.row, self.drone_a.col)
        b_pos = (self.drone_b.row, self.drone_b.col)
        a_cell = self._cell((self.drone_a.row, self.drone_a.col))
        b_cell = self._cell((self.drone_b.row, self.drone_b.col))

        # Any out-of-order goal contact is failure.
        for c in (a_cell, b_cell):
            if c.isdigit() and int(c) != next_goal:
                return False, f"Goal reached out of order: touched {c} before {next_goal}."

        # Correct next goal reached by either drone.
        if a_cell == goal_char or b_cell == goal_char:
            if a_cell == goal_char:
                self.grid[a_pos[0]][a_pos[1]] = "-"
            if b_cell == goal_char:
                self.grid[b_pos[0]][b_pos[1]] = "-"
            self.drone_a.goals_found.append(next_goal)
            self.drone_b.goals_found.append(next_goal)
            self.next_goal_idx += 1

        return True, ""

    def _drain_battery(self, d: DroneState) -> None:
        cell = self._cell((d.row, d.col))
        d.battery -= 5 if cell == "W" else 1

    def _queue_message(
        self,
        sender: DroneState,
        cmd: ActionCommand,
        receiver: DroneState,
        next_inbox: dict[str, str | None],
    ) -> None:
        if cmd.action != "SEND_MESSAGE":
            return
        if sender.inspection_wait_remaining > 0:
            return  # cannot communicate while inspected
        if receiver.inspection_wait_remaining > 0:
            return  # cannot receive while inspected
        if not cmd.message.strip():
            return
        next_inbox[receiver.drone_id] = cmd.message.strip()

    # ---------- Helpers ----------

    def current_next_goal(self) -> int | None:
        if self.next_goal_idx >= len(self.goal_numbers):
            return None
        return self.goal_numbers[self.next_goal_idx]

    def _extract_goals_sorted(self) -> list[int]:
        goals = set()
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c].isdigit():
                    goals.add(int(self.grid[r][c]))
        return sorted(goals)

    def _find_char(self, ch: str) -> tuple[int, int] | None:
        for r, row in enumerate(self.grid):
            for c, val in enumerate(row):
                if val == ch:
                    return r, c
        return None

    def _in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols

    def _cell(self, pos: tuple[int, int]) -> str:
        r, c = pos
        return self.grid[r][c]

    def _overlay_cell(self, r: int, c: int) -> str:
        if (r, c) == (self.drone_a.row, self.drone_a.col):
            return "A"
        if (r, c) == (self.drone_b.row, self.drone_b.col):
            return "B"
        return self.grid[r][c]

    def _local_view_3x3(self, r: int, c: int) -> list[list[str]]:
        out: list[list[str]] = []
        for rr in range(r - 1, r + 2):
            row: list[str] = []
            for cc in range(c - 1, c + 2):
                if not self._in_bounds(rr, cc):
                    row.append("#")
                else:
                    row.append(self._overlay_cell(rr, cc))
            out.append(row)
        return out

    def _append_log(
        self,
        obs_a: Observation,
        obs_b: Observation,
        cmd_a: ActionCommand,
        cmd_b: ActionCommand,
        status: str,
        reason: str,
    ) -> None:
        self.log.append(
            {
                "timestep": self.timestep,
                "status": status,
                "reason": reason,
                "drone_A": {
                    "observation": obs_a.to_dict(),
                    "action": cmd_a.to_dict(),
                    "state": {
                        "row": self.drone_a.row,
                        "col": self.drone_a.col,
                        "battery": self.drone_a.battery,
                        "inspection_wait_remaining": self.drone_a.inspection_wait_remaining,
                    },
                },
                "drone_B": {
                    "observation": obs_b.to_dict(),
                    "action": cmd_b.to_dict(),
                    "state": {
                        "row": self.drone_b.row,
                        "col": self.drone_b.col,
                        "battery": self.drone_b.battery,
                        "inspection_wait_remaining": self.drone_b.inspection_wait_remaining,
                    },
                },
                "next_goal": self.current_next_goal(),
            }
        )