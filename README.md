# llm-maze-navigation

This project simulates two LLM drone controllers collaborating within a 2D maze environment to find goals while avoiding obstacles. Goals are numbered chronologically, and the controllers must find them in chronological order without colliding. Controllers can communicate to potentially find all goals more quickly. 

There are two obstacles introduced to test how well the controllers can balance positive rewards (goals) with negative rewards (wind zone, inspection zone). The two obstacles are:
1. Wind zone: Battery depletes more quickly here at -5 per time step rather than -1.
2. Inspection zone: The controller must wait for three time steps at an inspection zone, at which time it cannot communicate or receive communications.   

The parameters are set as command line arguments. The configurable parameters are:
1. Battery (default is 30, which decreases at -1 per time step)
2. Time step limit (default is 300 steps)  

The drones successfully complete the mission if: 
1. They find all goals in chronological order  

The drones fail the mission if: 
1. Either battery battery level reaches 0
2. A drone finds a goal out of order
3. The simulation reaches the time step limit
4. The two drones collide  

There are three maps of increasing difficulty. These maps can be found in maps/. 