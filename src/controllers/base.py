from typing import Protocol

from types import ActionCommand, Observation


# ---------- Controller interface ----------

class DroneController(Protocol):
    def decide(self, observation: Observation) -> ActionCommand:
        ...
