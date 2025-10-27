#!/usr/bin/env python3
import json
import sys

def generate_simple_case():
    """Generates a simple 'diamond' graph."""
    
    case = {
        "sources": {
            "s1": {"supply": 500}
        },
        "sink": {"name": "sink"},
        "nodes": {
            "a": {},
            "b": {"capacity": 200} # Bottleneck node
        },
        "edges": [
            {"from": "s1", "to": "a", "lo": 0, "hi": 1000},
            {"from": "s1", "to": "b", "lo": 0, "hi": 1000},
            {"from": "a", "to": "sink", "lo": 0, "hi": 400}, # Bottleneck edge
            {"from": "b", "to": "sink", "lo": 100, "hi": 300} # With lower bound
        ]
    }
    return case

if __name__ == "__main__":
    # Generate the case and print it to stdout as JSON
    test_case = generate_simple_case()
    print(json.dumps(test_case, indent=2))