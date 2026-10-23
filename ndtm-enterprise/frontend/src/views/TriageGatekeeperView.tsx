import React, { useState } from "react";
import {
  ShieldAlert,
  Camera,
  MapPin,
  Send,
  Sparkles,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Lock,
} from "lucide-react";
import { apiClient } from "../services/apiClient";
import { IncidentSubmissionResponse } from "../types/api";

const PRESET_SCENARIOS = [
  {
    title: "⚡ Trafo Yangını & TCKN Test",
    text: "Tunalı Hilmi Caddesi No:45 önündeki elektrik trafosu patladı ve yangın çıktı. Vatandaş Ahmet Yılmaz (TC: 10000000146, Tel: 0532 987 6543) ekiplerin acil gelmesini istedi.",
    category: "TRANSFORMER_FIRE",
    lat: 39.9035,
    lon: 32.8369,
    urgency: 9,
  },
  {
    title: "💧 Ana Boru Patlağı (Kızılay)",
    text: "Atatürk Bulvarı üzerinde ana isale hattı patladı, cadde tamamen sular altında kaldı. Araçlar ilerleyemiyor.",
    category: "WATER_MAIN_BURST",
    lat: 39.9208,
    lon: 32.8543,
    urgency: 8,
  },
  {
    title: "⚠️ Çukur / Yol Çökmesi",
    text: "Eskişehir Yolu 5. kilometrede asfalt gövdesinde derin bir çökme meydana geldi. Kaza riski yüksek.",
    category: "ROAD_COLLAPSE",
    lat: 39.9123,
    lon: 32.8123,
    urgency: 7,
  },
];

export const TriageGatekeeperView: React.FC = () => {
  const [description, setDescription] = useState(PRESET_SCENARIOS[0].text);
  const [category, setCategory] = useState(PRESET_SCENARIOS[0].category);
  const [latitude, setLatitude] = useState(PRESET_SCENARIOS[0].lat);
  const [longitude, setLongitude] = useState(PRESET_SCENARIOS[0].lon);
  const [urgency, setUrgency] = useState(PRESET_SCENARIOS[0].urgency);
  const [imageBase64, setImageBase64] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<IncidentSubmissionResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<any | null>(null);

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setImageBase64(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    setErrorMsg(null);

    try {
      const res = await apiClient.submitIncident({
        description,
        category,
        latitude,
        longitude,
        urgency_score: urgency,
        image_base64: imageBase64,
      });
      setResult(res);
    } catch (err: any) {
      setErrorMsg(err.detail || err);
    } finally {
      setLoading(false);
    }
  };

  const loadScenario = (idx: number) => {
    const s = PRESET_SCENARIOS[idx];
    setDescription(s.text);
    setCategory(s.category);
    setLatitude(s.lat);
    setLongitude(s.lon);
    setUrgency(s.urgency);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
      {/* Input Formulation Panel */}
      <div className="lg:col-span-7 bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl">
        <div className="flex items-center justify-between pb-4 mb-6 border-b border-slate-800">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-cyan-400" />
              Yeni İhbar Girişi & Triaj Kontrolü
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              TCKN/Telefon maskeleme, fotoğraf netlik kontrolü ve 250m mükerrer tespiti
            </p>
          </div>
          <span className="px-2.5 py-1 text-xs font-mono font-medium rounded-full bg-cyan-950/60 text-cyan-400 border border-cyan-800/50">
            HNSW ef=64
          </span>
        </div>

        {/* Preset scenario shortcuts */}
        <div className="mb-4">
          <label className="text-xs font-semibold text-slate-300 block mb-2">
            Hızlı Test Senaryosu Seç:
          </label>
          <div className="flex flex-wrap gap-2">
            {PRESET_SCENARIOS.map((sc, i) => (
              <button
                key={i}
                type="button"
                onClick={() => loadScenario(i)}
                className="text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition"
              >
                {sc.title}
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={handleFormSubmit} className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-300 block mb-1">
              İhbar Açıklaması:
            </label>
            <textarea
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-sm text-slate-100 focus:border-cyan-500 focus:outline-none transition"
              placeholder="Olay yerini, tehlike durumunu ve vatandaş bildirimini yazın..."
              required
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className="text-xs font-mono uppercase text-gray-400 block mb-1">Category</label>
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full bg-mesh-900 border border-gray-700 rounded-lg p-2 text-xs font-mono text-gray-200"
              />
            </div>
            <div>
              <label className="text-xs font-mono uppercase text-gray-400 block mb-1">Urgency (1-10)</label>
              <input
                type="number"
                min={1}
                max={10}
                value={urgency}
                onChange={(e) => setUrgency(Number(e.target.value))}
                className="w-full bg-mesh-900 border border-gray-700 rounded-lg p-2 text-xs font-mono text-gray-200"
              />
            </div>
            <div>
              <label className="text-xs font-mono uppercase text-gray-400 block mb-1">Latitude</label>
              <input
                type="number"
                step="0.0001"
                value={latitude}
                onChange={(e) => setLatitude(Number(e.target.value))}
                className="w-full bg-mesh-900 border border-gray-700 rounded-lg p-2 text-xs font-mono text-gray-200"
              />
            </div>
            <div>
              <label className="text-xs font-mono uppercase text-gray-400 block mb-1">Longitude</label>
              <input
                type="number"
                step="0.0001"
                value={longitude}
                onChange={(e) => setLongitude(Number(e.target.value))}
                className="w-full bg-mesh-900 border border-gray-700 rounded-lg p-2 text-xs font-mono text-gray-200"
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-300 block mb-1">
              Olay Yeri Fotoğrafı (Opsiyonel):
            </label>
            <div className="flex items-center gap-3">
              <label className="cursor-pointer flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-200 transition">
                <Camera className="w-4 h-4 text-cyan-400" />
                Fotoğraf Seç
                <input type="file" accept="image/*" onChange={handleImageUpload} className="hidden" />
              </label>
              {imageBase64 && (
                <span className="text-xs text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Fotoğraf yüklendi (EXIF temizlenecek)
                </span>
              )}
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg font-bold text-sm bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white shadow-md flex items-center justify-center gap-2 transition disabled:opacity-50"
          >
            {loading ? "İhbar İşleniyor ve Kontrol Ediliyor..." : "İhbarı İncele ve Gönder"}
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>

      {/* Live Forensic Inspector Output */}
      <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between pb-3 mb-4 border-b border-slate-800">
            <h3 className="text-sm font-bold text-cyan-400 flex items-center gap-2">
              <Layers className="w-4 h-4" /> Triaj ve Ön Filtre Sonucu
            </h3>
            {result && (
              <span
                className={`text-xs px-2 py-0.5 rounded font-mono font-bold ${
                  result.is_duplicate ? "bg-amber-950 text-amber-400 border border-amber-800" : "bg-emerald-950 text-emerald-400 border border-emerald-800"
                }`}
              >
                {result.status}
              </span>
            )}
          </div>

          {errorMsg && (
            <div className="p-4 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-xs font-mono space-y-2 mb-4">
              <div className="flex items-center gap-2 font-bold text-rose-400">
                <AlertTriangle className="w-4 h-4" /> QUALITY GATE REJECTION:
              </div>
              <p>{errorMsg.clarification_prompt || errorMsg.message || JSON.stringify(errorMsg)}</p>
              {errorMsg.laplacian_score !== undefined && (
                <div className="text-[11px] text-gray-400">
                  Computed Sharpness Variance: <strong>{errorMsg.laplacian_score}</strong> (Min required: 85.0)
                </div>
              )}
            </div>
          )}

          {result ? (
            <div className="space-y-4">
              {/* Step 1: PII Scrubbing */}
              <div className="p-3 rounded-lg bg-mesh-900 border border-gray-800">
                <div className="flex items-center justify-between text-xs font-mono text-gray-400 mb-1">
                  <span className="flex items-center gap-1.5 text-cyan-300">
                    <Lock className="w-3.5 h-3.5" /> 1. Cryptographic PII Redaction:
                  </span>
                  <span className="text-emerald-400 font-bold">HMAC-SHA256 Masked</span>
                </div>
                <p className="text-xs font-mono text-gray-300 bg-black/40 p-2 rounded mt-1 break-words">
                  {result.scrubbed_text}
                </p>
              </div>

              {/* Step 2: Deduplication Verdict */}
              <div className="p-3 rounded-lg bg-mesh-900 border border-gray-800">
                <div className="flex items-center justify-between text-xs font-mono text-gray-400 mb-1">
                  <span className="flex items-center gap-1.5 text-cyan-300">
                    <MapPin className="w-3.5 h-3.5" /> 2. PostGIS + pgvector Matching:
                  </span>
                  <span className={result.is_duplicate ? "text-amber-400 font-bold" : "text-emerald-400 font-bold"}>
                    {result.is_duplicate ? "DUPLICATE MATCH" : "UNIQUE INCIDENT"}
                  </span>
                </div>
                {result.is_duplicate ? (
                  <div className="text-xs font-mono text-amber-200/90 space-y-1 mt-2">
                    <div>Parent Incident: <span className="text-white font-bold">{result.parent_incident_id}</span></div>
                    <div>Spatial Distance: <span className="text-white font-bold">{result.distance_meters}m</span> (Threshold: 250m)</div>
                    <div>Cosine Similarity: <span className="text-white font-bold">{(result.cosine_similarity! * 100).toFixed(2)}%</span> (Threshold: 86.0%)</div>
                    <div>Total Merged Reports: <span className="text-white font-bold">{result.duplicate_count}</span></div>
                  </div>
                ) : (
                  <div className="text-xs font-mono text-emerald-300/80 mt-2">
                    No duplicate cluster found within 250m radius. Atomically queued with Transactional Outbox.
                  </div>
                )}
              </div>

              {/* Step 3: Outbox Guarantee */}
              <div className="p-3 rounded-lg bg-mesh-900 border border-gray-800">
                <div className="text-xs font-mono text-gray-400">
                  <span className="text-cyan-300 font-bold">3. RabbitMQ Reliability:</span> Message committed to <code className="text-white">outbox_events</code>. Relay worker streaming with Publisher Confirms.
                </div>
              </div>
            </div>
          ) : (
            <div className="h-64 flex flex-col items-center justify-center text-center p-6 border border-dashed border-gray-800 rounded-lg">
              <Sparkles className="w-8 h-8 text-gray-600 mb-2" />
              <p className="text-xs text-gray-400 font-mono">
                Submit an incident report on the left to inspect live PII redaction and spatial deduplication.
              </p>
            </div>
          )}
        </div>

        <div className="pt-4 border-t border-gray-800 text-[11px] font-mono text-gray-500 flex justify-between">
          <span>GDPR / KVKK Modulo-11 Enforced</span>
          <span>Zero Plain PII on Disk</span>
        </div>
      </div>
    </div>
  );
};
