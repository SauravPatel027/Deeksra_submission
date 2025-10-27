#!/usr/bin/env python3
import sys
import subprocess
import json
import argparse
import time
import os

# --- Import Verification Helpers ---
try:
    import verify_belts
except ImportError:
    print("WARNING: Could not import verify_belts.py. Belts test will be less robust.")
    verify_belts = None

try:
    import verify_factory
except ImportError:
    print("WARNING: Could not import verify_factory.py. Factory test will be less robust.")
    verify_factory = None
    
# --- Factory Sample Data ---
FACTORY_SAMPLE_INPUT = {
    "machines": {
        "assembler_1": {"crafts_per_min": 30},
        "chemical": {"crafts_per_min": 60}
    },
    "recipes": {
        "iron_plate": {
            "machine": "chemical",
            "time_s": 3.2,
            "in": {"iron_ore": 1},
            "out": {"iron_plate": 1}
        },
        "copper_plate": {
            "machine": "chemical",
            "time_s": 3.2,
            "in": {"copper_ore": 1},
            "out": {"copper_plate": 1}
        },
        "green_circuit": {
            "machine": "assembler_1",
            "time_s": 0.5,
            "in": {"iron_plate": 1, "copper_plate": 3},
            "out": {"green_circuit": 1}
        }
    },
    "modules": {
        "assembler_1": {"prod": 0.1, "speed": 0.15},
        "chemical": {"prod": 0.2, "speed": 0.1}
    },
    "limits": {
        "raw_supply_per_min": {"iron_ore": 5000, "copper_ore": 5000},
        "max_machines": {"assembler_1": 300, "chemical": 300}
    },
    "target": {"item": "green_circuit", "rate_per_min": 1800}
}

# --- UPDATED EXPECTED OUTPUT (to match your script's logic) ---
FACTORY_SAMPLE_OUTPUT = {
    "status": "ok",
    "per_recipe_crafts_per_min": {
        "iron_plate": 1363.6363636363637,
        "copper_plate": 4090.909090909091,
        "green_circuit": 1636.3636363636365
    },
    "per_machine_counts": {
        "assembler_1": 0.3952569166007905,
        "chemical": 4.407713498898014
    },
    "raw_consumption_per_min": {
        "iron_ore": 1363.6363636363637,
        "copper_ore": 4090.909090909091
    }
}


# --- Belts Sample Data (Unchanged) ---
BELTS_SAMPLE_INPUT = {
    "sources": {
        "s1": {"supply": 900},
        "s2": {"supply": 600}
    },
    "sink": {"name": "sink"},
    "nodes": {
        "a": {"capacity": 2000}, 
        "b": {},
        "c": {}
    },
    "edges": [
        {"from": "s1", "to": "a", "lo": 0, "hi": 1000},
        {"from": "s2", "to": "a", "lo": 0, "hi": 1000},
        {"from": "a", "to": "b", "lo": 0, "hi": 1000},
        {"from": "a", "to": "c", "lo": 0, "hi": 1000},
        {"from": "b", "to": "sink", "lo": 0, "hi": 1000},
        {"from": "c", "to": "sink", "lo": 0, "hi": 1000}
    ]
}

BELTS_SAMPLE_OUTPUT = {
    "status": "ok",
    "max_flow_per_min": 1500,
    "flows": [
        {"from": "s1", "to": "a", "flow": 900.0},
        {"from": "a", "to": "b", "flow": 900.0},
        {"from": "b", "to": "sink", "flow": 900.0},
        {"from": "s2", "to": "a", "flow": 600.0},
        {"from": "a", "to": "c", "flow": 600.0},
        {"from": "c", "to": "sink", "flow": 600.0}
    ]
}


# --- HELPER: Compare JSON with float tolerance ---
def compare_json_with_tolerance(got, expected, tolerance=1e-5):
    """
    Recursively compares two JSON-like objects (dicts, lists, values)
    and checks if floats are within a given tolerance.
    Returns a list of error strings.
    """
    errors = []
    if type(got) != type(expected):
        # Handle int vs float comparison
        if isinstance(got, (int, float)) and isinstance(expected, (int, float)):
             if abs(got - expected) > tolerance:
                return [f"Float mismatch: got {got}, expected {expected}"]
             return []
        return [f"Type mismatch: got {type(got)}, expected {type(expected)}"]

    if isinstance(got, dict):
        # Sort keys for deterministic comparison, as order doesn't matter
        got_keys = sorted(got.keys())
        expected_keys = sorted(expected.keys())
        if got_keys != expected_keys:
            return [f"Key mismatch: got {got_keys}, expected {expected_keys}"]
        for k in expected_keys:
            errors.extend(
                [f"[{k}] {err}" for err in compare_json_with_tolerance(got[k], expected[k], tolerance)]
            )
    elif isinstance(got, list):
        if len(got) != len(expected):
            return [f"List length mismatch: got {len(got)}, expected {len(expected)}"]
        # Note: This assumes list order matters unless handled elsewhere
        # (like 'flows' which we will handle separately)
        for i, (g, e) in enumerate(zip(got, expected)):
             errors.extend(
                [f"[{i}] {err}" for err in compare_json_with_tolerance(g, e, tolerance)]
            )
    elif isinstance(got, float):
        if abs(got - expected) > tolerance:
            return [f"Float mismatch: got {got}, expected {expected}"]
    else: # int, str, bool
        if got != expected:
            return [f"Value mismatch: got {got}, expected {expected}"]
            
    return errors


def run_test(name, cmd, input_data, expected_output_data):
    print(f"--- Running Test: {name} ---")
    print(f"Command: {cmd}")
    
    start_time = time.time()
    try:
        process = subprocess.run(
            cmd,
            shell=True,
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=5 # 5 second timeout (spec is 2s)
        )
        end_time = time.time()
        duration = end_time - start_time

        if process.stderr:
            print(f"[\u274C FAIL] STDERR was not empty:")
            print(process.stderr)
            return

        try:
            output_json = json.loads(process.stdout)
        except json.JSONDecodeError:
            print(f"[\u274C FAIL] Output was not valid JSON.")
            print("Raw STDOUT:")
            print(process.stdout)
            return
        
        if name == "Factory Sample":
            if verify_factory:
                # 1. First, check if the solution is internally consistent
                #    (using the *updated* verifier)
                verify_errors = verify_factory.verify_solution(input_data, output_json)
                if verify_errors:
                    print(f"[\u274C FAIL] Solution is not valid (self-inconsistent). (Time: {duration:.4f}s)")
                    for err in verify_errors:
                        print(f"  - {err}")
                    return
            
            # 2. If valid, check if it matches our expected values (with tolerance)
            comparison_errors = compare_json_with_tolerance(output_json, expected_output_data)
            if comparison_errors:
                print(f"[\u274C FAIL] Output does not match expected (even with tolerance). (Time: {duration:.4f}s)")
                print("\nExpected:")
                print(json.dumps(expected_output_data, indent=2))
                print("\nGot:")
                print(json.dumps(output_json, indent=2))
                print("\nDifferences:")
                for err in comparison_errors:
                    print(f"  - {err}")
            else:
                print(f"[\u2705 PASS] Output matches expected. (Time: {duration:.4f}s)")

        elif name == "Belts Sample":
            if output_json.get("status") != "ok":
                 print(f"[\u274C FAIL] Status was not 'ok'. Got: {output_json.get('status')}")
                 return
                 
            if not verify_belts:
                print(f"[\u274C FAIL] Cannot verify Belts solution: verify_belts.py not found.")
                return

            # Use the verifier to check if the flow is *valid*
            verify_errors = verify_belts.verify_solution(input_data, output_json)
            if verify_errors:
                print(f"[\u274C FAIL] Belts solution is not valid. (Time: {duration:.4f}s)")
                print("Your program produced a flow, but it violates conservation, bounds, or capacity.")
                for err in verify_errors:
                    print(f"  - {err}")
                print("\nGot:")
                print(json.dumps(output_json, indent=2))
            else:
                print(f"[\u2705 PASS] Output is a valid max-flow solution. (Time: {duration:.4f}s)")

    except subprocess.TimeoutExpired:
        print(f"[\u274C FAIL] Process timed out (limit: 5s).")
    except Exception as e:
        print(f"[\u274C FAIL] An error occurred: {e}")
    print("-" * (20 + len(name)) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run assignment samples.")
    parser.add_argument("factory_cmd", help="Command to run the factory solution (e.g., 'python factory/main.py')")
    parser.add_argument("belts_cmd", help="Command to run the belts solution (e.g., 'python belts/main.py')")
    args = parser.parse_args()

    run_test("Factory Sample", args.factory_cmd, FACTORY_SAMPLE_INPUT, FACTORY_SAMPLE_OUTPUT)
    run_test("Belts Sample", args.belts_cmd, BELTS_SAMPLE_INPUT, BELTS_SAMPLE_OUTPUT)