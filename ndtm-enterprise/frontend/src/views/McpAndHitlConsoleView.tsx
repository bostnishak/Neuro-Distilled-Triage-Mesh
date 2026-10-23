import React, { useState, useEffect } from "react";
import { apiClient } from "../services/apiClient";
import { HITLApprovalItem, HITLSignResponse } from "../types/api";

export const McpAndHitlConsoleView: React.FC = () => {
  const [mcpTool, setMcpTool] = useState<string>("query_infra_telemetry");
  const [nodeCode, setNodeCode] = useState<string>("SUBSTATION_IKITELLI");
  const [mcpResult, setMcpResult] = useState<any>(null);
  const [mcpLoading, setMcpLoading] = useState<boolean>(false);

  // HITL state
  const [pendingRequests, setPendingRequests] = useState<HITLApprovalItem[]>([]);
  const [selectedRequest, setSelectedRequest] = useState<string>("");
  const [approverEmail, setApproverEmail] = useState<string>("auditor@ndtm-enterprise.local");
  const [publicKeyHex, setPublicKeyHex] = useState<string>(
    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
  );
  const [signatureHex, setSignatureHex] = useState<string>(
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
  );
  const [signResponse, setSignResponse] = useState<HITLSignResponse | null>(null);
  const [hitlLoading, setHitlLoading] = useState<boolean>(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  useEffect(() => {
    loadPending();
  }, []);

  const loadPending = async () => {
    try {
      const list = await apiClient.listPendingHITL();
      setPendingRequests(list);
      if (list.length > 0 && !selectedRequest) {
        setSelectedRequest(list[0].id);
      }
    } catch (err: any) {
      setStatusMsg("Failed loading pending HITL actions.");
    }
  };

  const handleExecuteMcpTool = async () => {
    try {
      setMcpLoading(true);
      setStatusMsg(null);
      let args: Record<string, any> = {};
      if (mcpTool === "query_infra_telemetry") {
        args = { node_code: nodeCode };
      } else if (mcpTool === "execute_counterfactual") {
        args = { failed_node_code: nodeCode, intervened_node_code: "FIBER_BOGAZICI_NORTH" };
      } else {
        args = { incident_id: "demo-task", risk_tier: "HIGH" };
      }

      const res = await apiClient.callMcpRpc({
        method: "tools/call",
        params: { name: mcpTool, arguments: args },
        id: `rpc-${Date.now()}`,
      });
      setMcpResult(res);
    } catch (err: any) {
      setMcpResult({ error: err.message || "MCP invocation failed" });
    } finally {
      setMcpLoading(false);
    }
  };

  const handleSignHitl = async () => {
    if (!selectedRequest) return;
    try {
      setHitlLoading(true);
      setStatusMsg(null);
      const res = await apiClient.signHITL(selectedRequest, {
        approver_email: approverEmail,
        public_key_hex: publicKeyHex,
        ed25519_signature_hex: signatureHex,
      });
      setSignResponse(res);
      await loadPending();
    } catch (err: any) {
      setStatusMsg(err.detail || err.message || "HITL cryptographic signing rejected.");
    } finally {
      setHitlLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
              <h2 className="text-lg font-bold text-white tracking-wide">
                Model Context Protocol (MCP) & Byzantine HITL Crypto-Gate
              </h2>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Sandboxed JSON-RPC 2.0 tool execution and Ed25519 asymmetric cryptographic signing for high-risk operations.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-emerald-400 bg-emerald-950/60 px-2.5 py-1 rounded-lg border border-emerald-800">
              Ed25519 Non-Repudiation Lock
            </span>
          </div>
        </div>
      </div>

      {statusMsg && (
        <div className="p-3 bg-rose-950/60 border border-rose-800 text-rose-300 rounded-lg text-xs">
          {statusMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Section 1: MCP Tool Calling Console */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <h3 className="text-sm font-semibold text-cyan-300 uppercase tracking-wider">
              1. Model Context Protocol (MCP) Konsolu
            </h3>
            <span className="text-[10px] font-mono bg-slate-800 text-slate-300 px-2 py-0.5 rounded">
              JSON-RPC 2.0
            </span>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Araç Seçimi (Tool Selection):</label>
              <select
                id="select-mcp-tool"
                value={mcpTool}
                onChange={(e) => setMcpTool(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
              >
                <option value="query_infra_telemetry">query_infra_telemetry (Altyapı Telemetrisi Sorgula)</option>
                <option value="execute_counterfactual">execute_counterfactual (Do-Calculus Müdahale)</option>
                <option value="propose_contingency_plan">propose_contingency_plan (Acil Durum Planı Üret)</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-slate-400 block mb-1">Hedef Düğüm / Parametre:</label>
              <input
                id="input-mcp-node"
                type="text"
                value={nodeCode}
                onChange={(e) => setNodeCode(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 font-mono focus:outline-none focus:border-cyan-500"
              />
            </div>

            <button
              id="btn-execute-mcp-tool"
              onClick={handleExecuteMcpTool}
              disabled={mcpLoading}
              className="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold rounded-lg text-xs transition shadow-md disabled:opacity-50"
            >
              {mcpLoading ? "Çalıştırılıyor..." : "MCP Aracını Çağır (Execute Tool)"}
            </button>

            {mcpResult && (
              <div className="mt-3">
                <span className="text-[11px] text-slate-400">JSON-RPC Yanıtı:</span>
                <pre className="mt-1 p-3 bg-slate-950 border border-slate-800 rounded-lg text-[11px] font-mono text-cyan-300 overflow-x-auto max-h-[220px]">
                  {JSON.stringify(mcpResult, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>

        {/* Section 2: Byzantine HITL Cryptographic Approval */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <h3 className="text-sm font-semibold text-emerald-300 uppercase tracking-wider">
              2. Byzantine HITL Kriptografik İmza Kapısı
            </h3>
            <span className="text-[10px] font-mono bg-emerald-950/60 text-emerald-400 border border-emerald-800 px-2 py-0.5 rounded">
              Ed25519
            </span>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Onay Bekleyen Yüksek Riskli Eylem:</label>
              <select
                id="select-hitl-request"
                value={selectedRequest}
                onChange={(e) => setSelectedRequest(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              >
                {pendingRequests.map((req) => (
                  <option key={req.id} value={req.id}>
                    {req.id.slice(0, 8)}... - Skor: {(req.agent_consensus_score * 100).toFixed(0)}% ({req.status})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs text-slate-400 block mb-1">Onaylayan Denetçi E-Postası:</label>
              <input
                id="input-approver-email"
                type="email"
                value={approverEmail}
                onChange={(e) => setApproverEmail(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div>
              <label className="text-xs text-slate-400 block mb-1">Ed25519 Açık Anahtar (32-Byte Hex):</label>
              <input
                id="input-public-key"
                type="text"
                value={publicKeyHex}
                onChange={(e) => setPublicKeyHex(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-[10px] font-mono text-slate-300 focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div>
              <label className="text-xs text-slate-400 block mb-1">Ed25519 Dijital İmza (64-Byte Hex):</label>
              <textarea
                id="input-ed25519-signature"
                rows={2}
                value={signatureHex}
                onChange={(e) => setSignatureHex(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-[10px] font-mono text-slate-300 focus:outline-none focus:border-emerald-500"
              />
            </div>

            <button
              id="btn-sign-hitl"
              onClick={handleSignHitl}
              disabled={hitlLoading || !selectedRequest}
              className="w-full py-2.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold rounded-lg text-xs transition shadow-md disabled:opacity-50"
            >
              {hitlLoading ? "Doğrulanıyor..." : "Ed25519 ile İmzala & Görevi Onayla"}
            </button>

            {signResponse && (
              <div className="p-3 bg-emerald-950/40 border border-emerald-800 text-emerald-300 rounded-lg text-xs space-y-1">
                <div className="font-semibold">&check; {signResponse.message}</div>
                <div className="text-[10px] font-mono text-slate-400">Durum: {signResponse.status} • Doğrulandı: {String(signResponse.verified)}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
