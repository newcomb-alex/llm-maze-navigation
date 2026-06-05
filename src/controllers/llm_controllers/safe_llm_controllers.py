# src/controllers/llm_controllers/safe_llm_controller.py
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.controllers.base import DroneController
from src.types import ActionCommand, Observation
from src.schema import validate_observation_dict, validate_action_dict


@dataclass
class SafeLLMControllerConfig:
    strict_observation_validation: bool = True
    max_message_chars: int = 160


class SafeLLMController(DroneController):
    def __init__(self, llm_client, model: str, config: SafeLLMControllerConfig | None = None):
        self.llm_client = llm_client
        self.model = model
        self.config = config or SafeLLMControllerConfig()

    def decide(self, observation: Observation) -> ActionCommand:
        obs_dict = observation.to_dict()

        # 1) Validate simulator to LLM payload
        obs_errors = validate_observation_dict(obs_dict)
        if obs_errors and self.config.strict_observation_validation:
            return ActionCommand(action="WAIT", message="")

        # 2) Call LLM
        raw_text = self._call_llm(obs_dict)

        # 3) Parse LLM output to dict
        action_dict = self._parse_json_object(raw_text)
        if action_dict is None:
            return ActionCommand(action="WAIT", message="")

        # 4) Validate LLM to simulator payload
        action_errors = validate_action_dict(action_dict)
        if action_errors:
            return ActionCommand(action="WAIT", message="")

        # 5) Normalize
        action = action_dict["action"]
        message = action_dict.get("message", "")

        if action != "SEND_MESSAGE":
            message = ""
        message = message[: self.config.max_message_chars]

        return ActionCommand(action=action, message=message)

    def _call_llm(self, obs_dict: dict) -> str:
        prompt = (
            "Return ONLY JSON with keys action,message.\n"
            f"Observation:\n{json.dumps(obs_dict, ensure_ascii=False)}"
        )
        # Adapt to your OpenRouter client
        resp = self.llm_client.chat(model=self.model, prompt=prompt)
        return resp

    def _parse_json_object(self, text: str) -> dict | None:
        text = text.strip()

        # Strip ```json ... ```
        text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None