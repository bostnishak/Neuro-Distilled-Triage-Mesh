# ADR-0001: Two-Tier Hungarian Algorithm and Isolated Z3 MaxSMT Dispatcher

## Status
Accepted

## Context
Emergency triage incidents (fires, gas leaks, structural collapses) require immediate matching with available specialized emergency responder field teams (Hazmat, Search & Rescue, Paramedics). 

Historically, solving this assignment using pure Microsoft Z3 SMT via subprocess spawning introduced ~225ms of latency overhead per call, exceeding the critical sub-20ms P99 operational requirement for carrier-grade dispatch loops. Furthermore, classical two-sided weighted bipartite matching without non-linear conflict constraints can be solved in polynomial $O(V^3)$ time to mathematical optimality.

## Decision
We adopt a strictly partitioned **Two-Tier Dispatch Architecture**:

1. **Tier A (Fast Baseline - Sub-5ms):** 
   - Uses the Hungarian Algorithm (Kuhn-Munkres algorithm / `scipy.optimize.linear_sum_assignment`) combined with 2-Opt Large Neighborhood Search (LNS) warm-starting.
   - Solves distance, burnout, and specialization matching with zero IPC overhead directly in the primary process memory space.
   - Guarantees an immediate, conflict-free, anytime-valid assignment schedule.

2. **Tier B (Subprocess-Isolated Z3 MaxSMT - Complex Constraints):**
   - Invoked only when complex non-linear SMT assertions (cross-incident causal dependency cascades, multi-team joint coordination, dynamic resource capacity constraints) are active.
   - Runs in a dedicated, isolated OS worker process with a hard deadline timer.
   - Uses non-blocking queue polling to avoid OS pipe deadlocks.
   - If the deadline expires, the system drops Tier B and returns Tier A instantly without dropping or blocking the request.

## Consequences
- **Positive:** P99 dispatch response latency drops below 15ms under high concurrent load; eliminates catastrophic deadlock on large payloads; provides mathematical proof of optimality for bipartite assignments.
- **Negative:** Requires maintaining two solver layers with unified cost score normalization.
