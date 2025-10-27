Factory Solver (factory/main.py)
 This solver finds the best way to use machines to reach a production goal while staying within the limits of the machines and raw materials.

 Model: Linear Programming (pulp)

 The issue is represented as a linear program:

 Variables: recipe_vars (the number of crafts that can be made in a minute for each recipe).

 Goal: Lp Cut down on the total cost of the machine.

 Limits: the balance of items, the amount of raw materials, and the capacity of the machines.

 Important Design Choices and Techniques:

 The Precision Challenge (and why it failed):

 The tolerance needed was 1e-9.

 My Try:  I added two main features to make this happen:

 parts. Fraction: To keep any floating-point errors from building up before they are sent to the solver, all constants (recipes, modules, etc.) are pre-processed using exact fractional math.

 Solver-Level Tolerance: I set the internal tolerance of the PULP_CBC_CMD solver to 1e-10 on purpose, hoping to make sure that the calculations were correct.

 The Discovered Limitation: I learned that this isn't enough.  Even with these changes, the pulp library still rounds its final outputs (like var.varValue). It looks like it rounds to about four decimal places.  This means that this tool can't really meet the 1e-9 tolerance goal.  The TOLERANCE = 1e-9 checks in the code are a hopeful try, but they don't work well with this rounding behavior.

 The "Two-Solve" Method for Handling Infeasibility Efficiently:

 I use a two-solve method instead of a slow binary search to find the max rate.

 If the first LpMinimize problem is "Infeasible," I work on a second LP problem that is different from the first one (_build_model(mode="maximize_rate")).

 The goal of this second problem is to LpMaximize a new variable called target_rate_var.  This finds the max_feasible_target_per_min in one go.

 Reporting on bottlenecks:

 The second "maximize" solve gives us the bottleneck_hint.

 I look at the values of constraint.slack.  A "tight" constraint is one that has a slack value close to zero (within the solver's practical tolerance). This is the limit on production.

 2. Belts Solver (belts/main.py)
 This solver finds a flow that works in a network with node capacities, edge lower and upper bounds, and more than one source and sink.

 Max-Flow (networkx) is a model.

 This is a "feasible flow with demands" problem, which I change into a regular max-flow problem.  This solution doesn't use pulp; instead, it uses networkx's graph algorithms.

 Important Techniques and Design Choices:

 Node Splitting (for Node Capacities):

 I divided each node v into two parts, v_in and v_out, and connected them with an edge that showed the node's capacity.

 All edges that come into v now go to v_in.  Now, all edges that go out of v come from v_out.

 Lower Bound Change:

 For an edge (u, v) with capacity [lo, hi]:

 The new edge (u_out, v_in) has a capacity of hi - lo.

 The nodes' balances are changed to "pre-flow" the lo amount: node_balance[u_out] -= lo and node_balance[v_in] += lo.

 Feasibility Check (The S_STAR / T_STAR Graph):

 I connect a super-source S_STAR to all the net-supply nodes and a super-sink T_STAR to all the net-demand nodes.

 The problem can be solved only if the max-flow from S_STAR to T_STAR is the same as the total demand.

 The Min-Cut: Exact Infeasibility Reporting

 If it can't be done, I find the reason by finding the min-cut.

 I make the residual graph from the partial flow networkx that I found.

 I do a depth-first search (dfs) from S_STAR to find all the nodes that can be reached.

 An edge or node on the "cut" (the line that goes from reachable to unreachable) that is at full capacity is called a "tight" edge or node.  These are the same bottlenecks that were reported in the output.
