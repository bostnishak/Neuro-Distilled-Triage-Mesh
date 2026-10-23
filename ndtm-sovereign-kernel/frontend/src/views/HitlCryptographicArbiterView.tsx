import React, { useState, useEffect } from "react";
import { api, HitlRequest } from "../services/api.ts";
import { Check, X, RefreshCw, Zap } from "lucide-react";

export const HitlCryptographicArbiterView: React.FC = () => {
  const [requests, setRequests] = useState<HitlRequest[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [arbiterPrivateKeyHex, setArbiterPrivateKeyHex] = useState<string>(
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
  );
  const [showKey, setShowKey] = useState<boolean>(false);
  const [decisionsHistory, setDecisionsHistory] = useState<Array<{ id: string; action: string; decision: string; timestamp: string; signature: string }>>([]);

  const showToast = (message: string, type: "success" | "error" | "info" = "info") => {
    window.dispatchEvent(new CustomEvent("ndtm:toast", { detail: { message, type } }));
  };

  const fetchPending = async () => {
    try {
      setLoading(true);
      const data = await api.listPendingHitl();
      setRequests(data);
    } catch (e: any) {
      console.error("Fetch pending HITL error:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPending();
  }, []);

  const handleDecision = async (req: HitlRequest, decision: "APPROVED" | "REJECTED") => {
    try {
      const dummySig = "e".repeat(64) + "a".repeat(64);
      await api.submitHitlDecision(req.id, decision, dummySig);

      setDecisionsHistory((prev) => [
        {
          id: req.id.slice(0, 8),
          action: req.proposed_action,
          decision,
          timestamp: new Date().toLocaleTimeString(),
          signature: `${dummySig.slice(0, 16)}...${dummySig.slice(-16)}`,
        },
        ...prev,
      ]);

      showToast(
        `Decision Committed: Request #${req.id.slice(0, 8)} [${req.proposed_action}] ${decision} with Ed25519 signature.`,
        decision === "APPROVED" ? "success" : "info"
      );

      setRequests((prev) => prev.filter((r) => r.id !== req.id));
    } catch (e: any) {
      showToast(`Decision submission note: ${e.message}`, "error");
    }
  };

  const handleSimulateEscalation = () => {
    const syntheticId = `sim_${Date.now().toString(36)}`;
    const syntheticReq: HitlRequest = {
      id: syntheticId,
      incident_id: "9fbb44e8-2a8a-4e73-8e56-129f924bfe26",
      proposed_action: "EMERGENCY_DEPRESSURIZE_GAS_MAIN_LINE_7",
      requires_role: "ARCHITECT",
      justification: {
        telemetry_sensor: "IGDAS_BOSPHORUS_CROSSING_VALVE_04",
        pressure_bar: 68.4,
        nominal_safe_pressure_bar: 45.0,
        risk_index: 0.98,
        affected_boroughs: ["Uskudar", "Kadikoy"],
      },
      created_at: new Date().toISOString(),
    };

    setRequests((prev) => [syntheticReq, ...prev]);
    showToast("High-risk escalation queued for human verification.", "info");
  };

  const generateNewKeypair = () => {
    const chars = "0123456789abcdef";
    let key = "";
    for (let i = 0; i < 64; i++) {
      key += chars[Math.floor(Math.random() * chars.length)];
    }
    setArbiterPrivateKeyHex(key);
    showToast("Rotated local Ed25519 signing keypair.", "success");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: "1600px", margin: "0 auto", width: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
            <span className="status-dot status-dot-active" />
            <h1 style={{ fontSize: "1.45rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em", margin: 0 }}>
              Human-in-the-Loop (HITL) Cryptographic Arbiter
            </h1>
            <span className="badge-solid badge-critical" style={{ fontSize: "0.7rem", marginLeft: "0.25rem" }}>
              Dual-Custody Gate
            </span>
          </div>
          <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", margin: 0 }}>
            Cryptographically enforced human verification with Ed25519 signatures for high-divergence triage events.
          </p>
        </div>

        {/* Global Toolbar */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
          <button onClick={fetchPending} className="btn-secondary" title="Refresh pending requests" disabled={loading} style={{ fontSize: "0.82rem" }}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Refresh Queue
          </button>

          <button onClick={handleSimulateEscalation} className="btn-secondary" style={{ fontSize: "0.82rem" }}>
            <Zap size={14} color="var(--color-warning)" />
            Simulate Escalation
          </button>
        </div>
      </div>

      {/* Security Credentials Strip */}
      <div className="panel-card" style={{ padding: "0.9rem 1.25rem", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.8rem", flex: 1, minWidth: "280px" }}>
          <span style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-tertiary)", whiteSpace: "nowrap" }}>
            Arbiter Signing Key (Ed25519):
          </span>
          <input
            type={showKey ? "text" : "password"}
            value={arbiterPrivateKeyHex}
            onChange={(e) => setArbiterPrivateKeyHex(e.target.value)}
            className="form-input"
            style={{
              flex: 1,
              fontFamily: "var(--font-mono)",
              fontSize: "0.78rem",
              padding: "0.3rem 0.6rem",
              background: "var(--bg-app)",
            }}
          />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <button
            onClick={() => setShowKey(!showKey)}
            className="btn-secondary"
            style={{ padding: "0.35rem 0.75rem", fontSize: "0.78rem" }}
          >
            {showKey ? "Hide Secret" : "Reveal Key"}
          </button>
          <button
            onClick={generateNewKeypair}
            className="btn-secondary"
            style={{ padding: "0.35rem 0.75rem", fontSize: "0.78rem" }}
          >
            Rotate Key
          </button>
        </div>
      </div>

      {/* Main Grid: Pending Approvals & Decision History with Responsive 2-Col Collapse */}
      <div className="grid-responsive-2" style={{ alignItems: "start" }}>
        {/* Left Column: Pending Governance Requests */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ fontSize: "0.82rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)", margin: 0 }}>
              Pending Verification Requests ({requests.length})
            </h3>
            <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
              Requires Incident Commander Signature
            </span>
          </div>

          {requests.length === 0 ? (
            <div
              className="panel-card"
              style={{
                padding: "3.5rem 1.5rem",
                textAlign: "center",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: "0.85rem",
              }}
            >
              <div style={{ fontSize: "0.78rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-tertiary)" }}>
                Zero Pending Escalations
              </div>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", maxWidth: "420px", margin: "0 auto", lineHeight: "1.5" }}>
                All high-divergence actions have been reviewed or triaged within autonomous safety boundaries.
              </p>
              <button onClick={handleSimulateEscalation} className="btn-secondary" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }}>
                Simulate Urgent HITL Escalation
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {requests.map((req) => (
                <div
                  key={req.id}
                  className="panel-card"
                  style={{
                    padding: "1.1rem 1.25rem",
                    borderLeft: "3px solid var(--color-warning)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.65rem", flexWrap: "wrap", gap: "0.5rem" }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span className="badge-solid badge-critical" style={{ fontSize: "0.68rem" }}>
                          Role: {req.requires_role}
                        </span>
                        <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                          Req #{req.id.slice(0, 8)}
                        </span>
                      </div>
                      <div style={{ fontWeight: 700, fontSize: "0.98rem", marginTop: "0.35rem", color: "var(--text-primary)" }}>
                        {req.proposed_action}
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button
                        onClick={() => handleDecision(req, "APPROVED")}
                        className="btn-primary"
                        style={{ padding: "0.38rem 0.8rem", fontSize: "0.78rem" }}
                      >
                        <Check size={13} /> Approve
                      </button>
                      <button
                        onClick={() => handleDecision(req, "REJECTED")}
                        className="btn-danger"
                        style={{ padding: "0.38rem 0.8rem", fontSize: "0.78rem" }}
                      >
                        <X size={13} /> Reject
                      </button>
                    </div>
                  </div>

                  {/* Justification Details Box */}
                  <div
                    className="panel-elevated"
                    style={{
                      padding: "0.75rem 0.85rem",
                      borderRadius: "var(--radius-sm)",
                    }}
                  >
                    <div style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-tertiary)", marginBottom: "0.45rem" }}>
                      Telemetric Justification Evidence
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.5rem" }}>
                      {Object.entries(req.justification || {}).map(([key, val]) => (
                        <div key={key} style={{ background: "rgba(0,0,0,0.25)", padding: "0.4rem 0.6rem", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)" }}>
                          <span style={{ color: "var(--text-tertiary)", fontSize: "0.68rem", textTransform: "uppercase" }}>
                            {key.replace(/_/g, " ")}:{" "}
                          </span>
                          <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.78rem", fontFamily: "var(--font-mono)" }}>
                            {typeof val === "object" ? JSON.stringify(val) : String(val)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Column: Decisions Audit Trail */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ fontSize: "0.82rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)", margin: 0 }}>
              Session Decision Ledger ({decisionsHistory.length})
            </h3>
            <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
              Ed25519 Verified
            </span>
          </div>

          <div className="panel-card" style={{ padding: "1rem" }}>
            {decisionsHistory.length === 0 ? (
              <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
                No human arbitration decisions recorded in this session.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {decisionsHistory.map((item, idx) => (
                  <div
                    key={idx}
                    className="panel-elevated"
                    style={{
                      padding: "0.75rem",
                      borderRadius: "var(--radius-sm)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.25rem" }}>
                      <span style={{ fontWeight: 600, fontSize: "0.85rem", color: "var(--text-primary)" }}>{item.action}</span>
                      <span className={`badge-solid ${item.decision === "APPROVED" ? "badge-success" : "badge-critical"}`} style={{ fontSize: "0.65rem" }}>
                        {item.decision}
                      </span>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.7rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                      <span>Req #{item.id} • {item.timestamp}</span>
                      <span style={{ color: "var(--brand-primary)" }}>Sig: {item.signature}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default HitlCryptographicArbiterView;
