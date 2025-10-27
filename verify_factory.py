#!/usr/bin/env python3
import json
import sys
import argparse
from collections import defaultdict

TOL = 1e-3

def get_eff_crafts(recipe, in_data):
    """
    Calculates effective crafts/min based on the PDF/your script's logic.
    """
    recipe_data = in_data["recipes"][recipe]
    machine_name = recipe_data["machine"]
    machine = in_data["machines"][machine_name]
    
    base_speed = machine["crafts_per_min"]
    time_s = recipe_data["time_s"]
    
    speed_mod = 0.0
    if "modules" in in_data and machine_name in in_data["modules"]:
        speed_mod = in_data["modules"][machine_name].get("speed", 0.0)
        
    # --- THIS IS THE UPDATED FORMULA TO MATCH YOUR SCRIPT ---
    if time_s <= 0:
        return 0 # Avoid division by zero, will be caught later if used
    eff = (base_speed * (1 + speed_mod) * 60) / time_s
    
    return eff

def get_prod_mod(recipe, in_data):
    """Gets the productivity modifier for a recipe."""
    machine_name = in_data["recipes"][recipe]["machine"]
    if "modules" in in_data and machine_name in in_data["modules"]:
        return in_data["modules"][machine_name].get("prod", 0.0)
    return 0.0

def verify_solution(in_data, out_data):
    """
    Checks if the output solution is valid for the given input.
    Returns a list of error strings.
    """
    errors = []
    
    if out_data.get("status") != "ok":
        errors.append(f"Status is not 'ok' (got '{out_data.get('status')}')")
        return errors # Stop verification if not 'ok'
        
    x_r = out_data.get("per_recipe_crafts_per_min", {})
    machines_used = out_data.get("per_machine_counts", {})
    raw_cons = out_data.get("raw_consumption_per_min", {})
    
    # 1. Check Machine Usage
    calc_machines = defaultdict(float)
    for recipe, crafts in x_r.items():
        if recipe not in in_data["recipes"]:
            errors.append(f"Output contains unknown recipe: {recipe}")
            continue
            
        if crafts < -TOL:
             errors.append(f"Recipe {recipe} has negative crafts: {crafts}")
             continue
             
        eff_crafts = get_eff_crafts(recipe, in_data)
        if eff_crafts <= TOL:
            if crafts > TOL:
                errors.append(f"Recipe {recipe} has {crafts} crafts but 0 eff_speed")
            continue
        
        machine_name = in_data["recipes"][recipe]["machine"]
        calc_machines[machine_name] += crafts / eff_crafts

    max_machines = in_data.get("limits", {}).get("max_machines", {})
    all_calc_machines = set(calc_machines.keys())
    all_reported_machines = set(machines_used.keys())
    
    # Check reported machines
    for m, reported_count in machines_used.items():
        if m not in calc_machines:
            if reported_count > TOL:
                errors.append(f"Output reports machine {m} usage {reported_count} but no recipes use it")
            continue
        
        calc_count = calc_machines[m]
        # Compare calculated vs reported
        if abs(reported_count - calc_count) > (TOL + abs(calc_count) * 1e-6): # Use relative tolerance
             errors.append(f"Machine {m}: reported {reported_count}, calculated {calc_count}")
        
        # Check cap
        if reported_count > max_machines.get(m, float('inf')) + TOL:
            errors.append(f"Machine {m}: usage {reported_count} > cap {max_machines.get(m)}")

    # Check for machines that were used but not reported (if usage > TOL)
    for m in all_calc_machines - all_reported_machines:
         if calc_machines[m] > TOL:
             errors.append(f"Machine {m}: calculated usage {calc_machines[m]} but not reported in per_machine_counts")

    # 2. Check Item Balances (Conservation)
    item_balance = defaultdict(float)
    all_items = set()
    raw_items = set(in_data.get("limits", {}).get("raw_supply_per_min", {}).keys())
    target_item = in_data.get("target", {}).get("item")

    for recipe, crafts in x_r.items():
        if recipe not in in_data["recipes"]:
            continue # Already reported this error
        recipe_data = in_data["recipes"][recipe]
        prod_mod = get_prod_mod(recipe, in_data)
        
        for item, amount in recipe_data.get("in", {}).items():
            item_balance[item] -= amount * crafts
            all_items.add(item)
            
        for item, amount in recipe_data.get("out", {}).items():
            item_balance[item] += amount * (1.0 + prod_mod) * crafts
            all_items.add(item)
    
    for item in all_items:
        balance = item_balance[item]
        
        if item == target_item:
            target_rate = in_data["target"]["rate_per_min"]
            if abs(balance - target_rate) > TOL:
                errors.append(f"Target {item}: balance {balance} != target {target_rate}")
        elif item in raw_items:
            # Net consumption, so balance should be negative or zero
            if balance > TOL:
                errors.append(f"Raw {item}: producing {balance} (should be consuming)")
            
            consumption = -balance
            cap = in_data["limits"]["raw_supply_per_min"].get(item, float('inf'))
            if consumption > cap + TOL:
                errors.append(f"Raw {item}: consumption {consumption} > cap {cap}")
            
            # Check reported consumption
            reported_cons = raw_cons.get(item, 0.0)
            if abs(consumption - reported_cons) > TOL:
                if consumption > TOL or reported_cons > TOL: # Only error if non-trivial
                    errors.append(f"Raw {item}: reported cons {reported_cons}, calculated {consumption}")
                
        else: # Intermediate item
            if abs(balance) > TOL:
                errors.append(f"Intermediate {item}: balance is {balance} (should be 0)")
    
    # Check for raw items reported but not calculated
    for item in raw_cons:
        if item not in all_items and raw_cons[item] > TOL:
             errors.append(f"Raw {item}: reported consumption {raw_cons[item]} but item is not used in any recipe")
             
    return errors

def main():
    parser = argparse.ArgumentParser(description="Verify a factory solution.")
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