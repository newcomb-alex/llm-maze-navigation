# src/controllers/llm_controllers/controller_a.py
from __future__ import annotations

import os
from collections import deque

import requests
from dotenv import load_dotenv

from src.controllers.llm_controllers.safe_llm_controller import (
    SafeLLMController,
    SafeLLMControllerConfig,
)

load_dotenv()  # reads the .env file in the project root


# ---------------- Memory ----------------

class DroneMemory:
    """Memory policy: the last N actions taken + every message received from drone B."""

    def __init__(self, max_moves: int = 5):
        self.moves: deque[str] = deque(maxlen=max_moves)
        self.messages: list[str] = []

    def record_observation(self, obs) -> None:
        """Store any incoming message and tag the previous move with its outcome."""
        if obs.incoming_message:
            self.messages.append(f"t{obs.timestep}: {obs.incoming_message}")

        feedback = obs.last_action_feedback
        if feedback and self.moves:
            self.moves[-1] += f" -> {feedback.get('status', 'unknown')}"

    def record_action(self, obs, cmd) -> None:
        """Store the action actually returned to the simulator."""
        detail = f' "{cmd.message}"' if cmd.action == "SEND_MESSAGE" and cmd.message else ""
        self.moves.append(f"t{obs.timestep} at {tuple(obs.position)}: {cmd.action}{detail}")

    def as_prompt(self) -> str:
        moves = "\n".join(self.moves) or "none"
        messages = "\n".join(self.messages) or "none"
        return (
            "MEMORY\n"
            f"Your last {self.moves.maxlen} actions (oldest first, with outcome):\n{moves}\n"
            f"All messages received from drone B so far:\n{messages}\n"
        )


# ---------------- LLM client ----------------

class OpenRouterClient:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise SystemExit(
                "Missing OPENROUTER_API_KEY. Create a .env file in the "
                "project root containing:\n  OPENROUTER_API_KEY=your-key-here"
            )
        self.memory_text = ""  # set by ControllerA before each call

    def chat(self, model: str, prompt: str) -> str:
        user_content = f"{self.memory_text}\n{prompt}" if self.memory_text else prompt
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            },
            timeout=30,
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]


# EDIT ME: enter prompt here
SYSTEM_PROMPT = """You are a drone navigating a maze.

You must find each numbered goal the correct order by communicating with drone B.
"X" - inspection zone. Only pass through if necessary. Upon entering this cell, three time steps will pass in which you cannot move or make communications.
"W" - wind zone. Only pass through if necessary. Entering a wind zone will drain the battery more quickly. Here, the battery will decrease by -5 instead of by -1 for each time step in which you remain in that cell.
"#" - wall. Do not attempt to move into. It will waste battery and result in no movement.
"-" - empty. This is the zone you will most commonly navigate.
"1" - first goal. To "complete" a goal, drone must enter the cell. Goals must be completed in chronological order. e.g.: "1", "2", "3", etc., or else attempt will be failed.
You may not enter 2 before 1, or 3 before 2, etc.
Before making a decision, assess the local view in a 3x3 grid manner, where you are at the center.

E.g. You will be given an observation of the local view in each time step in the following format:
local_view=[['#', '#', '#'], ['#', 'A', '-'], ['#', '-', '#']]
The first list is the view directly above (north of) you, the second list is your current row (showing east/west cells), and the third list is the view directly below (south) of you.
In this instance, the only options would be to move west, or south, with the consideration that there is a wind zone south, or to simply use this time step to communicate your location and findings with drone B.

You are also given a MEMORY block containing your last 5 actions (with their outcomes) and
every message drone B has sent you. Use it to avoid repeating invalid moves, to avoid
re-walking cells you just came from, and to act on what drone B has already reported.

Only if point a, b, or obstacles W or X is found, communicate their location with drone B. Ask drone B for an update on location.

Reply with ONLY JSON like {"action": "MOVE_NORTH", "message": ""}.
Valid actions: MOVE_NORTH, MOVE_SOUTH, MOVE_EAST, MOVE_WEST, SEND_MESSAGE, WAIT."""


class ControllerA:
    def __init__(self):
        self._client = OpenRouterClient()
        self._memory = DroneMemory(max_moves=5)
        self._controller = SafeLLMController(
            llm_client=self._client,
            # EDIT ME: pick your model
            model="google/gemini-2.5-flash",
            config=SafeLLMControllerConfig(),
        )

    def decide(self, observation):
        self._memory.record_observation(observation)
        self._client.memory_text = self._memory.as_prompt()
        command = self._controller.decide(observation)
        self._memory.record_action(observation, command)
        return command