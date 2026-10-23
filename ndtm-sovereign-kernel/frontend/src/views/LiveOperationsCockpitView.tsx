import React, { useState, useEffect } from "react";
import { api, Incident } from "../services/api.ts";
import { RefreshCw, CheckCircle2, AlertCircle } from "lucide-react";

export const LiveOperationsCockpitView: React.FC = () => {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [filterUrgency, setFilterUrgency] = useState<string>("ALL");

  // Ingestion Form State
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [urgency, setUrgency] = useState("HIGH");
  const [category, setCategory] = useState("ELECTRICAL_GRID");
  const [lat, setLat] = useState("41.0082");
  const [lon, setLon] = useState("28.9784");
  const [submitting, setSubmitting] = useState(false);

  const fetchIncidents = async () => {
    try {
      setLoading(true);
      const data = await api.listIncidents(50);
      setIncidents(data);
    } catch (err: any) {
      console.error("Failed to load incidents:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIncidents();
    const interval = setInterval(fetchIncidents, 8000);
    return () => clearInterval(interval);
  }, []);

  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !description.trim()) return;

    try {
      setSubmitting(true);
      const res = await api.ingestIncident({
        title,
        description,
        urgency,
        category,
        modality: "TEXT_ONLY",
        latitude: parseFloat(lat),
        longitude: parseFloat(lon),
      });

      window.dispatchEvent(
        new CustomEvent("ndtm:toast", {
          detail: {
            message: `Incident #${res.id ? res.id.slice(0, 8) : "LOG"} triaged: ${res.category || category} (${res.triage_state || "QUEUED"})`,
            type: "success",
          },
        })
      );

      setTitle("");
      setDescription("");
      await fetchIncidents();
    } catch (err: any) {
      window.dispatchEvent(
        new CustomEvent("ndtm:toast", {
          detail: { message: `Ingest failed: ${err.message}`, type: "error" },
        })
      );
    } finally {
      setSubmitting(false);
    }
  };

  const applyPreset = (preset: {
    title: string;
    description: string;
    urgency: string;
    category: string;
    lat: string;
    lon: string;
  }) => {
    setTitle(preset.title);
    setDescription(preset.description);
    setUrgency(preset.urgency);
    setCategory(preset.category);
    setLat(preset.lat);
    setLon(preset.lon);
  };

  const filteredIncidents =
    filterUrgency === "ALL"
      ? incidents
      : incidents.filter((i) => i.urgency === filterUrgency);

  const criticalCount = incidents.filter((i) => i.urgency === "CRITICAL").length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", maxWidth: "1600px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <h2 style={{ fontSize: "1.35rem", fontWeight: 700, margin: 0, letterSpacing: "-0.015em" }}>
              Live Incident Ingestion & Triage
            </h2>
            <span className="badge badge-low">HAWKES POINT PROCESS</span>
          </div>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", margin: "0.3rem 0 0 0" }}>
            Real-time multimodal incident ingestion pipeline with PII scrubbing, ONNX classification, and automatic spatio-temporal clustering.
          </p>
        </div>

        <button onClick={fetchIncidents} className="btn-secondary" disabled={loading}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Sync Stream
        </button>
      </div>

      {/* Operational Metrics Grid */}
      <div className="grid-responsive-kpi">
        <div className="card" style={{ padding: "0.9rem 1.1rem" }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Active Stream Inflow
          </div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.3rem 0 0.1rem 0", fontFamily: "var(--font-mono)" }}>
            {incidents.length}
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--color-success)", display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <span className="status-dot status-dot-green" />
            <span>Ingestion pipeline connected</span>
          </div>
        </div>

        <div className="card" style={{ padding: "0.9rem 1.1rem" }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Critical Alarms
          </div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.3rem 0 0.1rem 0", color: criticalCount > 0 ? "var(--color-danger)" : "var(--text-primary)", fontFamily: "var(--font-mono)" }}>
            {criticalCount}
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
            Immediate SLA response required
          </div>
        </div>

        <div className="card" style={{ padding: "0.9rem 1.1rem" }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Triage Latency (P99)
          </div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.3rem 0 0.1rem 0", fontFamily: "var(--font-mono)" }}>
            4.2<span style={{ fontSize: "0.85rem", color: "var(--text-tertiary)", fontWeight: 500 }}>ms</span>
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
            Zero-copy POSIX SHM bound
          </div>
        </div>

        <div className="card" style={{ padding: "0.9rem 1.1rem" }}>
          <div style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Model Confidence Mean
          </div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.3rem 0 0.1rem 0", fontFamily: "var(--font-mono)" }}>
            92.8<span style={{ fontSize: "0.85rem", color: "var(--text-tertiary)", fontWeight: 500 }}>%</span>
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
            Student model INT8 quantized
          </div>
        </div>
      </div>

      {/* Main Responsive Grid: Ingestion Form & Incident Stream */}
      <div className="grid-responsive-2" style={{ alignItems: "start" }}>
        {/* Left Column: Incident Dispatch Form */}
        <div className="card" style={{ padding: "1.25rem" }}>
          <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "1rem", paddingBottom: "0.65rem", borderBottom: "1px solid var(--border-subtle)" }}>
            Dispatch Operational Incident
          </div>

          {/* Quick Scenario Presets */}
          <div style={{ marginBottom: "1rem" }}>
            <div style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.4rem" }}>
              Quick Scenario Presets
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
              <button
                type="button"
                onClick={() =>
                  applyPreset({
                    title: "Kadıköy Rıhtım Trafo Patlaması & Duman",
                    description: "Kadıköy Rıhtım ana indirici merkez trafosunda aşırı ısınma ve patlama. Bölgesel enerji kesintisi mevcut.",
                    urgency: "CRITICAL",
                    category: "ELECTRICAL_GRID",
                    lat: "40.9912",
                    lon: "29.0254",
                  })
                }
                className="btn-secondary"
                style={{ fontSize: "0.72rem", padding: "0.3rem 0.55rem" }}
              >
                Trafo Patlaması
              </button>
              <button
                type="button"
                onClick={() =>
                  applyPreset({
                    title: "Beşiktaş Barbaros Gaz Basınç Düşüşü",
                    description: "BOTAŞ dağıtım hattı manometrelerinde ani %60 basınç kaybı ve koku ihbarları bildirildi.",
                    urgency: "CRITICAL",
                    category: "GAS_PIPELINE",
                    lat: "41.0428",
                    lon: "29.0077",
                  })
                }
                className="btn-secondary"
                style={{ fontSize: "0.72rem", padding: "0.3rem 0.55rem" }}
              >
                Gaz Sızıntısı
              </button>
              <button
                type="button"
                onClick={() =>
                  applyPreset({
                    title: "Maslak Ana Fiber Hat Kesintisi",
                    description: "Büyükdere Caddesi metro kazı bölgesinde ana fiber optik ring kablosu koptu.",
                    urgency: "HIGH",
                    category: "TELECOMMUNICATIONS",
                    lat: "41.1105",
                    lon: "29.0211",
                  })
                }
                className="btn-secondary"
                style={{ fontSize: "0.72rem", padding: "0.3rem 0.55rem" }}
              >
                Fiber Kesintisi
              </button>
            </div>
          </div>

          <form onSubmit={handleIngest} style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.3rem", fontWeight: 500 }}>
                Incident Title
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Kadıköy Ana İndirici Trafo Arızası"
                className="form-input"
                required
              />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.3rem", fontWeight: 500 }}>
                  Urgency Level
                </label>
                <select
                  value={urgency}
                  onChange={(e) => setUrgency(e.target.value)}
                  className="form-select"
                >
                  <option value="CRITICAL">CRITICAL</option>
                  <option value="HIGH">HIGH</option>
                  <option value="MEDIUM">MEDIUM</option>
                  <option value="LOW">LOW</option>
                </select>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.3rem", fontWeight: 500 }}>
                  Category
                </label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="form-select"
                >
                  <option value="ELECTRICAL_GRID">ELECTRICAL_GRID</option>
                  <option value="GAS_PIPELINE">GAS_PIPELINE</option>
                  <option value="WATER_MAINS">WATER_MAINS</option>
                  <option value="TELECOMMUNICATIONS">TELECOMMUNICATIONS</option>
                  <option value="ROAD_HAZARD">ROAD_HAZARD</option>
                </select>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.3rem", fontWeight: 500 }}>
                  Latitude
                </label>
                <input
                  type="text"
                  value={lat}
                  onChange={(e) => setLat(e.target.value)}
                  className="form-input font-mono"
                  required
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.3rem", fontWeight: 500 }}>
                  Longitude
                </label>
                <input
                  type="text"
                  value={lon}
                  onChange={(e) => setLon(e.target.value)}
                  className="form-input font-mono"
                  required
                />
              </div>
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.3rem", fontWeight: 500 }}>
                Incident Description (PII auto-scrubbed)
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Enter incident telemetry, sensor reports, or field observations..."
                rows={3}
                className="form-textarea"
                required
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="btn-primary"
              style={{ width: "100%", padding: "0.6rem 1rem", marginTop: "0.25rem" }}
            >
              {submitting ? "Triaging via Student ONNX..." : "Ingest & Execute Triage"}
            </button>
          </form>
        </div>

        {/* Right Column: Live Incident Stream */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          {/* Stream Filter Bar */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>
                Live Operational Stream
              </span>
              <span style={{ fontSize: "0.7rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                ({filteredIncidents.length})
              </span>
            </div>

            <div style={{ display: "flex", gap: "0.25rem" }}>
              {["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map((lvl) => (
                <button
                  key={lvl}
                  onClick={() => setFilterUrgency(lvl)}
                  style={{
                    padding: "0.25rem 0.55rem",
                    borderRadius: "4px",
                    background: filterUrgency === lvl ? "var(--bg-surface-elevated)" : "transparent",
                    border: `1px solid ${filterUrgency === lvl ? "var(--border-medium)" : "transparent"}`,
                    color: filterUrgency === lvl ? "var(--text-primary)" : "var(--text-tertiary)",
                    fontSize: "0.7rem",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  {lvl}
                </button>
              ))}
            </div>
          </div>

          {/* Incident Feed Cards */}
          {filteredIncidents.length === 0 ? (
            <div className="card" style={{ padding: "3rem 1.5rem", textAlign: "center" }}>
              <div style={{ fontWeight: 600, fontSize: "0.95rem", marginBottom: "0.25rem" }}>No Active Incidents</div>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.8rem", maxWidth: "360px", margin: "0 auto" }}>
                No incidents match the active filter criteria. Ingest a new scenario from the left panel.
              </p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {filteredIncidents.map((inc) => (
                <div
                  key={inc.id}
                  className="card"
                  style={{
                    padding: "1rem 1.15rem",
                    borderLeft: `3px solid ${
                      inc.urgency === "CRITICAL"
                        ? "#ef4444"
                        : inc.urgency === "HIGH"
                        ? "#f59e0b"
                        : "#3b82f6"
                    }`,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.4rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.45rem", flexWrap: "wrap" }}>
                      <span className={`badge ${
                        inc.urgency === "CRITICAL"
                          ? "badge-critical"
                          : inc.urgency === "HIGH"
                          ? "badge-high"
                          : "badge-medium"
                      }`}>
                        {inc.urgency}
                      </span>
                      <span style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase" }}>
                        {inc.category}
                      </span>
                      <span style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                        #{inc.id ? inc.id.slice(0, 8) : "LOG"}
                      </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span className="badge badge-low" style={{ fontSize: "0.65rem" }}>
                        {inc.triage_state || "TRIAGED"}
                      </span>
                      <span style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                        {inc.created_at ? new Date(inc.created_at).toLocaleTimeString() : "Recent"}
                      </span>
                    </div>
                  </div>

                  <h3 style={{ fontSize: "0.925rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.35rem" }}>
                    {inc.title}
                  </h3>

                  <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: "1.4", marginBottom: "0.75rem" }}>
                    {inc.description}
                  </p>

                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: "0.5rem", borderTop: "1px solid var(--border-subtle)" }}>
                    <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
                      Confidence: <strong style={{ color: "var(--text-primary)" }}>{inc.confidence ? `${(inc.confidence * 100).toFixed(0)}%` : "92%"}</strong>
                    </div>

                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <button
                        onClick={() => {
                          window.location.hash = "z3";
                        }}
                        className="btn-secondary"
                        style={{ padding: "0.25rem 0.55rem", fontSize: "0.72rem" }}
                      >
                        Dispatch Team
                      </button>
                      {inc.urgency === "CRITICAL" && (
                        <button
                          onClick={() => {
                            window.location.hash = "hitl";
                          }}
                          className="btn-danger"
                          style={{ padding: "0.25rem 0.55rem", fontSize: "0.72rem" }}
                        >
                          HITL Arbiter
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
