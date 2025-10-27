import json
import sys
import networkx as nx

TOLERANCE = 1e-9

def solve_belt_problem(graph_data, node_data):
    """
    Solves the feasible flow problem with lower bounds and node capacities
    by transforming it into a standard max-flow problem.
    """
    
    G_transformed = nx.DiGraph()
    node_balance = {}
    S_STAR = "_s_star_"
    T_STAR = "_t_star_"

    original_nodes = set(node_data.keys())
    original_sources = set()
    sink_node = None
    
    for node_name, data in node_data.items():
        v_in = f"{node_name}_in"
        v_out = f"{node_name}_out"
        
        G_transformed.add_nodes_from([v_in, v_out])
        capacity = data.get("cap", float('inf'))
        G_transformed.add_edge(v_in, v_out, capacity=capacity)
        
        node_balance[v_in] = 0
        node_balance[v_out] = 0
        
        if data.get("supply", 0) > 0:
            original_sources.add(node_name)
            node_balance[v_out] += data["supply"]
        
        if data.get("demand", 0) > 0:
            sink_node = node_name
            node_balance[v_in] -= data["demand"]

    original_edges = []
    for edge in graph_data:
        u, v = edge["from"], edge["to"]
        lo, hi = edge.get("lo", 0), edge.get("hi", float('inf'))
        
        if hi < lo:
            raise ValueError(f"Edge ({u} -> {v}) has hi < lo ({hi} < {lo})")
        
        original_edges.append((u, v, lo, hi))

        adjusted_capacity = hi - lo
        u_out, v_in = f"{u}_out", f"{v}_in"
        G_transformed.add_edge(u_out, v_in, capacity=adjusted_capacity)
        
        node_balance[u_out] -= lo
        node_balance[v_in] += lo

    total_demand_required = 0
    
    for node, balance in node_balance.items():
        
        if balance > 0:
            G_transformed.add_edge(S_STAR, node, capacity=balance)
        elif balance < 0:
            demand = -balance
            G_transformed.add_edge(node, T_STAR, capacity=demand)
            total_demand_required += demand

    try:
        flow_value, flow_dict = nx.maximum_flow(G_transformed, S_STAR, T_STAR)
    except nx.NetworkXUnbounded:
        return {
            "status": "error",
            "message": "Unbounded flow detected. Check for edges with infinite capacity."
        }
    
    if abs(flow_value - total_demand_required) < TOLERANCE:
        return _format_success(
            flow_dict, original_edges, original_sources, node_data
        )
    else:
        return _format_infeasible(
            G_transformed, flow_dict, flow_value, total_demand_required,
            original_edges, node_data
        )

def _format_success(flow_dict, original_edges, original_sources, node_data):
    final_flows = []
    total_supply = 0

    for src in original_sources:
        total_supply += node_data[src].get("supply", 0)
    
    for u, v, lo, hi in original_edges:
        u_out, v_in = f"{u}_out", f"{v}_in"
        f_prime = flow_dict.get(u_out, {}).get(v_in, 0)
        final_flow = f_prime + lo
        
        if final_flow > TOLERANCE:
            final_flows.append({"from": u, "to": v, "flow": final_flow})

    return {
        "status": "ok",
        "max_flow_per_min": total_supply,
        "flows": final_flows
    }

def _build_residual_graph(G, flow_dict):
    R = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        cap = data.get("capacity", float('inf'))
        flow = flow_dict.get(u, {}).get(v, 0)
        
        if cap - flow > TOLERANCE:
            R.add_edge(u, v, capacity=(cap - flow))
        
        if flow > TOLERANCE:
            R.add_edge(v, u, capacity=flow)
    return R

def _format_infeasible(
    G, flow_dict, flow_value, total_demand, original_edges, node_data
):
    R = _build_residual_graph(G, flow_dict)
    S_STAR = "_s_star_"
    
    try:
        reachable_nodes_transformed = set(nx.dfs_preorder_nodes(R, S_STAR))
    except (nx.NetworkXError, KeyError):
        reachable_nodes_transformed = {S_STAR}

    cut_reachable = set()
    for n in reachable_nodes_transformed:
        if n.endswith("_in") or n.endswith("_out"):
            cut_reachable.add(n.split("_")[0])
        elif n != S_STAR and n != "_t_star_":
            cut_reachable.add(n)
            
    tight_nodes = []
    tight_edges = []
    
    for node, data in node_data.items():
        if "cap" in data:
            v_in, v_out = f"{node}_in", f"{node}_out"
            if (v_in in reachable_nodes_transformed and 
                v_out not in reachable_nodes_transformed):
                
                flow = flow_dict.get(v_in, {}).get(v_out, 0)
                if abs(flow - data["cap"]) < TOLERANCE:
                    tight_nodes.append(node)
                
    for u, v, lo, hi in original_edges:
        u_out, v_in = f"{u}_out", f"{v}_in"
        if (u_out in reachable_nodes_transformed and 
            v_in not in reachable_nodes_transformed):
            
            f_prime = flow_dict.get(u_out, {}).get(v_in, 0)
            adjusted_capacity = hi - lo
            if abs(f_prime - adjusted_capacity) < TOLERANCE:
                tight_edges.append({"from": u, "to": v})

    return {
        "status": "infeasible",
        "cut_reachable": sorted(list(cut_reachable)),
        "deficit": {
            "demand_balance": total_demand - flow_value,
            "tight_nodes": sorted(tight_nodes),
            "tight_edges": tight_edges
        }
    }

if __name__ == "__main__":
    try:
        input_data = json.load(sys.stdin)

        graph_data = input_data.get("edges", [])

        node_data = {}
        total_supply = 0

        sources = input_data.get("sources", {})
        for name, data in sources.items():
            supply = data.get("supply", 0)
            node_data[name] = {"supply": supply}
            total_supply += supply

        nodes = input_data.get("nodes", {})
        for name, data in nodes.items():
            if "capacity" in data:
                node_data[name] = {"cap": data["capacity"]}
            else:
                node_data[name] = {}

        sink_info = input_data.get("sink", {})
        sink_name = sink_info.get("name")
        
        if not sink_name:
            raise ValueError("Input JSON missing 'sink' object with 'name'")

        node_data[sink_name] = {"demand": total_supply}

        if not graph_data:
            raise ValueError("Missing 'edges' data.")
        if not sources or not sink_name:
            raise ValueError("Missing 'sources' or 'sink' data.")
            
        solution = solve_belt_problem(graph_data, node_data)
        
        json.dump(solution, sys.stdout, indent=2)

    except json.JSONDecodeError:
        error_solution = {
            "status": "error",
            "message": "Invalid JSON input."
        }
        json.dump(error_solution, sys.stdout, indent=2)
    
    except Exception as e:
        error_solution = {
            "status": "error",
            "message": str(e)
        }
        json.dump(error_solution, sys.stdout, indent=2)
