import React, { useState, useEffect } from "react";
import { RefreshCw, CheckCircle2 } from "lucide-react";
import { api } from "../services/api.ts";

interface RegionNode {
  regionId: string;
  name: string;
  location: string;
  pingMs: number;
  vectorClock: Record<string, number>;
  activeIncidentsCount: number;
  dispatchedTeamsCount: number;
  wanStatus: "SYNCED" | "PARTITIONED";
  lastReplicatedAt: string;
}

interface BurnWindow {
  window: string;
  burn_rate: number;
  threshold: number;
  severity: string;
  consumed_budget_pct: number;
}

export const View12_MultiRegionCrdtAndSloBurnRate: React.FC = () => {
  // SRE Multi-Burn Rate State
  const [budgetRemaining, setBudgetRemaining] = useState<number>(99.85);
  const [sevStatus, setSevStatus] = useState<"HEALTHY" | "SEV1_CRITICAL">("HEALTHY");
  const [loading, setLoading] = useState<boolean>(false);
  const [burnSpikeActive, setBurnSpikeActive] = useState<boolean>(false);

  // CRDT WAN State
  const [isPartitioned, setIsPartitioned] = useState<boolean>(false);
  const [convergenceStatus, setConvergenceStatus] = useState<"CONVERGED" | "DIVERGING">("CONVERGED");

  // Regional nodes
  const [regions, setRegions] = useState<RegionNode[]>([
    {
      regionId: "us-west-1",
      name: "Silicon Valley Gateway",
      location: "San Jose, CA",
      pingMs: 142,
      vectorClock: { "us-west-1": 18, "eu-central-1": 14, "ap-southeast-1": 9 },
      activeIncidentsCount: 4,
      dispatchedTeamsCount: 6,
      wanStatus: "SYNCED",
      lastReplicatedAt: "1.2s ago",
    },
    {
      regionId: "eu-central-1",
      name: "Frankfurt Core Exchange",
      location: "Frankfurt am Main, DE",
      pingMs: 38,
      vectorClock: { "us-west-1": 18, "eu-central-1": 14, "ap-southeast-1": 9 },
      activeIncidentsCount: 4,
      dispatchedTeamsCount: 6,
      wanStatus: "SYNCED",
      lastReplicatedAt: "0.8s ago",
    },
    {
      regionId: "ap-southeast-1",
      name: "Singapore Maritime Relay",
      location: "Singapore, SG",
      pingMs: 194,
      vectorClock: { "us-west-1": 18, "eu-central-1": 14, "ap-southeast-1": 9 },
      activeIncidentsCount: 4,
      dispatchedTeamsCount: 6,
      wanStatus: "SYNCED",
      lastReplicatedAt: "1.5s ago",
    },
  ]);

  // Operational Event Ledger
  const [eventLedger, setEventLedger] = useState<Array<{ id: string; time: string; origin: string; event: string; status: string }>>([
    { id: "TX-901", time: "14:48:02", origin: "us-west-1", event: "LWW-Element-Set merge verified", status: "ACK_CONVERGED" },
    { id: "TX-902", time: "14:48:15", origin: "eu-central-1", event: "VectorClock increment ⟨EU:14⟩", status: "ACK_CONVERGED" },
    { id: "TX-903", time: "14:48:32", origin: "ap-southeast-1", event: "Delta-CRDT packet exchange acked", status: "ACK_CONVERGED" },
  ]);

  // Multi-Window Burn Rates
  const [burnRates, setBurnRates] = useState<BurnWindow[]>([
    { window: "1-Hour Window", burn_rate: 0.12, threshold: 14.4, severity: "HEALTHY", consumed_budget_pct: 0.02 },
    { window: "6-Hour Window", burn_rate: 0.18, threshold: 6.0, severity: "HEALTHY", consumed_budget_pct: 0.05 },
    { window: "24-Hour Window", burn_rate: 0.25, threshold: 3.0, severity: "HEALTHY", consumed_budget_pct: 0.10 },
    { window: "72-Hour Window", burn_rate: 0.31, threshold: 1.0, severity: "HEALTHY", consumed_budget_pct: 0.15 },
  ]);

  const showToast = (message: string, type: "success" | "error" | "info" = "info") => {
    window.dispatchEvent(new CustomEvent("ndtm:toast", { detail: { message, type } }));
  };

  const loadSreAndCrdt = async () => {
    try {
      setLoading(true);
      const slo = await api.getSloBudget();
      if (slo && slo.windows) {
        setBudgetRemaining(slo.remaining_budget_pct || 99.85);
        setBurnRates(slo.windows);
        setSevStatus(slo.highest_severity === "HEALTHY" ? "HEALTHY" : "SEV1_CRITICAL");
      }
    } catch (e: any) {
      console.warn("SRE load notice:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSreAndCrdt();
  }, []);

  const handleSimulatePartition = async () => {
    setIsPartitioned(true);
    setConvergenceStatus("DIVERGING");
    showToast("WAN Partition Active: Regions now buffering concurrent local updates into CRDT semilattices.", "info");

    try {
      await api.ingestCrdtEvent({
        region_id: "us-west-1",
        event_action: "OPEN_INCIDENT",
        entity_id: `inc_split_${Date.now().toString(36)}`,
      });
    } catch {}

    setRegions((prev) => [
      {
        ...prev[0],
        wanStatus: "PARTITIONED",
        vectorClock: { ...prev[0].vectorClock, "us-west-1": prev[0].vectorClock["us-west-1"] + 1 },
        activeIncidentsCount: prev[0].activeIncidentsCount + 1,
        lastReplicatedAt: "Buffering local",
      },
      {
        ...prev[1],
        wanStatus: "PARTITIONED",
        vectorClock: { ...prev[1].vectorClock, "eu-central-1": prev[1].vectorClock["eu-central-1"] + 1 },
        activeIncidentsCount: prev[1].activeIncidentsCount + 2,
        lastReplicatedAt: "Buffering local",
      },
      {
        ...prev[2],
        wanStatus: "PARTITIONED",
        lastReplicatedAt: "Link unreachable",
      },
    ]);

    setEventLedger((prev) => [
      {
        id: `TX-${Date.now().toString().slice(-3)}`,
        time: new Date().toLocaleTimeString(),
        origin: "WAN_ORCHESTRATOR",
        event: "BGP route partition detected. Delta buffer enabled.",
        status: "PARTITION_ACTIVE",
      },
      ...prev.slice(0, 5),
    ]);
  };

  const handleHealPartition = async () => {
    setLoading(true);
    let mergedClock = { "us-west-1": 19, "eu-central-1": 16, "ap-southeast-1": 9 };
    let mergedIncidents = 7;

    try {
      const res = await api.simulateWanPartition();
      if (res && res.us_west_state) {
        mergedClock = res.us_west_state.vector_clock || mergedClock;
        mergedIncidents = res.us_west_state.active_incidents_count ?? mergedIncidents;
      }
    } catch (err) {
      console.warn("WAN partition healing simulation fallback:", err);
    }

    setIsPartitioned(false);
    setConvergenceStatus("CONVERGED");
    setLoading(false);

    setRegions((prev) =>
      prev.map((r) => ({
        ...r,
        wanStatus: "SYNCED",
        vectorClock: mergedClock,
        activeIncidentsCount: mergedIncidents,
        lastReplicatedAt: "Just now",
      }))
    );

    setEventLedger((prev) => [
      {
        id: `TX-${Date.now().toString().slice(-3)}`,
        time: new Date().toLocaleTimeString(),
        origin: "MESH_CONSENSUS",
        event: "Join-semilattice merged across 3 regions without data loss.",
        status: "CONVERGED_OK",
      },
      ...prev.slice(0, 5),
    ]);

    showToast("WAN Partition Healed: State deterministically converged across all regions.", "success");
  };

  const handleSimulateSloSpike = () => {
    setBurnSpikeActive(true);
    setSevStatus("SEV1_CRITICAL");
    setBudgetRemaining(98.12);
    setBurnRates([
      { window: "1-Hour Window", burn_rate: 16.8, threshold: 14.4, severity: "CRITICAL_PAGING", consumed_budget_pct: 2.33 },
      { window: "6-Hour Window", burn_rate: 7.2, threshold: 6.0, severity: "CRITICAL_PAGING", consumed_budget_pct: 5.80 },
      { window: "24-Hour Window", burn_rate: 3.4, threshold: 3.0, severity: "HIGH_TICKET", consumed_budget_pct: 11.20 },
      { window: "72-Hour Window", burn_rate: 1.4, threshold: 1.0, severity: "NORMAL_AUDIT", consumed_budget_pct: 14.00 },
    ]);
    showToast("14.4x Burn Spike Triggered: PagerDuty on-call alert dispatched.", "error");
  };

  const handleResetSlo = () => {
    setBurnSpikeActive(false);
    setSevStatus("HEALTHY");
    setBudgetRemaining(99.85);
    setBurnRates([
      { window: "1-Hour Window", burn_rate: 0.12, threshold: 14.4, severity: "HEALTHY", consumed_budget_pct: 0.02 },
      { window: "6-Hour Window", burn_rate: 0.18, threshold: 6.0, severity: "HEALTHY", consumed_budget_pct: 0.05 },
      { window: "24-Hour Window", burn_rate: 0.25, threshold: 3.0, severity: "HEALTHY", consumed_budget_pct: 0.10 },
      { window: "72-Hour Window", burn_rate: 0.31, threshold: 1.0, severity: "HEALTHY", consumed_budget_pct: 0.15 },
    ]);
    showToast("SLO Burn Rates normalized to baseline.", "success");
  };

  // Circular gauge calculations
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (budgetRemaining / 100) * circumference;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", maxWidth: "1600px", margin: "0 auto" }}>
      {/* View Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 700, margin: 0, letterSpacing: "-0.015em" }}>
              Multi-Region CRDT & SRE Observability
            </h2>
            <span className={`badge ${convergenceStatus === "CONVERGED" ? "badge-low" : "badge-critical"}`}>
              {convergenceStatus}
            </span>
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", margin: "0.3rem 0 0 0" }}>
            Active-Active geo-distributed state replication with conflict-free semilattices and Google SRE multi-burn-rate controls.
          </p>
        </div>

        {/* Global Action Toolbar */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            onClick={loadSreAndCrdt}
            className="btn-secondary"
            title="Refresh telemetry"
            disabled={loading}
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            Sync Telemetry
          </button>

          {burnSpikeActive ? (
            <button onClick={handleResetSlo} className="btn-secondary">
              <CheckCircle2 size={13} color="#10b981" />
              Reset Normal
            </button>
          ) : (
            <button
              onClick={handleSimulateSloSpike}
              className="btn-danger"
            >
              Simulate 14.4x Burn Spike
            </button>
          )}

          {isPartitioned ? (
            <button
              onClick={handleHealPartition}
              className="btn-success"
              disabled={loading}
            >
              Heal & Converge Mesh
            </button>
          ) : (
            <button
              onClick={handleSimulatePartition}
              className="btn-secondary"
              style={{ borderColor: "rgba(239, 68, 68, 0.35)", color: "#f87171" }}
            >
              Simulate WAN Partition
            </button>
          )}
        </div>
      </div>

      {/* Operational Metrics Grid */}
      <div className="grid-responsive-kpi">
        <div className="card" style={{ padding: "0.9rem 1.1rem" }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            SLO Error Budget (30-Day)
          </div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.3rem 0 0.1rem 0", color: budgetRemaining > 99 ? "var(--color-success)" : "var(--color-danger)", fontFamily: "var(--font-mono)" }}>
            {budgetRemaining.toFixed(2)}%
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
            Permitted downtime: 43.8 min/mo
          </div>
        </div>

        <div className="card" style={{ padding: "0.9rem 1.1rem" }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Replication State
          </div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.3rem 0 0.1rem 0", color: isPartitioned ? "var(--color-warning)" : "var(--color-success)" }}>
            {isPartitioned ? "Split-Brain Buffer" : "Active-Active Synced"}
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
            Join-semilattice: zero-lock
          </div>
        </div>

        <div className="card" style={{ padding: "0.9rem 1.1rem" }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            SRE Severity State
          </div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.3rem 0 0.1rem 0", color: sevStatus === "HEALTHY" ? "var(--color-success)" : "var(--color-danger)" }}>
            {sevStatus}
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
            {sevStatus === "HEALTHY" ? "All burn rates within tolerance" : "Page on-call engineering lead"}
          </div>
        </div>

        <div className="card" style={{ padding: "0.9rem 1.1rem" }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Core Cross-Region RTT
          </div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.3rem 0 0.1rem 0", fontFamily: "var(--font-mono)" }}>
            38<span style={{ fontSize: "0.85rem", color: "var(--text-tertiary)", fontWeight: 500 }}>ms (EU-DE)</span>
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
            Optimistic local commits enabled
          </div>
        </div>
      </div>

      {/* Main Responsive Grid: Regional Gateways & SRE Controls */}
      <div className="grid-responsive-2">
        {/* Left Column: Regional Gateways & Replication Stream */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-tertiary)" }}>
              Regional Sovereign Nodes ({regions.length})
            </span>
            <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
              LWW Conflict Resolution
            </span>
          </div>

          {/* Regional Node Cards */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {regions.map((node) => (
              <div
                key={node.regionId}
                className="card"
                style={{
                  padding: "1rem 1.15rem",
                  borderLeft: `3px solid ${node.wanStatus === "SYNCED" ? "#10b981" : "#f59e0b"}`,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.65rem" }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.925rem" }}>{node.name}</div>
                    <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", marginTop: "0.15rem" }}>
                      {node.location} • <span style={{ fontFamily: "var(--font-mono)", color: "var(--brand-accent)" }}>{node.regionId}</span>
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                      RTT {node.pingMs}ms
                    </span>
                    <span className={`badge ${node.wanStatus === "SYNCED" ? "badge-low" : "badge-medium"}`}>
                      {node.wanStatus}
                    </span>
                  </div>
                </div>

                {/* Regional Metrics Bar */}
                <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr 1fr", gap: "0.65rem", fontSize: "0.78rem" }}>
                  <div style={{ background: "var(--bg-app)", padding: "0.55rem 0.7rem", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)" }}>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", marginBottom: "0.15rem" }}>VectorClock ⟨US, EU, AP⟩</div>
                    <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--text-primary)" }}>
                      ⟨{node.vectorClock["us-west-1"] || 0}, {node.vectorClock["eu-central-1"] || 0}, {node.vectorClock["ap-southeast-1"] || 0}⟩
                    </div>
                  </div>

                  <div style={{ background: "var(--bg-app)", padding: "0.55rem 0.7rem", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)" }}>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", marginBottom: "0.15rem" }}>Active Incidents</div>
                    <div style={{ fontWeight: 700, fontSize: "1rem", fontFamily: "var(--font-mono)" }}>{node.activeIncidentsCount}</div>
                  </div>

                  <div style={{ background: "var(--bg-app)", padding: "0.55rem 0.7rem", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)" }}>
                    <div style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", marginBottom: "0.15rem" }}>Dispatched Units</div>
                    <div style={{ fontWeight: 700, fontSize: "1rem", fontFamily: "var(--font-mono)" }}>{node.dispatchedTeamsCount}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* CRDT Event Ledger Table */}
          <div className="card" style={{ padding: "1rem 1.15rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.65rem" }}>
              <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>
                Live Delta-CRDT Replication Stream
              </span>
              <span style={{ fontSize: "0.7rem", color: "var(--text-tertiary)" }}>Last 3 transactions</span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
              {eventLedger.map((tx) => (
                <div
                  key={tx.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "0.45rem 0.65rem",
                    background: "var(--bg-app)",
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--border-subtle)",
                    fontSize: "0.75rem",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-tertiary)", fontSize: "0.68rem" }}>{tx.time}</span>
                    <span style={{ fontFamily: "var(--font-mono)", color: "var(--brand-accent)" }}>{tx.origin}</span>
                    <span style={{ color: "var(--text-secondary)" }}>{tx.event}</span>
                  </div>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.68rem", color: tx.status.includes("ACTIVE") ? "#f59e0b" : "#10b981" }}>
                    {tx.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: Google SRE Multi-Window Multi-Burn-Rate Control */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-tertiary)" }}>
              SRE Error Budget & Burn Rates
            </span>
            <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
              SLO: 99.9% Target
            </span>
          </div>

          {/* Circular Error Budget Card */}
          <div className="card" style={{ padding: "1.15rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
              {/* SVG Circular Ring Gauge */}
              <div style={{ position: "relative", width: "90px", height: "90px", flexShrink: 0 }}>
                <svg width="90" height="90" viewBox="0 0 100 100" style={{ transform: "rotate(-90deg)" }}>
                  <circle
                    cx="50"
                    cy="50"
                    r={radius}
                    fill="transparent"
                    stroke="rgba(255, 255, 255, 0.06)"
                    strokeWidth="8"
                  />
                  <circle
                    cx="50"
                    cy="50"
                    r={radius}
                    fill="transparent"
                    stroke={budgetRemaining > 99 ? "#10b981" : "#ef4444"}
                    strokeWidth="8"
                    strokeDasharray={circumference}
                    strokeDashoffset={strokeDashoffset}
                    strokeLinecap="round"
                    style={{ transition: "stroke-dashoffset 0.6s ease" }}
                  />
                </svg>
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <span style={{ fontSize: "1.05rem", fontWeight: 800, fontFamily: "var(--font-mono)" }}>{budgetRemaining.toFixed(1)}%</span>
                  <span style={{ fontSize: "0.55rem", color: "var(--text-tertiary)", fontWeight: 700 }}>REMAINING</span>
                </div>
              </div>

              {/* Budget Specifications */}
              <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem", fontSize: "0.8rem" }}>
                <div>
                  <span style={{ color: "var(--text-tertiary)" }}>Target Availability: </span>
                  <strong>99.9% (3 Nines)</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-tertiary)" }}>Rolling Window: </span>
                  <strong>30 Days Continuous</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-tertiary)" }}>Budget Depleted: </span>
                  <strong style={{ color: budgetRemaining > 99 ? "#10b981" : "#ef4444", fontFamily: "var(--font-mono)" }}>
                    {(100 - budgetRemaining).toFixed(2)}%
                  </strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-tertiary)" }}>Paging Escalation: </span>
                  <span style={{ color: sevStatus === "HEALTHY" ? "#10b981" : "#ef4444", fontWeight: 600 }}>
                    {sevStatus === "HEALTHY" ? "Standing by" : "Active SEV1 Ticket"}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Multi-Window Multi-Burn-Rate Threshold Table */}
          <div className="card" style={{ padding: "1.15rem" }}>
            <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.75rem" }}>
              Multi-Window Alert Rules (Google SRE Standard)
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
              {burnRates.map((b, idx) => {
                const isBreached = b.burn_rate >= b.threshold;
                const progressPct = Math.min(100, (b.burn_rate / b.threshold) * 100);

                return (
                  <div
                    key={idx}
                    style={{
                      padding: "0.75rem 0.85rem",
                      borderRadius: "var(--radius-sm)",
                      background: isBreached ? "rgba(239, 68, 68, 0.08)" : "var(--bg-app)",
                      border: `1px solid ${isBreached ? "rgba(239, 68, 68, 0.3)" : "var(--border-subtle)"}`,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
                      <div>
                        <span style={{ fontWeight: 600, fontSize: "0.825rem" }}>{b.window}</span>
                        <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", marginTop: "0.1rem" }}>
                          Threshold: {b.threshold}x • Consumed: {b.consumed_budget_pct.toFixed(2)}%
                        </div>
                      </div>

                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontWeight: 700, fontSize: "0.95rem", color: isBreached ? "#ef4444" : "#10b981", fontFamily: "var(--font-mono)" }}>
                          {b.burn_rate.toFixed(2)}x
                        </div>
                        <div style={{ fontSize: "0.65rem", color: isBreached ? "#ef4444" : "var(--text-tertiary)", fontWeight: 600 }}>
                          {isBreached ? "PAGE ON-CALL" : "NORMAL"}
                        </div>
                      </div>
                    </div>

                    {/* Visual Meter Bar */}
                    <div style={{ width: "100%", height: "4px", background: "rgba(255,255,255,0.06)", borderRadius: "2px", overflow: "hidden" }}>
                      <div
                        style={{
                          width: `${progressPct}%`,
                          height: "100%",
                          background: isBreached ? "#ef4444" : "#10b981",
                          borderRadius: "2px",
                          transition: "width 0.4s ease",
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
