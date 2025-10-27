#!/usr/bin/env python3
import json
import sys
import argparse
from collections import defaultdict

TOL = 1e-9

def verify_solution(in_data, out_data):
    """
    Checks if the output solution is valid for the given input.
    Returns a list of error strings.
    """
    errors = []
    
    if out_data.get("status") != "ok":
        errors.append(f"Status is not 'ok' (got '{out_data.get('status')}')")
        return errors

    flows = out_data.get("flows", [])
    if not isinstance(flows, list):
        errors.append("'flows' key is not a list")
        return errors

    sources = in_data.get("sources", {})
    sink_name = in_data.get("sink", {}).get("name")
    node_caps = {name: data.get("capacity", float('inf')) 
                 for name, data in in_data.get("nodes", {}).items()}
    edge_bounds = {}
    for edge in in_data.get("edges", []):
        edge_bounds[(edge["from"], edge["to"])] = (edge.get("lo", 0.0), edge.get("hi", float('inf')))

    outflow = defaultdict(float)
    inflow = defaultdict(float)
    all_nodes = set(sources.keys()) | set(node_caps.keys()) | {sink_name}
    
    total_supply = sum(s.get("supply", 0) for s in sources.values())
    
    # 1. Check edge flows and aggregate in/out flows
    for flow in flows:
        f_from = flow.get("from")
        f_to = flow.get("to")
        f_val = flow.get("flow", 0.0)
        
        all_nodes.add(f_from)
        all_nodes.add(f_to)
        
        # Check bounds
        key = (f_from, f_to)
        if key not in edge_bounds:
            errors.append(f"Flow reported for non-existent edge: {f_from} -> {f_to}")
            continue
        
        lo, hi = edge_bounds[key]
        if f_val < lo - TOL:
            errors.append(f"Edge {f_from}->{f_to}: flow {f_val} < lower bound {lo}")
        if f_val > hi + TOL:
            errors.append(f"Edge {f_from}->{f_to}: flow {f_val} > upper bound {hi}")
            
        outflow[f_from] += f_val
        inflow[f_to] += f_val

    # 2. Check node conservation and caps
    for node in all_nodes:
        if node in sources:
            # Source node: outflow == supply
            supply = sources[node].get("supply", 0.0)
            if abs(outflow[node] - supply) > TOL:
                errors.append(f"Source {node}: outflow {outflow[node]} != supply {supply}")
            if inflow[node] > TOL:
                errors.append(f"Source {node}: has inflow {inflow[node]} (should be 0)")
        
        elif node == sink_name:
            # Sink node: inflow == total_supply
            if abs(inflow[node] - total_supply) > TOL:
                errors.append(f"Sink {node}: inflow {inflow[node]} != total supply {total_supply}")
            if outflow[node] > TOL:
                errors.append(f"Sink {node}: has outflow {outflow[node]} (should be 0)")
        
        else: # Intermediate node
            # Conservation: inflow == outflow
            if abs(inflow[node] - outflow[node]) > TOL:
                errors.append(f"Node {node}: inflow {inflow[node]} != outflow {outflow[node]}")
            
            # Capacity
            cap = node_caps.get(node, float('inf'))
            if inflow[node] > cap + TOL:
                errors.append(f"Node {node}: inflow {inflow[node]} > capacity {cap}")
                
    # 3. Check total flow
    reported_flow = out_data.get("max_flow_per_min", 0.0)
    if abs(reported_flow - total_supply) > TOL:
         errors.append(f"Reported max_flow {reported_flow} != total supply {total_supply}")

    return errors

def main():
    parser = argparse.ArgumentParser(description="Verify a belts solution.")
    parser.add_argument("input_json", help="Path to the input JSON file.")
    parser.add_argument("output_json", help="Path to the output JSON file.")
    args = parser.parse_args()

    try:
        with open(args.input_json, 'r') as f:
            in_data = json.load(f)
    except Exception as e:
        print(f"Error loading input file {args.input_json}: {e}")
        sys.exit(1)
        
    try:
        with open(args.output_json, 'r') as f:
            out_data = json.load(f)
    except Exception as e:
        print(f"Error loading output file {args.output_json}: {e}")
        sys.exit(1)
        
    print("Verifying solution...")
    errors = verify_solution(in_data, out_data)
    
    if errors:
        print("\n[\u274C VERIFICATION FAILED]")
        for err in errors:
            print(f"- {err}")
    else:
        print("\n[\u2705 VERIFIED] Solution appears correct and self-consistent.")

if __name__ == "__main__":
    main()