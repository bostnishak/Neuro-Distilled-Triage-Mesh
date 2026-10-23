import React, { useState, useEffect } from "react";
import { apiClient } from "../services/apiClient";
import {
  LoRASwapResponse,
  MerkleBlockItem,
  MerkleVerifyResponse,
  SpeculativeDecodeResponse,
} from "../types/api";

export const MerkleAndSpeculativeView: React.FC = () => {
  // Speculative state
  const [prompt, setPrompt] = useState<string>("Trafoda ani voltaj dalgalanması ve duman tespiti");
  const [specResult, setSpecResult] = useState<SpeculativeDecodeResponse | null>(null);
  const [specLoading, setSpecLoading] = useState<boolean>(false);

  // LoRA state
  const [activeAdapter, setActiveAdapter] = useState<string>("DEFAULT_MUNICIPAL");
  const [availableAdapters, setAvailableAdapters] = useState<string[]>([
    "DEFAULT_MUNICIPAL",
    "TELECOM_FIBER",
    "ENERGY_GRID",
    "WATER_COOLING",
  ]);
  const [selectedAdapter, setSelectedAdapter] = useState<string>("TELECOM_FIBER");
  const [swapResult, setSwapResult] = useState<LoRASwapResponse | null>(null);
  const [loraLoading, setLoraLoading] = useState<boolean>(false);

  // Merkle state
  const [blocks, setBlocks] = useState<MerkleBlockItem[]>([]);
  const [verifyResult, setVerifyResult] = useState<MerkleVerifyResponse | null>(null);
  const [merkleLoading, setMerkleLoading] = useState<boolean>(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  useEffect(() => {
    loadAdapters();
    loadMerkleBlocks();
  }, []);

  const loadAdapters = async () => {
    try {
      const res = await apiClient.listLoRAAdapters();
      setActiveAdapter(res.active_adapter);
      setAvailableAdapters(res.available_adapters);
    } catch {
      // Fallback
    }
  };

  const loadMerkleBlocks = async () => {
    try {
      const chain = await apiClient.getMerkleLedgerChain();
      setBlocks(chain);
    } catch (err: any) {
      setStatusMsg("Failed loading Merkle audit ledger.");
    }
  };

  const handleRunSpeculative = async () => {
    try {
      setSpecLoading(true);
      setStatusMsg(null);
      const res = await apiClient.runSpeculativeDecode({
        prompt,
        max_tokens: 32,
        draft_lookahead_k: 4,
      });
      setSpecResult(res);
    } catch (err: any) {
      setStatusMsg(err.message || "Speculative decoding failed.");
    } finally {
      setSpecLoading(false);
    }
  };

  const handleSwapLoRA = async () => {
    try {
      setLoraLoading(true);
      setStatusMsg(null);
      const res = await apiClient.swapLoRAAdapter(selectedAdapter);
      setSwapResult(res);
      setActiveAdapter(res.active_adapter);
      await loadMerkleBlocks();
    } catch (err: any) {
      setStatusMsg(err.message || "LoRA swap failed.");
    } finally {
      setLoraLoading(false);
    }
  };

  const handleVerifyMerkle = async () => {
    try {
      setMerkleLoading(true);
      setStatusMsg(null);
      const res = await apiClient.verifyMerkleChain();
      setVerifyResult(res);
    } catch (err: any) {
      setStatusMsg(err.message || "Merkle verification error.");
    } finally {
      setMerkleLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
              <h2 className="text-lg font-bold text-white tracking-wide">
                Speculative Inference Kernel & Cryptographic Merkle State Ledger
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Leviathan et al. Rejection Sampling, atomic LoRA hot-swapping, and SHA-256 tamper-evident chain verification.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-amber-400 bg-amber-950/60 px-2.5 py-1 rounded-lg border border-amber-800">
              Zero-Trust Audit Chain
            </span>
          </div>
        </div>
      </div>

      {statusMsg && (
        <div className="p-3 bg-rose-950/60 border border-rose-800 text-rose-300 rounded-lg text-xs">
          {statusMsg}
        </div>
      )}

      {/* Grid: Speculative Kernel & LoRA Hot-Swapper */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Speculative Decoding Panel */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <h3 className="text-sm font-semibold text-cyan-300 uppercase tracking-wider">
              1. Spekülatif Çıkarım Çekirdeği (Leviathan et al.)
            </h3>
            <span className="text-[10px] font-mono bg-cyan-950/60 text-cyan-400 border border-cyan-800 px-2 py-0.5 rounded">
              K=4 Taslak
            </span>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Giriş İhbar Metni (Prompt):</label>
              <textarea
                id="input-speculative-prompt"
                rows={2}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
              />
            </div>

            <button
              id="btn-run-speculative"
              onClick={handleRunSpeculative}
              disabled={specLoading}
              className="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold rounded-lg text-xs transition shadow-md disabled:opacity-50"
            >
              {specLoading ? "Çözümleniyor..." : "Spekülatif Çıkarım Çalıştır (Rejection Sampling)"}
            </button>

            {specResult && (
              <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-xs space-y-2">
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="p-2 bg-slate-900 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-400">Hızlanma (Speedup):</div>
                    <div className="text-sm font-bold font-mono text-emerald-400 mt-0.5">
                      {specResult.speedup_ratio}x
                    </div>
                  </div>
                  <div className="p-2 bg-slate-900 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-400">Kabul Oranı:</div>
                    <div className="text-sm font-bold font-mono text-cyan-400 mt-0.5">
                      {(specResult.acceptance_rate * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="p-2 bg-slate-900 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-400">Yeniden Örnekleme:</div>
                    <div className="text-sm font-bold font-mono text-amber-400 mt-0.5">
                      {specResult.resampled_count} Token
                    </div>
                  </div>
                </div>
                <div className="text-[11px] text-slate-300">
                  {specResult.generated_text}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Dynamic LoRA Hot-Swapper */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <h3 className="text-sm font-semibold text-amber-300 uppercase tracking-wider">
              2. Dinamik LoRA Adapter Hot-Swap
            </h3>
            <span className="text-[10px] font-mono bg-slate-800 text-slate-300 px-2 py-0.5 rounded">
              Aktif: {activeAdapter}
            </span>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Hedef LoRA Modülü Seçimi:</label>
              <select
                id="select-lora-adapter"
                value={selectedAdapter}
                onChange={(e) => setSelectedAdapter(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
              >
                {availableAdapters.map((adp) => (
                  <option key={adp} value={adp}>
                    {adp} {adp === activeAdapter ? "(Aktif)" : ""}
                  </option>
                ))}
              </select>
            </div>

            <button
              id="btn-swap-lora"
              onClick={handleSwapLoRA}
              disabled={loraLoading}
              className="w-full py-2.5 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white font-semibold rounded-lg text-xs transition shadow-md disabled:opacity-50"
            >
              {loraLoading ? "Değiştiriliyor..." : "LoRA Adaptörünü Sıfır Kesintiyle Değiştir (Hot-Swap)"}
            </button>

            {swapResult && (
              <div className="p-3 bg-emerald-950/40 border border-emerald-800 text-emerald-300 rounded-lg text-xs space-y-1">
                <div className="font-semibold">&check; Adaptör başarıyla değiştirildi!</div>
                <div className="text-[10px] font-mono text-slate-400">
                  {swapResult.previous_adapter} ➔ {swapResult.active_adapter}
                </div>
                <div className="text-[9px] font-mono text-slate-500 truncate">
                  SHA-256: {swapResult.adapter_checksum_sha256}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Section 3: Merkle State Audit Ledger */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-white uppercase tracking-wider">
              3. Kriptografik Merkle Denetim Zinciri ({blocks.length} Blok)
            </h3>
            {verifyResult && (
              <span
                className={`text-[11px] font-mono px-2 py-0.5 rounded border ${
                  verifyResult.valid
                    ? "bg-emerald-950/60 text-emerald-300 border-emerald-800"
                    : "bg-rose-950/60 text-rose-300 border-rose-800"
                }`}
              >
                {verifyResult.valid ? "&check; Zincir Doğrulandı" : "&cross; Tahrifat Saptandı!"}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              id="btn-verify-merkle"
              onClick={handleVerifyMerkle}
              disabled={merkleLoading}
              className="px-3 py-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold rounded-lg text-xs transition shadow-md disabled:opacity-50"
            >
              {merkleLoading ? "Doğrulanıyor..." : "Merkle Zincir Bütünlüğünü Doğrula"}
            </button>
          </div>
        </div>

        {/* Ledger Blocks Table */}
        <div className="overflow-x-auto max-h-[300px]">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-950 text-slate-400 border-b border-slate-800">
                <th className="p-2 font-semibold">Sıra (Seq)</th>
                <th className="p-2 font-semibold">Olay Tipi</th>
                <th className="p-2 font-semibold">Aktör</th>
                <th className="p-2 font-semibold">Blok Hash (SHA-256)</th>
                <th className="p-2 font-semibold">Merkle Kök Özeti</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
              {blocks.map((b) => (
                <tr key={b.seq_no} className="hover:bg-slate-850/50">
                  <td className="p-2 font-bold text-cyan-400">#{b.seq_no}</td>
                  <td className="p-2 font-sans font-semibold text-slate-200">{b.event_type}</td>
                  <td className="p-2 text-slate-400">{b.actor_id}</td>
                  <td className="p-2 text-slate-400 truncate max-w-[140px]">{b.block_hash.slice(0, 16)}...</td>
                  <td className="p-2 text-amber-400 truncate max-w-[140px]">{b.merkle_root_snapshot.slice(0, 16)}...</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
