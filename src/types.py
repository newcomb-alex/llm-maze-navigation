# src/types.py
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, Optional, TypedDict

import json

ActionName = Literal[
    "MOVE_NORTH",
    "MOVE_SOUTH",
    "MOVE_EAST",
    "MOVE_WEST",
    "SEND_MESSAGE",
    "WAIT",
]

ActionStatus = Literal["ok", "invalid", "forced_wait", "error"]


class ActionFeedback(TypedDict, total=False):
    status: ActionStatus
    reason: str
    attempted_action: str


@dataclass
class Observation:
    drone_id: str
    timestep: int
    position: tuple[int, int]              # (row, col), 0-indexed
    battery: int
    local_view: list[list[str]]            # 3x3 centered on drone by default
    incoming_message: Optional[str]
    last_action_feedback: Optional[ActionFeedback]
    valid_actions: list[ActionName]
    next_goal: Optional[int]               # None if no goals or all found
    goals_found: list[int] = field(default_factory=list)
    inspection_wait_remaining: int = 0

    def to_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self)))


@dataclass
class ActionCommand:
    action: ActionName
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)