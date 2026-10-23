import React, { useState, useEffect } from "react";
import { apiClient } from "../services/apiClient";
import { FederatedRoundExecuteResponse, FederatedStatusResponse } from "../types/api";

export const FederatedPrivacyView: React.FC = () => {
  const [fedStatus, setFedStatus] = useState<FederatedStatusResponse | null>(null);
  const [roundResult, setRoundResult] = useState<FederatedRoundExecuteResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      const res = await apiClient.getFederatedStatus();
      setFedStatus(res);
    } catch (err: any) {
      setStatusMsg("Failed loading federated status.");
    }
  };

  const handleInjectByzantineGradient = async () => {
    try {
      setLoading(true);
      setStatusMsg(null);
      // Malicious poisoned gradient vector
      const poisonedVector = new Array(384).fill(-2.5);
      await apiClient.submitEdgeGradient({
        edge_node_id: "EDGE_NODE_06_POISON",
        round_number: fedStatus?.current_round || 1,
        gradient_vector: poisonedVector,
      });
      setStatusMsg("Zehirli Byzantine Gradyan Vektörü (EDGE_NODE_06_POISON) ağa enjekte edildi.");
      await loadStatus();
    } catch (err: any) {
      setStatusMsg(err.message || "Gradyan enjeksiyonu başarısız.");
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteRound = async () => {
    try {
      setLoading(true);
      setStatusMsg(null);
      const res = await apiClient.executeFederatedRound();
      setRoundResult(res);
      await loadStatus();
    } catch (err: any) {
      setStatusMsg(err.detail || err.message || "Federasyon turu çalıştırılamadı.");
    } finally {
      setLoading(false);
    }
  };

  const epsilonPercent = Math.min(
    100,
    Math.round(((fedStatus?.total_epsilon_spent || 0) / (fedStatus?.max_epsilon_budget || 10.0)) * 100)
  );

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-violet-400"></span>
              <h2 className="text-lg font-bold text-white tracking-wide">
                Byzantine-Resilient Federated Mesh & (&epsilon;, &delta;)-Differential Privacy
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Multi-Krum geometric outlier isolation with Gaussian perturbation and cumulative epsilon budget tracking.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-violet-400 bg-violet-950/60 px-2.5 py-1 rounded-lg border border-violet-800">
              Multi-Krum Aggregator
            </span>
          </div>
        </div>
      </div>

      {statusMsg && (
        <div className="p-3 bg-slate-950 border border-slate-800 text-slate-300 rounded-lg text-xs">
          {statusMsg}
        </div>
      )}

      {/* DP Metrics & Progress */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
          <div className="text-xs text-slate-400">Aktif Tur (Round):</div>
          <div className="text-2xl font-mono font-bold text-white mt-1">
            #{fedStatus?.current_round || 1}
          </div>
        </div>

        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
          <div className="text-xs text-slate-400">Harcanan &epsilon; (Epsilon):</div>
          <div className="text-2xl font-mono font-bold text-violet-400 mt-1">
            {fedStatus?.total_epsilon_spent || 0.0} / {fedStatus?.max_epsilon_budget || 10.0}
          </div>
          <div className="w-full bg-slate-800 rounded-full h-1.5 mt-2">
            <div
              className="bg-violet-500 h-1.5 rounded-full transition-all"
              style={{ width: `${epsilonPercent}%` }}
            ></div>
          </div>
        </div>

        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
          <div className="text-xs text-slate-400">&delta; (Delta Parametresi):</div>
          <div className="text-2xl font-mono font-bold text-slate-200 mt-1">
            1 &times; 10<sup>-5</sup>
          </div>
        </div>

        <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl">
          <div className="text-xs text-slate-400">Katılımcı Uç Düğümler:</div>
          <div className="text-2xl font-mono font-bold text-emerald-400 mt-1">
            {fedStatus?.participating_nodes.length || 6} Düğüm
          </div>
        </div>
      </div>

      {/* Control Buttons & Aggregation Result */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider border-b border-slate-800 pb-2">
            Federasyon Kontrolleri
          </h3>

          <div className="flex flex-col gap-3">
            <button
              id="btn-inject-byzantine"
              onClick={handleInjectByzantineGradient}
              disabled={loading}
              className="w-full py-2.5 bg-rose-950/80 hover:bg-rose-900 text-rose-200 border border-rose-700 font-semibold rounded-lg text-xs transition shadow-md disabled:opacity-50"
            >
              &times; Zehirli Gradyan Enjekte Et (Inject Byzantine Poison)
            </button>

            <button
              id="btn-execute-fed-round"
              onClick={handleExecuteRound}
              disabled={loading}
              className="w-full py-2.5 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-semibold rounded-lg text-xs transition shadow-md disabled:opacity-50"
            >
              {loading ? "Birleştiriliyor..." : "&check; Multi-Krum Turunu Başlat (Execute Round)"}
            </button>
          </div>

          <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-xs space-y-1">
            <span className="text-slate-400">Son Global Ağırlık Özeti:</span>
            <div className="font-mono text-[10px] text-cyan-400 truncate">
              {fedStatus?.last_round_sha256 || "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
            </div>
          </div>
        </div>

        {/* Aggregation Telemetry */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <h3 className="text-sm font-semibold text-violet-300 uppercase tracking-wider">
              Multi-Krum Agregasyon Telemetrisi
            </h3>
            {roundResult && (
              <span className="text-xs font-mono bg-violet-950/60 text-violet-300 px-2 py-0.5 rounded border border-violet-800">
                Tur #{roundResult.round_number}
              </span>
            )}
          </div>

          {roundResult ? (
            <div className="space-y-3 text-xs">
              <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-slate-400">Katılan Uç Düğüm:</span>
                  <span className="font-mono text-white">{roundResult.participating_nodes_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Reddedilen Byzantine Düğüm:</span>
                  <span className="font-mono text-rose-400 font-bold">{roundResult.rejected_byzantine_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Turda Harcanan &epsilon;:</span>
                  <span className="font-mono text-violet-400">{roundResult.epsilon_spent}</span>
                </div>
              </div>

              {roundResult.rejected_node_ids.length > 0 && (
                <div className="p-3 bg-rose-950/30 border border-rose-800/50 rounded-lg text-rose-300 space-y-1">
                  <div className="font-semibold">&cross; Karantinaya Alınan Düğümler:</div>
                  <ul className="list-disc list-inside font-mono text-[11px]">
                    {roundResult.rejected_node_ids.map((id) => (
                      <li key={id}>{id} (Krum Geometrik Sapması)</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="py-12 text-center text-xs text-slate-500">
              Multi-Krum agregasyon sonuçlarını görmek için yukarıdaki butonu tıklayın.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
