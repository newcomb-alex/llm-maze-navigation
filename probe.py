# probe.py at project root
from src.schema import validate_observation_dict
from src.simulator import MazeSimulator, VALID_ACTIONS

# build a throwaway sim just to grab one real observation
class Stub:
    def decide(self, obs): return {"action": "WAIT", "message": ""}

lines = [l for l in open("maps/easy_01.txt").read().splitlines() if l.strip()]
lines = ["".join(ch for ch in l if not ch.isspace()) for l in lines]
sim = MazeSimulator(lines, Stub(), Stub())
obs = sim._build_observation(sim.drone_a, None)
obs_dict = obs.to_dict()

print("OBS DICT:", obs_dict)
print("OBS ERRORS:", validate_observation_dict(obs_dict))