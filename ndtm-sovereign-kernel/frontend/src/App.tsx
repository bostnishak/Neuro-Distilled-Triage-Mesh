import React, { useState, useEffect } from "react";
import {
  Shield,
  Activity,
  Network,
  Scale,
  ShieldCheck,
  Code,
  Layers,
  ShieldAlert,
  Link2,
  History,
  GitPullRequest,
  Globe,
  Radio,
  UserCheck,
  ChevronDown,
  CheckCircle2,
  AlertCircle,
  X,
  Menu,
} from "lucide-react";

import { api, OPERATOR_PROFILES, OperatorProfile } from "./services/api.ts";
import { LiveOperationsCockpitView } from "./views/LiveOperationsCockpitView.tsx";
import { HawkesPointProcessVisualizerView } from "./views/HawkesPointProcessVisualizerView.tsx";
import { CausalDigitalTwinView } from "./views/CausalDigitalTwinView.tsx";
import { Z3ParetoDispatchMatrixView } from "./views/Z3ParetoDispatchMatrixView.tsx";
import { HitlCryptographicArbiterView } from "./views/HitlCryptographicArbiterView.tsx";
import { RuleLangStudioView } from "./views/RuleLangStudioView.tsx";
import { ModelDistillationMonitorView } from "./views/ModelDistillationMonitorView.tsx";
import { ByzantineMeshDashboardView } from "./views/ByzantineMeshDashboardView.tsx";
import { MerkleAuditChainView } from "./views/MerkleAuditChainView.tsx";
import { TimeTravelPlaybackView } from "./views/TimeTravelPlaybackView.tsx";
import { View11_CanaryRolloutAndModelSupplyChain } from "./views/View11_CanaryRolloutAndModelSupplyChain.tsx";
import { View12_MultiRegionCrdtAndSloBurnRate } from "./views/View12_MultiRegionCrdtAndSloBurnRate.tsx";

type ViewKey =
  | "live"
  | "causal"
  | "z3"
  | "hitl"
  | "hawkes"
  | "distill"
  | "rulelang"
  | "byzantine"
  | "crdt"
  | "merkle"
  | "timetravel"
  | "canary";

interface NavItem {
  key: ViewKey;
  label: string;
  category: "OPERATIONS" | "INTELLIGENCE" | "SRE & COMPLIANCE";
  icon: React.ReactNode;
}

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("Cockpit View Error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="card" style={{ padding: "2.5rem", maxWidth: "600px", margin: "2rem auto" }}>
          <h2 style={{ fontSize: "1.2rem", color: "var(--color-danger)", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <AlertCircle size={18} />
            Component Recovery Active
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginBottom: "1.25rem" }}>
            The operating view encountered an unexpected error. You can safely retry rendering.
          </p>
          <pre style={{ background: "var(--bg-app)", padding: "0.85rem", borderRadius: "6px", overflowX: "auto", fontSize: "0.78rem", color: "var(--text-tertiary)", marginBottom: "1.25rem" }}>
            {this.state.error?.message || "Unknown error"}
          </pre>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="btn-primary"
          >
            Retry Component
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export const App: React.FC = () => {
  const getInitialView = (): ViewKey => {
    const hash = window.location.hash.replace("#", "") as ViewKey;
    const validKeys: ViewKey[] = [
      "live", "causal", "z3", "hitl", "hawkes", "distill",
      "rulelang", "byzantine", "crdt", "merkle", "timetravel", "canary"
    ];
    return validKeys.includes(hash) ? hash : "live";
  };

  const [currentView, setCurrentView] = useState<ViewKey>(getInitialView);
  const [activeProfile, setActiveProfile] = useState<OperatorProfile>(OPERATOR_PROFILES[0]);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState<boolean>(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState<boolean>(false);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" | "info" } | null>(null);

  // Auto-login on load
  useEffect(() => {
    api.ensureAuthenticated().then(() => {
      const u = api.getCurrentUser();
      if (u) {
        const found = OPERATOR_PROFILES.find((p) => p.email === u.email);
        if (found) setActiveProfile(found);
      }
    });

    const handleCustomToast = (e: any) => {
      if (e.detail) {
        setToast(e.detail);
        setTimeout(() => setToast(null), 4500);
      }
    };

    window.addEventListener("ndtm:toast", handleCustomToast);
    return () => window.removeEventListener("ndtm:toast", handleCustomToast);
  }, []);

  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.replace("#", "") as ViewKey;
      const validKeys: ViewKey[] = [
        "live", "causal", "z3", "hitl", "hawkes", "distill",
        "rulelang", "byzantine", "crdt", "merkle", "timetravel", "canary"
      ];
      if (validKeys.includes(hash)) {
        setCurrentView(hash);
      }
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const handleSelectView = (key: ViewKey) => {
    setCurrentView(key);
    window.location.hash = key;
    setMobileMenuOpen(false);
  };

  const handleProfileSwitch = async (profile: OperatorProfile) => {
    try {
      await api.switchProfile(profile.email);
      setActiveProfile(profile);
      setProfileDropdownOpen(false);
      window.dispatchEvent(
        new CustomEvent("ndtm:toast", {
          detail: { message: `Active operator switched to ${profile.name} (${profile.role})`, type: "success" },
        })
      );
    } catch (err: any) {
      window.dispatchEvent(
        new CustomEvent("ndtm:toast", {
          detail: { message: `Operator switch failed: ${err.message}`, type: "error" },
        })
      );
    }
  };

  const navItems: NavItem[] = [
    // Operations
    { key: "live", label: "Live Incident Cockpit", category: "OPERATIONS", icon: <Shield size={16} /> },
    { key: "causal", label: "Causal Digital Twin", category: "OPERATIONS", icon: <Network size={16} /> },
    { key: "z3", label: "Pareto Fleet Dispatch", category: "OPERATIONS", icon: <Scale size={16} /> },
    { key: "hitl", label: "HITL Arbiter (Ed25519)", category: "OPERATIONS", icon: <ShieldCheck size={16} /> },

    // Intelligence
    { key: "hawkes", label: "Hawkes Point Process", category: "INTELLIGENCE", icon: <Activity size={16} /> },
    { key: "distill", label: "Distillation Forge", category: "INTELLIGENCE", icon: <Layers size={16} /> },
    { key: "rulelang", label: "RuleLang Studio", category: "INTELLIGENCE", icon: <Code size={16} /> },
    { key: "byzantine", label: "Byzantine Federated Mesh", category: "INTELLIGENCE", icon: <ShieldAlert size={16} /> },

    // SRE & Compliance
    { key: "crdt", label: "Multi-Region CRDT & SLO", category: "SRE & COMPLIANCE", icon: <Globe size={16} /> },
    { key: "merkle", label: "Merkle Audit Ledger", category: "SRE & COMPLIANCE", icon: <Link2 size={16} /> },
    { key: "timetravel", label: "Time-Travel Recorder", category: "SRE & COMPLIANCE", icon: <History size={16} /> },
    { key: "canary", label: "Canary Rollout Pipeline", category: "SRE & COMPLIANCE", icon: <GitPullRequest size={16} /> },
  ];

  const renderView = () => {
    switch (currentView) {
      case "live":
        return <LiveOperationsCockpitView />;
      case "causal":
        return <CausalDigitalTwinView />;
      case "z3":
        return <Z3ParetoDispatchMatrixView />;
      case "hitl":
        return <HitlCryptographicArbiterView />;
      case "hawkes":
        return <HawkesPointProcessVisualizerView />;
      case "rulelang":
        return <RuleLangStudioView />;
      case "distill":
        return <ModelDistillationMonitorView />;
      case "byzantine":
        return <ByzantineMeshDashboardView />;
      case "merkle":
        return <MerkleAuditChainView />;
      case "timetravel":
        return <TimeTravelPlaybackView />;
      case "canary":
        return <View11_CanaryRolloutAndModelSupplyChain />;
      case "crdt":
        return <View12_MultiRegionCrdtAndSloBurnRate />;
      default:
        return <LiveOperationsCockpitView />;
    }
  };

  const categories: ("OPERATIONS" | "INTELLIGENCE" | "SRE & COMPLIANCE")[] = [
    "OPERATIONS",
    "INTELLIGENCE",
    "SRE & COMPLIANCE",
  ];

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--bg-app)", position: "relative" }}>
      {/* Mobile Drawer Overlay */}
      {mobileMenuOpen && (
        <div
          onClick={() => setMobileMenuOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.6)",
            backdropFilter: "blur(4px)",
            zIndex: 40,
          }}
        />
      )}

      {/* Sidebar Navigation */}
      <aside
        style={{
          width: "250px",
          background: "var(--bg-sidebar)",
          borderRight: "1px solid var(--border-subtle)",
          display: "flex",
          flexDirection: "column",
          padding: "1.25rem 0.85rem",
          flexShrink: 0,
          transition: "transform 0.25s ease",
          zIndex: 50,
          position: "sticky",
          top: 0,
          height: "100vh",
        }}
        className={`cockpit-sidebar ${mobileMenuOpen ? "open" : ""}`}
      >
        {/* Brand Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.2rem 0.4rem 1.25rem", borderBottom: "1px solid var(--border-subtle)", marginBottom: "1rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div
              style={{
                width: "32px",
                height: "32px",
                borderRadius: "6px",
                background: "#181b22",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#f3f4f6",
                fontWeight: "700",
                fontSize: "0.9rem",
                letterSpacing: "-0.02em",
              }}
            >
              N9
            </div>
            <div>
              <div style={{ fontSize: "0.9rem", fontWeight: "700", color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                NDTM-9000
              </div>
              <div style={{ fontSize: "0.65rem", color: "var(--text-tertiary)", fontWeight: "600", letterSpacing: "0.06em" }}>
                SOVEREIGN KERNEL
              </div>
            </div>
          </div>

          {/* Close button for mobile */}
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="mobile-close-btn"
            style={{
              display: "none",
              background: "transparent",
              border: "none",
              color: "var(--text-tertiary)",
              cursor: "pointer",
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Categorized Navigation */}
        <nav style={{ display: "flex", flexDirection: "column", gap: "1.25rem", flex: 1, overflowY: "auto" }}>
          {categories.map((cat) => (
            <div key={cat} style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
              <div style={{ fontSize: "0.65rem", fontWeight: "700", color: "var(--text-tertiary)", padding: "0.2rem 0.5rem", letterSpacing: "0.06em" }}>
                {cat}
              </div>
              {navItems
                .filter((item) => item.category === cat)
                .map((item) => {
                  const isActive = currentView === item.key;
                  return (
                    <button
                      key={item.key}
                      onClick={() => handleSelectView(item.key)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.65rem",
                        padding: "0.5rem 0.65rem",
                        borderRadius: "var(--radius-sm)",
                        background: isActive ? "var(--bg-surface-elevated)" : "transparent",
                        border: isActive ? "1px solid var(--border-medium)" : "1px solid transparent",
                        color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                        fontWeight: isActive ? "600" : "500",
                        fontSize: "0.8rem",
                        cursor: "pointer",
                        textAlign: "left",
                        transition: "all 0.15s ease",
                      }}
                      onMouseEnter={(e) => {
                        if (!isActive) {
                          e.currentTarget.style.background = "rgba(255, 255, 255, 0.02)";
                          e.currentTarget.style.color = "var(--text-primary)";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!isActive) {
                          e.currentTarget.style.background = "transparent";
                          e.currentTarget.style.color = "var(--text-secondary)";
                        }
                      }}
                    >
                      <span style={{ color: isActive ? "#3b82f6" : "var(--text-tertiary)" }}>
                        {item.icon}
                      </span>
                      {item.label}
                    </button>
                  );
                })}
            </div>
          ))}
        </nav>

        {/* Cluster Status Footer */}
        <div style={{ marginTop: "auto", paddingTop: "0.85rem", borderTop: "1px solid var(--border-subtle)" }}>
          <div style={{ padding: "0.65rem 0.75rem", background: "var(--bg-surface)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
              <span className="status-dot status-dot-green" />
              <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)", fontWeight: "500" }}>
                Mesh Verified
              </span>
            </div>
            <span style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
              P99: 4.2ms
            </span>
          </div>
        </div>
      </aside>

      {/* Main View Area */}
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>
        {/* Top Header Bar */}
        <header
          style={{
            height: "54px",
            background: "var(--bg-surface)",
            borderBottom: "1px solid var(--border-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 clamp(1rem, 2vw, 1.75rem)",
            flexShrink: 0,
            zIndex: 10,
            gap: "1rem",
          }}
        >
          {/* Left: Mobile Toggle & Telemetry Status */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="mobile-hamburger-btn"
              style={{
                display: "none",
                background: "transparent",
                border: "none",
                color: "var(--text-primary)",
                cursor: "pointer",
                padding: "0.25rem",
              }}
            >
              <Menu size={20} />
            </button>

            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.78rem", color: "var(--text-secondary)" }}>
              <span className="status-dot status-dot-green animate-pulse" />
              <span>Node Istanbul-01</span>
              <span style={{ color: "var(--border-medium)" }}>•</span>
              <span style={{ color: "var(--color-success)", fontWeight: "600" }}>Invariants Normal</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.72rem", background: "var(--bg-app)", padding: "0.2rem 0.5rem", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)", color: "var(--text-tertiary)" }}>
              <span>SLO:</span>
              <span style={{ color: "var(--text-primary)", fontWeight: "600" }}>99.9%</span>
            </div>
          </div>

          {/* Right: Operator Identity Switcher */}
          <div style={{ position: "relative" }}>
            <button
              onClick={() => setProfileDropdownOpen(!profileDropdownOpen)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.35rem 0.7rem",
                background: "var(--bg-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-sm)",
                color: "var(--text-primary)",
                cursor: "pointer",
                fontSize: "0.8rem",
                fontFamily: "var(--font-heading)",
                transition: "all 0.15s ease",
              }}
            >
              <UserCheck size={14} color="#3b82f6" />
              <div style={{ textAlign: "left" }}>
                <div style={{ fontWeight: "600", lineHeight: "1.1", fontSize: "0.8rem" }}>{activeProfile.name}</div>
                <div style={{ fontSize: "0.65rem", color: "var(--text-tertiary)", fontWeight: "500" }}>
                  {activeProfile.role}
                </div>
              </div>
              <ChevronDown size={13} color="var(--text-tertiary)" style={{ marginLeft: "0.2rem" }} />
            </button>

            {/* Profile Dropdown */}
            {profileDropdownOpen && (
              <div
                style={{
                  position: "absolute",
                  top: "115%",
                  right: 0,
                  width: "280px",
                  background: "var(--bg-surface-elevated)",
                  border: "1px solid var(--border-medium)",
                  borderRadius: "var(--radius-md)",
                  boxShadow: "0 10px 30px rgba(0, 0, 0, 0.7)",
                  padding: "0.4rem",
                  zIndex: 100,
                }}
              >
                <div style={{ padding: "0.4rem 0.5rem", fontSize: "0.68rem", color: "var(--text-tertiary)", fontWeight: "700", letterSpacing: "0.05em" }}>
                  SWITCH OPERATOR IDENTITY
                </div>
                {OPERATOR_PROFILES.map((p) => (
                  <button
                    key={p.email}
                    onClick={() => handleProfileSwitch(p)}
                    style={{
                      width: "100%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "0.5rem 0.65rem",
                      background: p.email === activeProfile.email ? "rgba(37, 84, 215, 0.15)" : "transparent",
                      border: "none",
                      borderRadius: "var(--radius-sm)",
                      color: p.email === activeProfile.email ? "var(--text-primary)" : "var(--text-secondary)",
                      cursor: "pointer",
                      textAlign: "left",
                      fontSize: "0.8rem",
                      marginBottom: "0.2rem",
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: "600" }}>{p.name}</div>
                      <div style={{ fontSize: "0.68rem", color: "var(--text-tertiary)" }}>{p.email}</div>
                    </div>
                    <span className="badge badge-low" style={{ fontSize: "0.62rem" }}>
                      {p.badge}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </header>

        {/* View Content Canvas */}
        <main style={{ flex: 1, padding: "clamp(1rem, 2vw, 1.5rem)", overflowY: "auto", minWidth: 0 }}>
          <ErrorBoundary>
            {renderView()}
          </ErrorBoundary>
        </main>
      </div>

      {/* Global Interactive Toast Notification */}
      {toast && (
        <div className="toast-banner">
          {toast.type === "success" && <span className="status-dot status-dot-green" style={{ marginTop: "4px" }} />}
          {toast.type === "error" && <span className="status-dot status-dot-red" style={{ marginTop: "4px" }} />}
          {toast.type === "info" && <span className="status-dot status-dot-blue" style={{ marginTop: "4px" }} />}
          <div style={{ flex: 1, fontSize: "0.825rem", color: "var(--text-primary)" }}>
            {toast.message}
          </div>
          <button
            onClick={() => setToast(null)}
            style={{ background: "transparent", border: "none", color: "var(--text-tertiary)", cursor: "pointer" }}
          >
            <X size={13} />
          </button>
        </div>
      )}
    </div>
  );
};

export default App;
