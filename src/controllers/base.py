# src/controllers/base.py
from typing import Protocol

from src.types import ActionCommand, Observation


# ---------- Controller interface ----------

class DroneController(Protocol):
    def decide(self, observation: Observation) -> ActionCommand:
        ...
