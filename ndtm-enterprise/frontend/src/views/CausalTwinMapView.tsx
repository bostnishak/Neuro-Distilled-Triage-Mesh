import React, { useState, useEffect } from "react";
import { apiClient } from "../services/apiClient";
import {
  CascadeSimulationResponse,
  CounterfactualInterventionResponse,
  TopologyResponse,
} from "../types/api";

export const CausalTwinMapView: React.FC = () => {
  const [topology, setTopology] = useState<TopologyResponse | null>(null);
  const [selectedRoot, setSelectedRoot] = useState<string>("SUBSTATION_IKITELLI");
  const [intervenedNode, setIntervenedNode] = useState<string>("FIBER_BOGAZICI_NORTH");
  const [simulation, setSimulation] = useState<CascadeSimulationResponse | null>(null);
  const [counterfactual, setCounterfactual] = useState<CounterfactualInterventionResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    loadTopology();
  }, []);

  const loadTopology = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await apiClient.getCausalTopology();
      setTopology(res);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed loading infrastructure topology.");
    } finally {
      setLoading(false);
    }
  };

  const handleRunCascade = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await apiClient.simulateCascade({
        failed_node_code: selectedRoot,
        time_horizon_minutes: 60,
      });
      setSimulation(res);
    } catch (err: any) {
      setErrorMsg(err.message || "Cascade simulation failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleRunDoCalculus = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await apiClient.evaluateCounterfactual({
        failed_node_code: selectedRoot,
        intervened_node_code: intervenedNode,
        intervention_action: "REINFORCED",
      });
      setCounterfactual(res);
    } catch (err: any) {
      setErrorMsg(err.message || "Counterfactual intervention failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping"></span>
              <h2 className="text-lg font-bold text-white tracking-wide">
                Causal Digital Twin & Pearl's Do-Calculus (12-Node Topology)
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Topological Graph Structural Equation Model (SEM) across Istanbul Metro critical infrastructure.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              id="btn-refresh-topology"
              onClick={loadTopology}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-lg border border-slate-700 text-slate-300 transition"
            >
              Yenile
            </button>
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="p-3 bg-rose-950/60 border border-rose-800 text-rose-300 rounded-lg text-xs">
          {errorMsg}
        </div>
      )}

      {/* Control Panel & Graph Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Controls */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider border-b border-slate-800 pb-2">
            Nedensel Simülasyon Kontrolleri
          </h3>

          <div>
            <label className="text-xs text-slate-400 block mb-1">Kök Arıza Düğümü (Root Failure):</label>
            <select
              id="select-root-node"
              value={selectedRoot}
              onChange={(e) => setSelectedRoot(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
            >
              {topology?.nodes.map((n) => (
                <option key={n.node_code} value={n.node_code}>
                  {n.node_code} ({n.node_type})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs text-slate-400 block mb-1">Müdahale Düğümü (do(X = x)):</label>
            <select
              id="select-intervened-node"
              value={intervenedNode}
              onChange={(e) => setIntervenedNode(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
            >
              {topology?.nodes.map((n) => (
                <option key={n.node_code} value={n.node_code}>
                  {n.node_code} ({n.node_type})
                </option>
              ))}
            </select>
          </div>

          <div className="pt-2 flex flex-col gap-2">
            <button
              id="btn-run-cascade"
              onClick={handleRunCascade}
              disabled={loading}
              className="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold rounded-lg text-xs transition shadow-md disabled:opacity-50"
            >
              {loading ? "Hesaplanıyor..." : "1. Kaskat Arıza Simülasyonu Başlat"}
            </button>

            <button
              id="btn-run-do-calculus"
              onClick={handleRunDoCalculus}
              disabled={loading}
              className="w-full py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-semibold rounded-lg text-xs transition shadow-md disabled:opacity-50"
            >
              {loading ? "Hesaplanıyor..." : "2. Pearl Do-Calculus Müdahalesi Uygula"}
            </button>
          </div>
        </div>

        {/* 12-Node Topology Grid */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
              İstanbul Altyapı Düğümleri ({topology?.total_nodes || 12} Düğüm • {topology?.total_edges || 18} Bağımlılık)
            </h3>
            <span className="text-[11px] font-mono text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-800">
              PostGIS EPSG:4326
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5 max-h-[300px] overflow-y-auto pr-1">
            {topology?.nodes.map((node) => (
              <div
                key={node.node_code}
                className={`p-2.5 rounded-lg border text-xs transition ${
                  node.node_code === selectedRoot
                    ? "bg-rose-950/40 border-rose-500 text-rose-200"
                    : node.node_code === intervenedNode
                    ? "bg-purple-950/40 border-purple-500 text-purple-200"
                    : "bg-slate-950/60 border-slate-800 text-slate-300"
                }`}
              >
                <div className="font-semibold truncate">{node.node_code}</div>
                <div className="text-[10px] text-slate-400">{node.node_type}</div>
                <div className="mt-1 flex items-center justify-between text-[10px]">
                  <span>Sağlık:</span>
                  <span className="font-mono text-emerald-400">{node.current_health_score}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Simulation & Do-Calculus Results */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cascade Blast Radius Results */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <h3 className="text-sm font-semibold text-rose-300 uppercase tracking-wider">
              Kaskat Arıza Yayılımı (Blast-Radius)
            </h3>
            {simulation && (
              <span className="text-xs font-mono bg-rose-950/60 text-rose-300 px-2 py-0.5 rounded border border-rose-800">
                CRR: {simulation.cumulative_risk_rating}
              </span>
            )}
          </div>

          {simulation ? (
            <div className="space-y-3">
              <div className="text-xs text-slate-300">
                Kök Arıza: <span className="font-bold text-rose-400">{simulation.root_failed_node}</span> (Etkilenen: {simulation.affected_nodes_count} düğüm)
              </div>
              <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
                {simulation.cascade_timeline.map((item, idx) => (
                  <div key={idx} className="p-2 rounded bg-slate-950 border border-slate-800 text-xs flex items-center justify-between">
                    <div>
                      <span className="font-mono text-cyan-400">{item.node_code}</span>
                      <div className="text-[10px] text-slate-500 truncate max-w-[200px]">
                        Yol: {item.coupling_path.join(" ➔ ")}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono text-rose-400">P(Arıza): {(item.failure_probability * 100).toFixed(1)}%</div>
                      <div className="text-[10px] text-slate-400">+{item.time_to_fail_minutes} dk</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="py-12 text-center text-xs text-slate-500">
              Simülasyon sonucunu görmek için yukarıdaki butonu tıklayın.
            </div>
          )}
        </div>

        {/* Counterfactual Intervention Results */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <h3 className="text-sm font-semibold text-indigo-300 uppercase tracking-wider">
              Do-Calculus Müdahale Sonucu (G&#773;<sub>X</sub>)
            </h3>
            {counterfactual && (
              <span className={`text-xs font-mono px-2 py-0.5 rounded border ${
                counterfactual.is_risk_mitigated
                  ? "bg-emerald-950/60 text-emerald-300 border-emerald-800"
                  : "bg-slate-800 text-slate-300 border-slate-700"
              }`}>
                &Delta;CRR: {counterfactual.delta_crr}
              </span>
            )}
          </div>

          {counterfactual ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                  <div className="text-slate-400">Orijinal Risk (CRR):</div>
                  <div className="text-base font-mono font-bold text-rose-400 mt-1">
                    {counterfactual.original_risk_rating}
                  </div>
                </div>
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                  <div className="text-slate-400">Müdahale Sonrası Risk:</div>
                  <div className="text-base font-mono font-bold text-emerald-400 mt-1">
                    {counterfactual.counterfactual_risk_rating}
                  </div>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-800/40 text-xs text-emerald-300">
                &check; Müdahale do({intervenedNode} = REINFORCED) kaskat yayılım riskini net <strong>{counterfactual.delta_crr}</strong> puan azalttı.
              </div>

              <div>
                <span className="text-[11px] text-slate-400">Kesilen Gelen Kenarlar (Mutilated Edges):</span>
                <div className="mt-1 space-y-1">
                  {counterfactual.mutilated_edges_severed.map((e, idx) => (
                    <div key={idx} className="text-[10px] font-mono bg-slate-950 p-1.5 rounded border border-slate-800 text-slate-300">
                      &times; {e}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="py-12 text-center text-xs text-slate-500">
              Pearl Do-Calculus değerlendirmesini başlatmak için yukarıdaki butonu tıklayın.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
