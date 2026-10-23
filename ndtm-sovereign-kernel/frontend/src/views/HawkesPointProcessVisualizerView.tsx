import React, { useState, useEffect } from "react";
import { api, Cluster } from "../services/api.ts";
import { RefreshCw } from "lucide-react";

export const HawkesPointProcessVisualizerView: React.FC = () => {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCluster, setSelectedCluster] = useState<Cluster | null>(null);

  const fetchClusters = async () => {
    try {
      setLoading(true);
      const data = await api.listClusters();
      setClusters(data);
      if (data.length > 0 && !selectedCluster) {
        setSelectedCluster(data[0]);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClusters();
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: "1600px", margin: "0 auto", width: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
            <span className="status-dot status-dot-active" />
            <h1 style={{ fontSize: "1.45rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em", margin: 0 }}>
              Hawkes Point Process & Aftershock Forecaster
            </h1>
          </div>
          <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", margin: 0 }}>
            Self-exciting cluster detection with mathematical conditional intensity λ(t, x, y) tracking.
          </p>
        </div>
        <button onClick={fetchClusters} className="btn-secondary" disabled={loading} style={{ fontSize: "0.82rem" }}>
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Sync Clusters
        </button>
      </div>

      {/* Responsive 2-Col Split */}
      <div className="grid-responsive-2" style={{ alignItems: "start" }}>
        {/* Cluster List */}
        <div className="panel-card" style={{ padding: "1.25rem" }}>
          <div style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem", marginBottom: "1rem" }}>
            <h3 style={{ fontSize: "0.85rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)", margin: 0 }}>
              Active Spatio-Temporal Clusters ({clusters.length})
            </h3>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem", maxHeight: "550px", overflowY: "auto" }}>
            {clusters.length === 0 ? (
              <div style={{ color: "var(--text-tertiary)", padding: "2.5rem 1rem", textAlign: "center", fontSize: "0.85rem" }}>
                No active excitation clusters detected in memory.
              </div>
            ) : (
              clusters.map((c) => {
                const isSelected = selectedCluster?.id === c.id;
                const br = c.hawkes_parameters.branching_ratio;
                const isStable = br < 1.0;

                return (
                  <div
                    key={c.id}
                    onClick={() => setSelectedCluster(c)}
                    className="panel-elevated"
                    style={{
                      padding: "0.85rem 1rem",
                      borderRadius: "var(--radius-sm)",
                      cursor: "pointer",
                      border: isSelected ? "1px solid var(--brand-primary)" : "1px solid var(--border-subtle)",
                      background: isSelected ? "var(--bg-surface-elevated)" : undefined,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
                      <span className={`badge-solid badge-${c.cluster_urgency.toLowerCase()}`} style={{ fontSize: "0.65rem" }}>
                        {c.cluster_urgency}
                      </span>
                      <span style={{ fontSize: "0.72rem", color: isStable ? "var(--color-success)" : "var(--color-danger)", fontWeight: 600, fontFamily: "var(--font-mono)" }}>
                        η = {br.toFixed(2)} ({isStable ? "Subcritical" : "Supercritical"})
                      </span>
                    </div>

                    <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.2rem" }}>
                      Cluster #{c.id.slice(0, 8)} • {c.incident_count} Incidents Linked
                    </div>

                    <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                      Centroid: {c.centroid.latitude.toFixed(4)}°N, {c.centroid.longitude.toFixed(4)}°E • Radius: {c.radius_meters.toFixed(0)}m
                    </div>

                    <div style={{ marginTop: "0.4rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>Aftershock Risk (1h):</span>
                      <span style={{ fontSize: "0.82rem", fontWeight: 700, fontFamily: "var(--font-mono)", color: c.aftershock_probability > 0.5 ? "var(--color-danger)" : "var(--color-warning)" }}>
                        {(c.aftershock_probability * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Selected Cluster Deep Inspection */}
        <div className="panel-card" style={{ padding: "1.25rem" }}>
          <div style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem", marginBottom: "1rem" }}>
            <h3 style={{ fontSize: "0.85rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)", margin: 0 }}>
              Hawkes Point Process Analytics
            </h3>
          </div>

          {selectedCluster ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <div className="panel-elevated" style={{ padding: "0.75rem 0.85rem", borderRadius: "var(--radius-sm)" }}>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", textTransform: "uppercase" }}>Background Rate (μ)</div>
                  <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--brand-primary)", fontFamily: "var(--font-mono)", marginTop: "0.15rem" }}>
                    {selectedCluster.hawkes_parameters.mu.toFixed(4)} ev/s
                  </div>
                </div>

                <div className="panel-elevated" style={{ padding: "0.75rem 0.85rem", borderRadius: "var(--radius-sm)" }}>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", textTransform: "uppercase" }}>Decay Half-Life (β)</div>
                  <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--color-success)", fontFamily: "var(--font-mono)", marginTop: "0.15rem" }}>
                    {(1 / selectedCluster.hawkes_parameters.beta).toFixed(0)} seconds
                  </div>
                </div>
              </div>

              <div className="panel-elevated" style={{ padding: "0.9rem", borderRadius: "var(--radius-sm)" }}>
                <div style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)", marginBottom: "0.4rem" }}>
                  Mathematical Kernel Formulation
                </div>
                <code style={{ fontSize: "0.75rem", color: "var(--brand-primary)", display: "block", marginBottom: "0.4rem", fontFamily: "var(--font-mono)", wordBreak: "break-all" }}>
                  λ(t, x, y) = μ + Σ α·exp(-β(t - tᵢ)) · (1 / 2πσ²)·exp(-||x - xᵢ||² / 2σ²)
                </code>
                <p style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", lineHeight: "1.4", margin: 0 }}>
                  Branching ratio η = α / β dictates whether the cluster stabilizes naturally or initiates explosive cascading aftershocks.
                </p>
              </div>

              <div style={{ padding: "0.85rem 1rem", background: "rgba(220, 38, 38, 0.08)", border: "1px solid rgba(220, 38, 38, 0.25)", borderRadius: "var(--radius-sm)" }}>
                <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--color-danger)", marginBottom: "0.2rem" }}>
                  Automated Aftershock Triage Advisory
                </div>
                <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", margin: 0, lineHeight: "1.4" }}>
                  Recommended field team pre-positioning within {selectedCluster.radius_meters.toFixed(0)}m perimeter of ({selectedCluster.centroid.latitude.toFixed(4)}, {selectedCluster.centroid.longitude.toFixed(4)}).
                </p>
              </div>
            </div>
          ) : (
            <div style={{ color: "var(--text-tertiary)", padding: "3rem 1rem", textAlign: "center", fontSize: "0.85rem" }}>
              Select a cluster from the left panel to examine mathematical kernels.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default HawkesPointProcessVisualizerView;
