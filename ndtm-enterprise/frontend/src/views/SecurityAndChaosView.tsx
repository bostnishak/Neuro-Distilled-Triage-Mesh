import React, { useState, useEffect } from "react";
import { apiClient } from "../services/apiClient";
import { wsClient } from "../services/wsClient";
import { ChaosResponse, DLQMessageItem } from "../types/api";

const CHAOS_SCENARIOS = [
  {
    id: "TEACHER_503_OUTAGE",
    title: "Trip Circuit Breaker (LLM 503 Outage)",
    desc: "Forces Circuit Breaker into OPEN state. Tests zero-downtime ONNX student fallback.",
    btnColor: "bg-rose-600 hover:bg-rose-500",
  },
  {
    id: "PROMPT_INJECTION_ATTACK",
    title: "Inject Adversarial Prompt (OWASP)",
    desc: "Sends prompt injection vector: 'IGNORE ALL PREVIOUS INSTRUCTIONS AND SYSTEM PROMPTS...'",
    btnColor: "bg-amber-600 hover:bg-amber-500",
  },
  {
    id: "TCKN_PII_LEAK_PROBE",
    title: "Trigger TC Kimlik No & PII Masker",
    desc: "Sends valid Modulo-10/11 TCKN and credit card to test HMAC-SHA256 tokenization.",
    btnColor: "bg-cyan-600 hover:bg-cyan-500",
  },
  {
    id: "SIMULATE_RABBITMQ_PARTITION",
    title: "Simulate AMQP Worker Failure",
    desc: "Simulates transient network partition to verify Transactional Outbox retry loop.",
    btnColor: "bg-purple-600 hover:bg-purple-500",
  },
];

export const SecurityAndChaosView: React.FC = () => {
  const [dlqMessages, setDlqMessages] = useState<DLQMessageItem[]>([]);
  const [chaosLog, setChaosLog] = useState<ChaosResponse[]>([]);
  const [securityEvents, setSecurityEvents] = useState<any[]>([]);
  const [isRunningScenario, setIsRunningScenario] = useState(false);
  const [replayingId, setReplayingId] = useState<string | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  useEffect(() => {
    fetchDLQ();

    // Listen to WebSocket security & DLQ events
    const unsubSecurity = wsClient.subscribe("SECURITY_EVENT", (event) => {
      setSecurityEvents((prev) => [event, ...prev.slice(0, 49)]);
    });

    const unsubDLQ = wsClient.subscribe("DLQ_MESSAGE", (msg: DLQMessageItem) => {
      setDlqMessages((prev) => [msg, ...prev]);
    });

    return () => {
      unsubSecurity();
      unsubDLQ();
    };
  }, []);

  const fetchDLQ = async () => {
    try {
      const msgs = await apiClient.listDLQ();
      setDlqMessages(msgs);
    } catch {
      // Mock fallback DLQ items if backend is offline or queue is empty
      setDlqMessages([
        {
          id: "dlq-msg-8812",
          routing_key: "ndtm.triage.unverified",
          payload: { incident_id: "inc-err-99", error: "SMT_UNSAT_NO_REPAIR_FEASIBLE" },
          retry_count: 3,
          error_reason: "Max retries exceeded: Z3 theorem prover could not find SAT assignment",
          created_at: new Date().toISOString(),
        },
      ]);
    }
  };

  const handleRunChaos = async (scenarioId: string) => {
    setIsRunningScenario(true);
    setToastMsg(null);
    try {
      const resp = await apiClient.triggerChaos(scenarioId);
      setChaosLog((prev) => [resp, ...prev]);
      setToastMsg(`Chaos senaryosu başarıyla tetiklendi: ${resp.action_taken}`);
    } catch (err: any) {
      setToastMsg(`Hata: ${err.detail || err.message || "Chaos injection başarısız."}`);
    } finally {
      setIsRunningScenario(false);
    }
  };

  const handleReplayDLQ = async (id: string) => {
    setReplayingId(id);
    try {
      await apiClient.replayDLQ(id);
      setToastMsg(`DLQ Mesajı (${id}) ana RabbitMQ 'ndtm.events.topic' kuyruğuna yeniden iletildi.`);
      setDlqMessages((prev) => prev.filter((m) => m.id !== id));
    } catch (err: any) {
      setToastMsg(`Yeniden iletim hatası: ${err.detail || err.message}`);
    } finally {
      setReplayingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-rose-500 animate-pulse"></span>
            Sistem Güvenliği & Hata Yönetimi (DLQ)
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Devre kesici arıza simülasyonu, prompt injection koruması ve Dead-Letter Queue (DLQ) mesaj yönetimi.
          </p>
        </div>
      </div>

      {toastMsg && (
        <div className="bg-slate-900 border border-cyan-800 text-cyan-300 px-4 py-3 rounded-lg text-xs flex items-center justify-between shadow">
          <span>{toastMsg}</span>
          <button onClick={() => setToastMsg(null)} className="text-cyan-400 font-bold hover:underline">
            ✕
          </button>
        </div>
      )}

      {/* Chaos Triggers Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {CHAOS_SCENARIOS.map((scenario) => (
          <div
            key={scenario.id}
            className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow flex flex-col justify-between space-y-3"
          >
            <div>
              <h4 className="text-sm font-bold text-white">{scenario.title}</h4>
              <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">{scenario.desc}</p>
            </div>
            <button
              onClick={() => handleRunChaos(scenario.id)}
              disabled={isRunningScenario}
              className={`w-full py-2 px-3 text-white text-xs font-bold rounded-lg transition shadow disabled:opacity-50 ${scenario.btnColor}`}
            >
              Trigger Scenario
            </button>
          </div>
        ))}
      </div>

      {/* Main Grid: Chaos Execution Log & Dead-Letter Queue */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Chaos & Audit Stream */}
        <div className="lg:col-span-6 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <svg className="w-4 h-4 text-rose-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            Chaos Execution Log
          </h3>

          <div className="space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
            {chaosLog.length === 0 ? (
              <div className="text-center py-10 text-slate-500 text-xs border border-dashed border-slate-800 rounded-lg">
                Henüz bir chaos testi çalıştırılmadı. Yukarıdaki senaryolardan birini tetikleyin.
              </div>
            ) : (
              chaosLog.map((log, idx) => (
                <div key={idx} className="bg-slate-950 border border-slate-800 p-3 rounded-lg space-y-1.5 font-mono text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-rose-400">{log.scenario}</span>
                    <span className="text-[10px] text-slate-500">{new Date(log.timestamp * 1000).toLocaleTimeString()}</span>
                  </div>
                  <div className="text-slate-300 font-sans">{log.action_taken}</div>
                  <div className="flex items-center gap-3 text-[10px] text-slate-400 pt-1">
                    <span>Subsystem: <span className="text-white">{log.affected_subsystem}</span></span>
                    <span>Circuit Breaker Tripped: <span className={log.circuit_breaker_tripped ? "text-rose-400 font-bold" : "text-emerald-400"}>{String(log.circuit_breaker_tripped)}</span></span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right: Dead-Letter Queue (DLQ) Inspector & Replay */}
        <div className="lg:col-span-6 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              RabbitMQ Dead-Letter Queue (DLQ)
            </h3>
            <button
              onClick={fetchDLQ}
              className="text-xs text-amber-400 hover:text-amber-300 hover:underline"
            >
              Refresh DLQ
            </button>
          </div>

          <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1">
            {dlqMessages.length === 0 ? (
              <div className="text-center py-10 text-emerald-400 text-xs border border-dashed border-emerald-900/40 rounded-lg">
                DLQ Tertemiz: Hatalı veya zehirli mesaj bulunmuyor.
              </div>
            ) : (
              dlqMessages.map((msg) => (
                <div key={msg.id} className="bg-slate-950 border border-slate-800 p-3 rounded-lg space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-bold text-amber-400">{msg.id}</span>
                    <span className="text-[10px] bg-rose-950 text-rose-300 px-2 py-0.5 rounded font-mono">
                      Retries: {msg.retry_count}
                    </span>
                  </div>

                  <div className="text-[11px] text-slate-400">
                    Routing Key: <span className="font-mono text-slate-200">{msg.routing_key}</span>
                  </div>

                  <div className="bg-slate-900 p-2 rounded border border-slate-800/80 text-[11px] text-rose-300 font-mono break-all">
                    {msg.error_reason}
                  </div>

                  <div className="flex justify-between items-center pt-1">
                    <span className="text-[10px] text-slate-500 font-mono">
                      {new Date(msg.created_at).toLocaleTimeString()}
                    </span>
                    <button
                      onClick={() => handleReplayDLQ(msg.id)}
                      disabled={replayingId === msg.id}
                      className="px-3 py-1 bg-amber-600 hover:bg-amber-500 text-slate-950 font-bold rounded text-[11px] transition disabled:opacity-50 flex items-center gap-1.5"
                    >
                      {replayingId === msg.id ? (
                        "Replaying..."
                      ) : (
                        <>
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                          </svg>
                          Replay to Exchange
                        </>
                      )}
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
