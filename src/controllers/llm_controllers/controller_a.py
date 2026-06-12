# src/controllers/llm_controllers/controller_a.py
from __future__ import annotations

import os
import requests
from dotenv import load_dotenv

from src.controllers.llm_controllers.safe_llm_controller import (
    SafeLLMController,
    SafeLLMControllerConfig,
)

load_dotenv() # reads the .env file in the project root

class OpenRouterClient:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise SystemExit(
                "Missing OPENROUTER_API_KEY. Create a .env file in the "
                "project root containing:\n  OPENROUTER_API_KEY=your-key-here"
            )


    def chat(self, model: str, prompt: str) -> str:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=30,
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]


#EDIT ME: write your prompt here
SYSTEM_PROMPT = """You are a drone navigating a maze. Reply with ONLY JSON
like {"action": "MOVE_NORTH", "message": ""}.
Valid actions: MOVE_NORTH, MOVE_SOUTH, MOVE_EAST, MOVE_WEST, SEND_MESSAGE, WAIT."""



# The no-argument wrapper the simulator will create.
# The class name here is what is typed on the command line.
class ControllerA:
    def __init__(self):
        self._controller = SafeLLMController(
            llm_client=OpenRouterClient(),
            # EDIT ME: pick your model
            model="openai/gpt-4o-mini",
            config=SafeLLMControllerConfig(),
        )

    def decide(self, observation):
        return self._controller.decide(observation)