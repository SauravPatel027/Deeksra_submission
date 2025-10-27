import json
import sys
from fractions import Fraction
from pulp import (
    LpProblem,
    LpMinimize,
    LpMaximize,
    LpVariable,
    lpSum,
    LpStatus,
    PULP_CBC_CMD
)

TOLERANCE = 1e-9


def solve_factory_steady_state(
    recipes, machines, modules, raw_caps, machine_caps, target_item, target_rate
):
    try:
        constants = _preprocess_constants(
            recipes, machines, modules, raw_caps, machine_caps, target_item
        )
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    solver_options = ["-primalTolerance", "1e-10", "-dualTolerance", "1e-10"]
    solver = PULP_CBC_CMD(msg=False, options=solver_options)

    opt_prob, opt_vars, _, _ = _build_model(constants, target_rate, mode="optimize")

    opt_prob.solve(solver)

    if LpStatus[opt_prob.status] == "Optimal":
        return _format_success_output(constants, opt_vars)
    else:
        return _solve_and_format_max_rate(constants, solver)


def _preprocess_constants(
    recipes, machines, modules, raw_caps, machine_caps, target_item
):
    constants = {
        "eff_outputs": {},
        "frac_inputs": {},
        "machine_costs": {},
        "recipe_machines": {},
        "all_items": set(),
        "recipe_names": sorted(list(recipes.keys())),
        "machine_types": sorted(list(machine_caps.keys())),
        "raw_items": set(raw_caps.keys()),
        "target_item": target_item,
        "machine_caps": machine_caps,
        "raw_caps": raw_caps,
        "recipes": recipes,
    }

    all_produced_items = set()

    one = Fraction(1)
    sixty = Fraction(60)

    for r_name, r_data in recipes.items():
        m_name = r_data["machine"]
        if m_name not in machines:
            raise ValueError(f"Recipe '{r_name}' uses unknown machine '{m_name}'")

        machine = machines[m_name]
        module = modules.get(m_name, {})

        speed_mod = Fraction(str(module.get("speed", 0)))
        prod_mod = Fraction(str(module.get("prod", 0)))
        base_speed = Fraction(str(machine["crafts_per_min"]))
        time_s = Fraction(str(r_data["time_s"]))

        if time_s <= 0:
            raise ValueError(f"Recipe '{r_name}' has invalid time_s <= 0")

        eff_crafts_per_min = (base_speed * (one + speed_mod) * sixty) / time_s

        if eff_crafts_per_min <= 0:
            constants["machine_costs"][r_name] = Fraction(1, 10**-30)
        else:
            constants["machine_costs"][r_name] = one / eff_crafts_per_min

        constants["recipe_machines"][r_name] = m_name

        constants["eff_outputs"][r_name] = {}
        for item, amount in r_data.get("out", {}).items():
            frac_amount = Fraction(str(amount))
            constants["eff_outputs"][r_name][item] = frac_amount * (one + prod_mod)
            constants["all_items"].add(item)
            all_produced_items.add(item)

        constants["frac_inputs"][r_name] = {}
        for item, amount in r_data.get("in", {}).items():
            constants["frac_inputs"][r_name][item] = Fraction(str(amount))
            constants["all_items"].add(item)

    constants["intermediate_items"] = (
        all_produced_items - constants["raw_items"] - {target_item}
    )

    if target_item in all_produced_items:
        constants["intermediate_items"].add(target_item)

    constants["all_items"] = sorted(list(constants["all_items"]))
    return constants


def _build_model(constants, target_rate, mode="optimize"):
    if mode == "optimize":
        prob = LpProblem("Factory_Optimization", LpMinimize)
    else:
        prob = LpProblem("Factory_Max_Rate", LpMaximize)

    recipe_vars = LpVariable.dicts(
        "recipe", constants["recipe_names"], lowBound=0, cat="Continuous"
    )
    target_rate_var = LpVariable("max_target_rate", lowBound=0, cat="Continuous")

    if mode == "optimize":
        prob += (
            lpSum(
                float(constants["machine_costs"][r]) * recipe_vars[r]
                for r in constants["recipe_names"]
            ),
            "Total_Machine_Usage",
        )
    else:
        prob += target_rate_var, "Maximize_Target_Rate"

    constraints = {"machine": {}, "raw": {}}

    for item in constants["all_items"]:
        balance_expr = lpSum(
            (
                float(constants["eff_outputs"][r].get(item, 0))
                - float(constants["frac_inputs"][r].get(item, 0))
            )
            * recipe_vars[r]
            for r in constants["recipe_names"]
        )

        if item == constants["target_item"]:
            if mode == "optimize":
                frac_rate = float(Fraction(str(target_rate)))
                prob += (balance_expr == frac_rate, f"C_Target_{item}")
            else:
                prob += (balance_expr == target_rate_var, f"C_Target_{item}")

        elif item in constants["intermediate_items"]:
            prob += (balance_expr == 0, f"C_Intermediate_{item}")

        elif item in constants["raw_items"]:
            prob += (balance_expr <= 0, f"C_Raw_Net_{item}")
            if item in constants["raw_caps"]:
                cap = float(Fraction(str(constants["raw_caps"][item])))
                c_raw_cap = balance_expr >= -cap
                prob += c_raw_cap, f"C_Raw_Cap_{item}"
                constraints["raw"][item] = c_raw_cap

    for m_type in constants["machine_types"]:
        if m_type in constants["machine_caps"]:
            cap = float(Fraction(str(constants["machine_caps"][m_type])))
            usage_expr = lpSum(
                float(constants["machine_costs"][r]) * recipe_vars[r]
                for r in constants["recipe_names"]
                if constants["recipe_machines"][r] == m_type
            )
            c_machine_cap = usage_expr <= cap
            prob += c_machine_cap, f"C_Machine_Cap_{m_type}"
            constraints["machine"][m_type] = c_machine_cap

    return prob, recipe_vars, target_rate_var, constraints


def _format_success_output(constants, recipe_vars):
    per_recipe_crafts_per_min = {}
    for r_name, var in recipe_vars.items():
        val = var.varValue
        per_recipe_crafts_per_min[r_name] = val if val > TOLERANCE else 0.0


    per_machine_counts = {}
    for m_type in constants["machine_types"]:
        usage = sum(
            float(constants["machine_costs"][r]) * per_recipe_crafts_per_min[r]
            for r in constants["recipe_names"]
            if constants["recipe_machines"][r] == m_type
        )
        if usage > TOLERANCE:
            per_machine_counts[m_type] = usage

    raw_consumption_per_min = {}
    for item in constants["raw_items"]:
        consumption = -sum(
            (
                float(constants["eff_outputs"][r].get(item, 0))
                - float(constants["frac_inputs"][r].get(item, 0))
            )
            * per_recipe_crafts_per_min[r]
            for r in constants["recipe_names"]
        )
        if consumption > TOLERANCE:
            raw_consumption_per_min[item] = consumption

    return {
        "status": "ok",
        "per_recipe_crafts_per_min": per_recipe_crafts_per_min,
        "per_machine_counts": per_machine_counts,
        "raw_consumption_per_min": raw_consumption_per_min,
    }


def _solve_and_format_max_rate(constants, solver):
    (
        max_rate_prob,
        recipe_vars,
        target_rate_var,
        constraints,
    ) = _build_model(constants, target_rate=None, mode="maximize_rate")

    max_rate_prob.solve(solver)

    if LpStatus[max_rate_prob.status] != "Optimal":
        return {
            "status": "infeasible",
            "max_feasible_target_per_min": 0.0,
            "bottleneck_hint": [
                "Problem is fundamentally infeasible, even at zero target rate."
            ],
        }

    max_rate = target_rate_var.varValue
    bottleneck_hint = []

    for m_type, constraint in constraints["machine"].items():
        if constraint.slack is not None and abs(constraint.slack) < TOLERANCE:
            bottleneck_hint.append(f"{m_type} cap")

    for item in constraints["raw"].keys():
        cap = float(Fraction(str(constants["raw_caps"][item])))
        balance = sum(
            (
                float(constants["eff_outputs"][r].get(item, 0))
                - float(constants["frac_inputs"][r].get(item, 0))
            )
            * recipe_vars[r].varValue
            for r in constants["recipe_names"]
        )
        if balance <= -cap + TOLERANCE:
            bottleneck_hint.append(f"{item} supply")

    return {
        "status": "infeasible",
        "max_feasible_target_per_min": max(0, max_rate),
        "bottleneck_hint": sorted(list(set(bottleneck_hint))) or ["Unknown bottleneck"],
    }


if __name__ == "__main__":
    try:
        input_data = json.load(sys.stdin)

        machines = input_data.get("machines", {})
        recipes = input_data.get("recipes", {})
        modules = input_data.get("modules", {})
        limits = input_data.get("limits", {})
        target = input_data.get("target", {})

        raw_caps = limits.get("raw_supply_per_min", {})
        machine_caps = limits.get("max_machines", {})

        target_item = target.get("item")
        target_rate = target.get("rate_per_min")

        if not target_item or target_rate is None:
            raise ValueError("Missing 'target' item or 'rate_per_min'")

        solution = solve_factory_steady_state(
            recipes,
            machines,
            modules,
            raw_caps,
            machine_caps,
            target_item,
            target_rate,
        )

        json.dump(solution, sys.stdout)

    except json.JSONDecodeError:
        error_solution = {
            "status": "error",
            "message": "Invalid JSON input."
        }
        json.dump(error_solution, sys.stdout)

    except Exception as e:
        error_solution = {
            "status": "error",
            "message": str(e)
        }
        json.dump(error_solution, sys.stdout)
