import pytest
import subprocess
import json
import os
import sys

# Add helpers to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    import verify_belts
except ImportError:
    print("Warning: Could not import verify_belts.py for extended validation.")
    verify_belts = None


# Get the command to run from environment variable
BELTS_CMD = os.environ.get("BELTS_CMD")
if not BELTS_CMD:
    print("Skipping tests: BELTS_CMD environment variable not set.")
    pytest.skip("BELTS_CMD not set", allow_module_level=True)


# --- Test Case Data ---
SAMPLE_INPUT = {
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

SAMPLE_OUTPUT = {
    "status": "ok",
    "max_flow_per_min": 1500.0,
    "flows": [
        {"from": "s1", "to": "a", "flow": 900.0},
        {"from": "s2", "to": "a", "flow": 600.0},
        {"from": "a", "to": "b", "flow": 900.0},
        {"from": "a", "to": "c", "flow": 600.0},
        {"from": "b", "to": "sink", "flow": 900.0},
        {"from": "c", "to": "sink", "flow": 600.0}
    ]
}

INFEASIBLE_INPUT = {
    "sources": {
        "s1": {"supply": 1000}
    },
    "sink": {"name": "sink"},
    "nodes": {},
    "edges": [
        # Bottleneck edge
        {"from": "s1", "to": "sink", "lo": 0, "hi": 500} 
    ]
}


# --- Helper Function ---
def run_command(input_data, timeout=2.0):
    try:
        process = subprocess.run(
            BELTS_CMD,
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

def normalize_flows(output_json):
    """Sorts the 'flows' list to allow deterministic comparison."""
    if "flows" in output_json and isinstance(output_json["flows"], list):
        try:
            output_json["flows"] = sorted(
                output_json["flows"], 
                key=lambda x: (x.get("from", ""), x.get("to", ""))
            )
        except (AttributeError, TypeError):
            pass # Ignore if items aren't dicts
    return output_json

def assert_json_floats_close(d1, d2, rel_tol=1e-6, abs_tol=1e-9):
    """Recursively compare dicts/lists, allowing floats to be 'close'."""
    assert type(d1) == type(d2)
    if isinstance(d1, dict):
        assert d1.keys() == d2.keys()
        for k in d1:
            assert_json_floats_close(d1[k], d2[k], rel_tol, abs_tol)
    elif isinstance(d1, list):
        # Handle empty lists
        if len(d1) == 0 and len(d2) == 0:
            return
        # Assumes lists are pre-sorted if order matters (like flows)
        assert len(d1) == len(d2)
        for i, _ in enumerate(d1):
            assert_json_floats_close(d1[i], d2[i], rel_tol, abs_tol)
    elif isinstance(d1, float):
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
    """Test the sample case against the expected output values."""
    process = run_command(SAMPLE_INPUT)
    try:
        output_json = json.loads(process.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"Output was not valid JSON. Got:\n{process.stdout}")

    assert output_json.get("status") == "ok"
    
    # Normalize flow order before comparison
    norm_output = normalize_flows(output_json)
    norm_expected = normalize_flows(SAMPLE_OUTPUT)
    
    assert_json_floats_close(norm_output, norm_expected)

def test_sample_case_verification():
    """Test if the output is self-consistent using the verify script."""
    if not verify_belts:
        pytest.skip("verify_belts.py not available")

    process = run_command(SAMPLE_INPUT)
    output_json = json.loads(process.stdout)
    
    if output_json.get("status") != "ok":
        pytest.fail("Solver did not return status: ok")

    # Run the verification logic
    try:
        errors = verify_belts.verify_solution(SAMPLE_INPUT, output_json)
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
    assert "cut_reachable" in output_json
    assert "deficit" in output_json
    assert isinstance(output_json["cut_reachable"], list)
    assert isinstance(output_json["deficit"], dict)