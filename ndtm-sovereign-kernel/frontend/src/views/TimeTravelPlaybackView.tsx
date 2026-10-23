import React, { useState } from "react";
import { api } from "../services/api.ts";
import { Play } from "lucide-react";

export const TimeTravelPlaybackView: React.FC = () => {
  const [timestampIso, setTimestampIso] = useState<string>(
    new Date(Date.now() - 3600000).toISOString()
  );
  const [reconstructedState, setReconstructedState] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleTimeTravel = async () => {
    try {
      setLoading(true);
      const res = await api.timeTravelState(timestampIso);
      setReconstructedState(res);
    } catch (e: any) {
      alert(`Time-travel error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const setOffsetMinutes = (minsAgo: number) => {
    const t = new Date(Date.now() - minsAgo * 60000).toISOString();
    setTimestampIso(t);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: "1600px", margin: "0 auto", width: "100%" }}>
      {/* Header */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
          <span className="status-dot status-dot-active" />
          <h1 style={{ fontSize: "1.45rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em", margin: 0 }}>
            Event Sourcing Time-Travel Flight Recorder
          </h1>
        </div>
        <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", margin: 0 }}>
          Reconstruct complete kernel operational state as of any exact microsecond in the past by chronological event folding.
        </p>
      </div>

      {/* Scrubbing Bar */}
      <div className="panel-card" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem" }}>
          <h3 style={{ fontSize: "0.85rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)", margin: 0 }}>
            Historical Cutoff Selector
          </h3>
        </div>

        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button onClick={() => setOffsetMinutes(15)} className="btn-secondary" style={{ fontSize: "0.78rem", padding: "0.3rem 0.65rem" }}>
            15 mins ago
          </button>
          <button onClick={() => setOffsetMinutes(60)} className="btn-secondary" style={{ fontSize: "0.78rem", padding: "0.3rem 0.65rem" }}>
            1 hour ago
          </button>
          <button onClick={() => setOffsetMinutes(360)} className="btn-secondary" style={{ fontSize: "0.78rem", padding: "0.3rem 0.65rem" }}>
            6 hours ago
          </button>
          <button onClick={() => setOffsetMinutes(1440)} className="btn-secondary" style={{ fontSize: "0.78rem", padding: "0.3rem 0.65rem" }}>
            24 hours ago
          </button>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
          <input
            type="text"
            value={timestampIso}
            onChange={(e) => setTimestampIso(e.target.value)}
            className="form-input"
            style={{
              flex: 1,
              minWidth: "260px",
              padding: "0.45rem 0.75rem",
              background: "var(--bg-app)",
              fontFamily: "var(--font-mono)",
              fontSize: "0.82rem",
            }}
          />

          <button onClick={handleTimeTravel} className="btn-primary" disabled={loading} style={{ fontSize: "0.82rem" }}>
            <Play size={14} />
            {loading ? "Replaying Ledger..." : "Reconstruct State"}
          </button>
        </div>
      </div>

      {/* Reconstructed State Display */}
      <div className="panel-card" style={{ padding: "1.25rem" }}>
        <div style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem", marginBottom: "1rem" }}>
          <h3 style={{ fontSize: "0.85rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)", margin: 0 }}>
            Reconstructed State Inspection
          </h3>
        </div>

        {reconstructedState ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ padding: "0.75rem 1rem", background: "rgba(5, 150, 105, 0.08)", border: "1px solid rgba(5, 150, 105, 0.25)", borderRadius: "var(--radius-sm)", display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
              <span style={{ fontSize: "0.82rem", color: "var(--color-success)", fontWeight: 700 }}>
                Total Events Replayed: {reconstructedState.applied_events_count}
              </span>
              <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                As Of: {new Date(reconstructedState.as_of_timestamp).toLocaleString()}
              </span>
            </div>

            <div className="grid-responsive-2">
              <div className="panel-elevated" style={{ padding: "1rem", borderRadius: "var(--radius-sm)" }}>
                <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                  Active Incidents ({Object.keys(reconstructedState.incidents || {}).length})
                </div>
                <pre style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontFamily: "var(--font-mono)", maxHeight: "250px", overflowY: "auto", margin: 0 }}>
                  {JSON.stringify(reconstructedState.incidents, null, 2)}
                </pre>
              </div>

              <div className="panel-elevated" style={{ padding: "1rem", borderRadius: "var(--radius-sm)" }}>
                <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                  Active Dispatches ({Object.keys(reconstructedState.dispatches || {}).length})
                </div>
                <pre style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontFamily: "var(--font-mono)", maxHeight: "250px", overflowY: "auto", margin: 0 }}>
                  {JSON.stringify(reconstructedState.dispatches, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        ) : (
          <div style={{ textAlign: "center", padding: "4rem 1rem", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
            Select an ISO timestamp and click "Reconstruct State" to fold past events into the state machine.
          </div>
        )}
      </div>
    </div>
  );
};

export default TimeTravelPlaybackView;
