OBSERVATION_JSON_SCHEMA = {
    "type": "object",
    "required": [
        "drone_id",
        "timestep",
        "position",
        "battery",
        "local_view",
        "incoming_message",
        "last_action_feedback",
        "valid_actions",
        "next_goal",
        "goals_found",
        "inspection_wait_remaining",
    ],
    "properties": {
        "drone_id": {"type": "string"},
        "timestep": {"type": "integer", "minimum": 0},
        "position": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {"type": "integer", "minimum": 0},
        },
        "battery": {"type": "integer"},
        "local_view": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {"type": "string"},
            },
        },
        "incoming_message": {"type": ["string", "null"]},
        "last_action_feedback": {
            "type": ["object", "null"],
            "properties": {
                "status": {"type": "string", "enum": ["ok", "invalid", "forced_wait", "error"]},
                "reason": {"type": "string"},
                "attempted_action": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "valid_actions": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "MOVE_NORTH",
                    "MOVE_SOUTH",
                    "MOVE_EAST",
                    "MOVE_WEST",
                    "SEND_MESSAGE",
                    "WAIT",
                ],
            },
        },
        "next_goal": {"type": ["integer", "null"], "minimum": 1},
        "goals_found": {"type": "array", "items": {"type": "integer", "minimum": 1}},
        "inspection_wait_remaining": {"type": "integer", "minimum": 0},
    },
    "additionalProperties": False,
}

ACTION_JSON_SCHEMA = {
    "type": "object",
    "required": ["action", "message"],
    "properties": {
        "action": {
            "type": "string",
            "enum": [
                "MOVE_NORTH",
                "MOVE_SOUTH",
                "MOVE_EAST",
                "MOVE_WEST",
                "SEND_MESSAGE",
                "WAIT",
            ],
        },
        "message": {"type": "string"},
    },
    "additionalProperties": False,
}