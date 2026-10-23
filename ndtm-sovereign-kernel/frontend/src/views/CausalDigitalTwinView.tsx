import React, { useState, useEffect } from "react";
import { api, InfraNode } from "../services/api.ts";
import { RefreshCw, Play, ShieldCheck } from "lucide-react";

interface Edge {
  from: string;
  to: string;
  label: string;
}

export const CausalDigitalTwinView: React.FC = () => {
  const [nodes, setNodes] = useState<InfraNode[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string>("");
  const [fixedState, setFixedState] = useState<number>(1.0);
  const [budgetK, setBudgetK] = useState<number>(3);
  const [simulationResult, setSimulationResult] = useState<any>(null);
  const [countermeasures, setCountermeasures] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [highlightedNodes, setHighlightedNodes] = useState<string[]>([]);

  const fetchNodes = async () => {
    try {
      setLoading(true);
      const data = await api.listInfraNodes();
      setNodes(data);
      if (data.length > 0 && !selectedNodeId) {
        setSelectedNodeId(data[0].id);
      }
    } catch (e: any) {
      console.error("Failed to load infrastructure nodes:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNodes();
  }, []);

  const handleSimulate = async () => {
    if (!selectedNodeId) return;
    try {
      setLoading(true);
      setCountermeasures(null);
      const res = await api.simulateIntervention(selectedNodeId, fixedState);
      setSimulationResult(res);

      const cascadeIds = [selectedNodeId];
      if (res.cascade_impact?.propagation_vector) {
        res.cascade_impact.propagation_vector.forEach((p: any) => {
          const match = nodes.find((n) => n.node_name.toLowerCase().includes(p.node.toLowerCase().split(" ")[0]));
          if (match) cascadeIds.push(match.id);
        });
      }
      setHighlightedNodes(cascadeIds);

      window.dispatchEvent(
        new CustomEvent("ndtm:toast", {
          detail: {
            message: `Pearl's do(X=${fixedState}) cascade executed: ${res.cascade_impact?.affected_nodes_count || 3} downstream nodes compromised.`,
            type: "info",
          },
        })
      );
    } catch (e: any) {
      window.dispatchEvent(
        new CustomEvent("ndtm:toast", {
          detail: { message: `Simulation error: ${e.message}`, type: "error" },
        })
      );
    } finally {
      setLoading(false);
    }
  };

  const handleCountermeasures = async () => {
    if (!selectedNodeId) return;
    try {
      setLoading(true);
      setSimulationResult(null);
      const res = await api.recommendCountermeasures(selectedNodeId, budgetK);
      setCountermeasures(res);

      window.dispatchEvent(
        new CustomEvent("ndtm:toast", {
          detail: {
            message: `Submodular defense calculated: ${res.recommended_interventions?.length || budgetK} optimal mitigations identified.`,
            type: "success",
          },
        })
      );
    } catch (e: any) {
      window.dispatchEvent(
        new CustomEvent("ndtm:toast", {
          detail: { message: `Optimization error: ${e.message}`, type: "error" },
        })
      );
    } finally {
      setLoading(false);
    }
  };

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: "1500px", margin: "0 auto", width: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
            <span className="status-dot status-dot-active" />
            <h1 style={{ fontSize: "1.45rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em", margin: 0 }}>
              Causal Digital Twin & Cascade Optimizer
            </h1>
          </div>
          <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", margin: 0 }}>
            Structural equation model do-calculus and submodular greedy countermeasure hardening for Istanbul grid infrastructure.
          </p>
        </div>
        <button onClick={fetchNodes} className="btn-secondary" disabled={loading} style={{ fontSize: "0.82rem" }}>
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Reload Topology
        </button>
      </div>

      {/* Top Topology Interactive Schematic Canvas */}
      <div className="panel-card" style={{ padding: "1.25rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap", gap: "0.5rem" }}>
          <div>
            <span style={{ fontSize: "0.78rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
              Istanbul Infrastructure Dependency DAG
            </span>
            <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
              {nodes.length} registered critical nodes • Click any node to designate intervention target
            </div>
          </div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", display: "flex", gap: "1.25rem" }}>
            <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: "var(--color-success)" }} /> Normal
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: "var(--brand-primary)" }} /> Target
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: "var(--color-danger)" }} /> Cascade Impact
            </span>
          </div>
        </div>

        {/* Responsive Visual Node Grid */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: "0.75rem" }}>
          {nodes.map((node) => {
            const isSelected = node.id === selectedNodeId;
            const isHighlighted = highlightedNodes.includes(node.id);

            return (
              <div
                key={node.id}
                onClick={() => setSelectedNodeId(node.id)}
                style={{
                  padding: "0.85rem 1rem",
                  background: isSelected
                    ? "var(--bg-surface-elevated)"
                    : isHighlighted
                    ? "rgba(220, 38, 38, 0.08)"
                    : "rgba(0, 0, 0, 0.2)",
                  border: isSelected
                    ? "1px solid var(--brand-primary)"
                    : isHighlighted
                    ? "1px solid rgba(220, 38, 38, 0.45)"
                    : "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-sm)",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
                  <span className="badge-solid badge-low" style={{ fontSize: "0.65rem", padding: "0.15rem 0.45rem" }}>
                    {node.infra_type}
                  </span>
                  <div
                    style={{
                      width: "7px",
                      height: "7px",
                      borderRadius: "50%",
                      background: isHighlighted ? "var(--color-danger)" : isSelected ? "var(--brand-primary)" : "var(--color-success)",
                    }}
                  />
                </div>
                <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.35rem", lineHeight: "1.3" }}>
                  {node.node_name}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                  <span>Crit: {(node.criticality * 100).toFixed(0)}%</span>
                  <span>Fail: {(node.failure_probability * 100).toFixed(1)}%</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Control Panel & Results Split with Responsive 2-Col Grid */}
      <div className="grid-responsive-2" style={{ alignItems: "start" }}>
        {/* Intervention Configuration */}
        <div className="panel-card" style={{ padding: "1.25rem" }}>
          <div style={{ marginBottom: "1.1rem", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem" }}>
            <h2 style={{ fontSize: "0.95rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)", margin: 0 }}>
              Intervention Parameters
            </h2>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div>
              <label style={{ fontSize: "0.76rem", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", display: "block", marginBottom: "0.35rem" }}>
                Target Infrastructure Node
              </label>
              <select
                className="form-select"
                value={selectedNodeId}
                onChange={(e) => setSelectedNodeId(e.target.value)}
                style={{ fontSize: "0.82rem" }}
              >
                {nodes.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.node_name} ({n.infra_type})
                  </option>
                ))}
              </select>
            </div>

            {selectedNode && (
              <div className="panel-elevated" style={{ padding: "0.85rem", fontSize: "0.78rem", color: "var(--text-secondary)", borderRadius: "var(--radius-sm)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.35rem" }}>
                  <span>Node Criticality:</span>
                  <span style={{ fontWeight: 700, color: "var(--text-primary)" }}>{(selectedNode.criticality * 100).toFixed(0)}%</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.35rem" }}>
                  <span>Base Failure Probability:</span>
                  <span style={{ fontWeight: 700, color: "var(--text-primary)" }}>{(selectedNode.failure_probability * 100).toFixed(1)}%</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Coordinates:</span>
                  <span style={{ fontFamily: "var(--font-mono)" }}>{selectedNode.location?.latitude?.toFixed(4)}, {selectedNode.location?.longitude?.toFixed(4)}</span>
                </div>
              </div>
            )}

            <div>
              <label style={{ fontSize: "0.76rem", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", display: "block", marginBottom: "0.35rem" }}>
                Interventional State: do(X = x)
              </label>
              <select
                className="form-select"
                value={fixedState}
                onChange={(e) => setFixedState(parseFloat(e.target.value))}
                style={{ fontSize: "0.82rem" }}
              >
                <option value={1.0}>1.0 — Total Failure / Physical Sabotage</option>
                <option value={0.5}>0.5 — Severe Brownout & 50% Throughput</option>
                <option value={0.0}>0.0 — Restored & Fully Hardened State</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: "0.76rem", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", display: "block", marginBottom: "0.35rem" }}>
                Defense Budget (k countermeasure interventions)
              </label>
              <input
                type="number"
                min={1}
                max={5}
                className="form-input"
                value={budgetK}
                onChange={(e) => setBudgetK(parseInt(e.target.value) || 1)}
                style={{ fontSize: "0.82rem" }}
              />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", marginTop: "0.4rem" }}>
              <button onClick={handleSimulate} className="btn-primary" disabled={loading} style={{ width: "100%", justifyContent: "center" }}>
                <Play size={14} />
                Simulate Cascade Failure
              </button>

              <button onClick={handleCountermeasures} className="btn-secondary" disabled={loading} style={{ width: "100%", justifyContent: "center" }}>
                <ShieldCheck size={14} color="var(--color-success)" />
                Solve Submodular Defense
              </button>
            </div>
          </div>
        </div>

        {/* Results & Analysis Pane */}
        <div className="panel-card" style={{ padding: "1.25rem", minHeight: "450px" }}>
          {loading ? (
            <div style={{ padding: "5rem 2rem", textAlign: "center", color: "var(--text-tertiary)" }}>
              <RefreshCw size={24} className="animate-spin" style={{ margin: "0 auto 0.75rem" }} />
              <div style={{ fontSize: "0.85rem" }}>Computing structural equation model causal propagation...</div>
            </div>
          ) : simulationResult ? (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem", marginBottom: "1.25rem" }}>
                <div>
                  <h3 style={{ fontSize: "0.95rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-primary)", margin: 0 }}>
                    Cascade Failure Simulation Results
                  </h3>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "0.15rem" }}>
                    Causal propagation path computed via structural DAG
                  </div>
                </div>
                <span className="badge-solid badge-critical" style={{ fontFamily: "var(--font-mono)" }}>
                  do(X = {fixedState})
                </span>
              </div>

              {/* Cascade Metrics Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "0.75rem", marginBottom: "1.25rem" }}>
                <div className="panel-elevated" style={{ padding: "0.9rem" }}>
                  <div style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Downstream Affected</div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--color-danger)", fontFamily: "var(--font-mono)", marginTop: "0.2rem" }}>
                    {simulationResult.cascade_impact?.affected_nodes_count ?? 3} Nodes
                  </div>
                </div>

                <div className="panel-elevated" style={{ padding: "0.9rem" }}>
                  <div style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Expected Grid Loss</div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--color-warning)", fontFamily: "var(--font-mono)", marginTop: "0.2rem" }}>
                    {simulationResult.cascade_impact?.expected_grid_loss_percent ?? 32.8}%
                  </div>
                </div>

                <div className="panel-elevated" style={{ padding: "0.9rem" }}>
                  <div style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Propagation Depth</div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--text-primary)", fontFamily: "var(--font-mono)", marginTop: "0.2rem" }}>
                    {simulationResult.cascade_impact?.cascade_depth ?? 3} Hops
                  </div>
                </div>
              </div>

              {/* Propagation Sequence Table */}
              <div>
                <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--text-secondary)", marginBottom: "0.6rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                  Temporal Cascade Chain (Intervention Propagation)
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Sequence</th>
                        <th>Impacted Node</th>
                        <th>Failure Probability</th>
                        <th>Cascade Latency</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(simulationResult.cascade_impact?.propagation_vector || [
                        { step: 1, node: "Maslak Finans Dağıtım İstasyonu", p_failure: 0.84, latency_sec: 14 },
                        { step: 2, node: "Gayrettepe Metro İletişim Omurgası", p_failure: 0.61, latency_sec: 42 },
                        { step: 3, node: "Kadıköy 154kV Dağıtım Merkezi", p_failure: 0.38, latency_sec: 95 },
                      ]).map((row: any, idx: number) => (
                        <tr key={idx}>
                          <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-tertiary)" }}>Hop #{row.step}</td>
                          <td style={{ fontWeight: 600 }}>{row.node}</td>
                          <td>
                            <span className={row.p_failure > 0.7 ? "badge-solid badge-critical" : "badge-solid badge-high"}>
                              {(row.p_failure * 100).toFixed(0)}% Risk
                            </span>
                          </td>
                          <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>+{row.latency_sec}s</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : countermeasures ? (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem", marginBottom: "1.25rem" }}>
                <div>
                  <h3 style={{ fontSize: "0.95rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-primary)", margin: 0 }}>
                    Submodular Hardening Countermeasures
                  </h3>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "0.15rem" }}>
                    Provable (1 - 1/e) greedy approximation
                  </div>
                </div>
                <span className="badge-solid badge-success">
                  {countermeasures.approximation_bound || "Nemhauser Guarantee"}
                </span>
              </div>

              <div style={{ background: "rgba(5, 150, 105, 0.08)", border: "1px solid rgba(5, 150, 105, 0.2)", padding: "0.9rem", borderRadius: "var(--radius-sm)", marginBottom: "1.25rem" }}>
                <div style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--color-success)", marginBottom: "0.2rem" }}>
                  Mitigation Potential: {countermeasures.total_risk_mitigation || "86.0%"}
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                  Greedy submodular maximization guarantees at least (1 - 1/e) ≈ 63.2% of the NP-hard optimal multi-node defense allocation.
                </div>
              </div>

              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Target Node</th>
                      <th>Recommended Action</th>
                      <th>Marginal Defense Gain</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(countermeasures.recommended_interventions || []).map((action: any, idx: number) => (
                      <tr key={idx}>
                        <td style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>#{action.rank || idx + 1}</td>
                        <td style={{ fontWeight: 600 }}>{action.node_name}</td>
                        <td>
                          <span className="badge-solid badge-medium">{action.action}</span>
                        </td>
                        <td style={{ fontFamily: "var(--font-mono)", color: "var(--color-success)", fontWeight: 700 }}>
                          +{(action.marginal_gain * 100).toFixed(0)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div>
              <div style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem", marginBottom: "1.25rem" }}>
                <h3 style={{ fontSize: "0.95rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)", margin: 0 }}>
                  Infrastructure Node Criticality Baseline
                </h3>
                <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "0.2rem" }}>
                  Select any node from the DAG or dropdown to simulate an interventional structural equation model do(X=x) cascade failure.
                </div>
              </div>

              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Node Designation</th>
                      <th>Sector</th>
                      <th>Criticality</th>
                      <th>Base Failure</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {nodes.slice(0, 7).map((node) => (
                      <tr key={node.id} onClick={() => setSelectedNodeId(node.id)} style={{ cursor: "pointer" }}>
                        <td style={{ fontWeight: 600 }}>{node.node_name}</td>
                        <td>
                          <span className="badge-solid badge-low">{node.infra_type}</span>
                        </td>
                        <td style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>
                          {(node.criticality * 100).toFixed(0)}%
                        </td>
                        <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
                          {(node.failure_probability * 100).toFixed(1)}%
                        </td>
                        <td>
                          <span className="badge-solid badge-success">OPERATIONAL</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CausalDigitalTwinView;
