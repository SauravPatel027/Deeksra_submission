import pytest
import subprocess
import json
import os
import sys

# Add helpers to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import verify_factory
except ImportError:
    print("Warning: Could not import verify_factory.py for extended validation.")
    verify_factory = None


# Get the command to run from environment variable
FACTORY_CMD = os.environ.get("FACTORY_CMD")
if not FACTORY_CMD:
    print("Skipping tests: FACTORY_CMD environment variable not set.")
    pytest.skip("FACTORY_CMD not set", allow_module_level=True)


# --- Test Case Data ---
SAMPLE_INPUT = {
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

# --- UPDATED EXPECTED OUTPUT ---
CORRECTED_OUTPUT = {
    "status": "ok",
    "per_recipe_crafts_per_min": {
        "green_circuit": 1636.3636363636365,
        "iron_plate": 1363.6363636363637,
        "copper_plate": 4090.909090909091
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

# --- Infeasible Case (Unchanged) ---
INFEASIBLE_INPUT = {
    "machines": {
        "assembler_1": {"crafts_per_min": 30}
    },
    "recipes": {
         "green_circuit": {
            "machine": "assembler_1",
            "time_s": 0.5,
            "in": {"iron_plate": 1},
            "out": {"green_circuit": 1}
        }
    },
    "modules": {},
    "limits": {
        "raw_supply_per_min": {"iron_plate": 100}, # Bottleneck
        "max_machines": {"assembler_1": 1}        # Also a bottleneck
    },
    "target": {"item": "green_circuit", "rate_per_min": 9999}
}

# --- Helper Function ---
def run_command(input_data, timeout=2.0):
    try:
        process = subprocess.run(
            FACTORY_CMD,
            shell=True,
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=timeout
        )
        return process
    except subprocess.TimeoutExpired:
        pytest.fail(f"Process exceeded time limit of {timeout}s.")
    except Exception as e:
        pytest.fail(f"Process failed to run: {e}")

def assert_json_floats_close(d1, d2, rel_tol=1e-6, abs_tol=1e-9):
    """Recursively compare dicts/lists, allowing floats to be 'close'."""
    assert type(d1) == type(d2)
    if isinstance(d1, dict):
        assert sorted(d1.keys()) == sorted(d2.keys())
        for k in d1:
            assert_json_floats_close(d1[k], d2[k], rel_tol, abs_tol)
    elif isinstance(d1, list):
        assert len(d1) == len(d2)
        for i, _ in enumerate(d1):
            assert_json_floats_close(d1[i], d2[i], rel_tol, abs_tol)
    elif isinstance(d1, (float, int)):
        assert d1 == pytest.approx(d2, rel=rel_tol, abs=abs_tol)
    else:
        assert d1 == d2


# --- Pytest Tests ---

def test_sample_case_stdout():
    """Test that the sample case produces no stderr and valid JSON on stdout."""
    process = run_command(SAMPLE_INPUT)
    assert process.stderr == "", "STDERR should be empty on success"
    
    try:
        output_json = json.loads(process.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"Output was not valid JSON. Got:\n{process.stdout}")
    
    assert "status" in output_json, "Output JSON must have a 'status' key"

def test_sample_case_correctness():
    """Test the sample case against the corrected output values."""
    process = run_command(SAMPLE_INPUT)
    try:
        output_json = json.loads(process.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"Output was not valid JSON. Got:\n{process.stdout}")

    assert output_json.get("status") == "ok"
    
    # Use approx comparison for floats
    assert_json_floats_close(output_json, CORRECTED_OUTPUT)

def test_sample_case_verification():
    """Test if the output is self-consistent using the verify script."""
    if not verify_factory:
        pytest.skip("verify_factory.py not available")

    process = run_command(SAMPLE_INPUT)
    try:
        output_json = json.loads(process.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"Output was not valid JSON. Got:\n{process.stdout}")
    
    if output_json.get("status") != "ok":
        # Handle cases where the solver might fail, even if it shouldn't
        if output_json.get("status") == "infeasible":
             pytest.fail(f"Solver reported 'infeasible' for a known 'ok' case. Max rate: {output_json.get('max_feasible_target_per_min')}")
        pytest.fail(f"Solver did not return status: ok. Got: {output_json.get('status')}")

    # Run the verification logic (which now uses the correct PDF formula)
    try:
        errors = verify_factory.verify_solution(SAMPLE_INPUT, output_json)
        if errors:
            pytest.fail("Verification script found errors:\n" + "\n".join(errors))
    except Exception as e:
        pytest.fail(f"Verification script failed: {e}")


def test_infeasible_case():
    """Test that an impossible request returns an 'infeasible' status."""
    process = run_command(INFEASIBLE_INPUT)
    try:
        output_json = json.loads(process.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"Output was not valid JSON. Got:\n{process.stdout}")
    
    assert output_json.get("status") == "infeasible"
    assert "max_feasible_target_per_min" in output_json
    assert "bottleneck_hint" in output_json
    assert isinstance(output_json["max_feasible_target_per_min"], (int, float))
    assert isinstance(output_json["bottleneck_hint"], list)