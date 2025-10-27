#!/usr/bin/env python3
import json
import sys

def generate_simple_case():
    """Generates a simple 2-step (ore -> plate -> rod) factory."""
    
    case = {
        "machines": {
            "smelter": {"crafts_per_min": 60},
            "assembler": {"crafts_per_min": 30}
        },
        "recipes": {
            "iron_plate": {
                "machine": "smelter",
                "time_s": 3.0,
                "in": {"iron_ore": 1},
                "out": {"iron_plate": 1}
            },
            "iron_rod": {
                "machine": "assembler",
                "time_s": 0.5,
                "in": {"iron_plate": 1},
                "out": {"iron_rod": 2}
            }
        },
        "modules": {
            "smelter": {"speed": 0.5}, # 50% speed
            "assembler": {"prod": 0.2} # 20% productivity
        },
        "limits": {
            "raw_supply_per_min": {"iron_ore": 1000},
            "max_machines": {"smelter": 10, "assembler": 10}
        },
        "target": {"item": "iron_rod", "rate_per_min": 120}
    }
    return case

if __name__ == "__main__":
    # Generate the case and print it to stdout as JSON
    test_case = generate_simple_case()
    print(json.dumps(test_case, indent=2))