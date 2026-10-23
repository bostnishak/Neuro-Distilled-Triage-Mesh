import React, { useState, useEffect } from "react";
import { useAuth } from "./context/AuthContext";
import { wsClient } from "./services/wsClient";
import { UserRole } from "./types/api";

import { TriageGatekeeperView } from "./views/TriageGatekeeperView";
import { DistillMeshRouterView } from "./views/DistillMeshRouterView";
import { SymbolicSchedulerView } from "./views/SymbolicSchedulerView";
import { SecurityAndChaosView } from "./views/SecurityAndChaosView";
import { CausalTwinMapView } from "./views/CausalTwinMapView";
import { McpAndHitlConsoleView } from "./views/McpAndHitlConsoleView";
import { FederatedPrivacyView } from "./views/FederatedPrivacyView";
import { MerkleAndSpeculativeView } from "./views/MerkleAndSpeculativeView";

type ActiveTab =
  | "triage"
  | "router"
  | "scheduler"
  | "security"
  | "causal"
  | "mcp_hitl"
  | "federated"
  | "merkle_spec";

export const App: React.FC = () => {
  const { role, setRole } = useAuth();
  const [activeTab, setActiveTab] = useState<ActiveTab>("triage");
  const [wsConnected, setWsConnected] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setWsConnected(wsClient.isConnected());
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  const handleRoleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setRole(e.target.value as UserRole);
  };

  const navTabs: { id: ActiveTab; label: string; badge?: string }[] = [
    { id: "triage", label: "1. İhbar & Triaj" },
    { id: "router", label: "2. Model Yönlendirici" },
    { id: "scheduler", label: "3. Z3 Saha Atama" },
    { id: "security", label: "4. Sistem & DLQ" },
    { id: "causal", label: "5. Nedensel İkiz (Causal)", badge: "v2.0" },
    { id: "mcp_hitl", label: "6. MCP & HITL Kapısı", badge: "v2.0" },
    { id: "federated", label: "7. Federasyon & DP", badge: "v2.0" },
    { id: "merkle_spec", label: "8. Merkle & Spekülatif", badge: "v2.0" },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col selection:bg-cyan-500 selection:text-black">
      {/* Üst Navigasyon Çubuğu */}
      <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-50 backdrop-blur-md bg-slate-900/90">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Logo ve Başlık */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-cyan-600 via-blue-600 to-indigo-600 flex items-center justify-center shadow-md">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-base tracking-tight text-white">TriageMesh</span>
                <span className="text-[10px] bg-gradient-to-r from-cyan-900 to-indigo-900 text-cyan-300 border border-cyan-700 px-1.5 py-0.5 rounded font-mono font-bold">
                  v2.0 Sovereign
                </span>
              </div>
              <p className="text-[11px] text-slate-400 hidden sm:block">Sovereign Distributed & Autonomous AI Cockpit</p>
            </div>
          </div>

          {/* Sağ Alan: Canlı Durum ve Rol Seçimi */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-slate-950 border border-slate-800 text-xs">
              <span
                className={`w-2 h-2 rounded-full ${
                  wsConnected ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
                }`}
              ></span>
              <span className="text-slate-400 hidden md:inline">
                {wsConnected ? "Canlı Bağlantı" : "Yeniden Bağlanıyor..."}
              </span>
            </div>

            <div className="flex items-center gap-2 bg-slate-950 border border-slate-800 px-3 py-1 rounded-lg text-xs">
              <span className="text-slate-400">Rol:</span>
              <select
                id="select-user-role"
                value={role}
                onChange={handleRoleChange}
                className="bg-transparent text-cyan-300 font-semibold focus:outline-none cursor-pointer"
              >
                <option value="OPERATOR" className="bg-slate-900 text-slate-200">
                  Operatör
                </option>
                <option value="ARCHITECT" className="bg-slate-900 text-slate-200">
                  Sistem Yöneticisi (Architect)
                </option>
                <option value="AUDITOR" className="bg-slate-900 text-slate-200">
                  Denetçi (Auditor)
                </option>
              </select>
            </div>
          </div>
        </div>

        {/* 8-Tab Menüsü */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex space-x-1 border-t border-slate-800/80 overflow-x-auto">
          {navTabs.map((tab) => (
            <button
              key={tab.id}
              id={`tab-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={`py-3 px-3 text-xs font-semibold transition whitespace-nowrap border-b-2 flex items-center gap-1.5 ${
                activeTab === tab.id
                  ? "border-cyan-400 text-cyan-300 bg-cyan-950/20 font-bold"
                  : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700"
              }`}
            >
              <span>{tab.label}</span>
              {tab.badge && (
                <span className="text-[9px] font-mono px-1 py-0.2 bg-indigo-950 text-indigo-300 rounded border border-indigo-800">
                  {tab.badge}
                </span>
              )}
            </button>
          ))}
        </div>
      </header>

      {/* Ana İçerik (8 Views) */}
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 w-full">
        {activeTab === "triage" && <TriageGatekeeperView />}
        {activeTab === "router" && <DistillMeshRouterView />}
        {activeTab === "scheduler" && <SymbolicSchedulerView />}
        {activeTab === "security" && <SecurityAndChaosView />}
        {activeTab === "causal" && <CausalTwinMapView />}
        {activeTab === "mcp_hitl" && <McpAndHitlConsoleView />}
        {activeTab === "federated" && <FederatedPrivacyView />}
        {activeTab === "merkle_spec" && <MerkleAndSpeculativeView />}
      </main>

      {/* Alt Bilgi */}
      <footer className="bg-slate-900 border-t border-slate-800 py-3 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-[11px] text-slate-400">
            <span>FastAPI 2.0</span>
            <span>•</span>
            <span>PostGIS + pgvector</span>
            <span>•</span>
            <span>Z3 Solver</span>
            <span>•</span>
            <span>C++20 Edge FFT</span>
            <span>•</span>
            <span>MCP & Ed25519</span>
            <span>•</span>
            <span>Multi-Krum DP</span>
            <span>•</span>
            <span>Merkle Ledger</span>
          </div>
          <div className="text-[11px] text-slate-500">
            NDTM Sovereign Edition v2.0 • 8-View Autonomous Cockpit
          </div>
        </div>
      </footer>
    </div>
  );
};

export default App;
