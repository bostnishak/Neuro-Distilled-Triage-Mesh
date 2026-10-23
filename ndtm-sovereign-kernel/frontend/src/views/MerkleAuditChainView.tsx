import React, { useState, useEffect } from "react";
import { api, MerkleBlock } from "../services/api.ts";
import { RefreshCw, ShieldCheck } from "lucide-react";

export const MerkleAuditChainView: React.FC = () => {
  const [blocks, setBlocks] = useState<MerkleBlock[]>([]);
  const [loading, setLoading] = useState(false);
  const [verificationResult, setVerificationResult] = useState<any>(null);

  const fetchBlocks = async () => {
    try {
      setLoading(true);
      const data = await api.listBlocks();
      setBlocks(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBlocks();
  }, []);

  const handleVerifyChain = async () => {
    try {
      setLoading(true);
      const res = await api.verifyMerkleChain();
      setVerificationResult(res);
    } catch (e: any) {
      setVerificationResult({ verified: false, error: e.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: "1600px", margin: "0 auto", width: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
            <span className="status-dot status-dot-active" />
            <h1 style={{ fontSize: "1.45rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em", margin: 0 }}>
              Cryptographic Merkle Audit Ledger
            </h1>
          </div>
          <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", margin: 0 }}>
            Immutable append-only ledger with SHA-256 binary tree proofs and kernel Ed25519 signature verification.
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
          <button onClick={fetchBlocks} className="btn-secondary" disabled={loading} style={{ fontSize: "0.82rem" }}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Sync Chain
          </button>
          <button onClick={handleVerifyChain} className="btn-primary" disabled={loading} style={{ fontSize: "0.82rem" }}>
            <ShieldCheck size={14} />
            Verify Chain Integrity
          </button>
        </div>
      </div>

      {verificationResult && (
        <div
          style={{
            padding: "1rem 1.25rem",
            background: verificationResult.verified ? "rgba(5, 150, 105, 0.08)" : "rgba(220, 38, 38, 0.08)",
            border: `1px solid ${verificationResult.verified ? "rgba(5, 150, 105, 0.3)" : "rgba(220, 38, 38, 0.3)"}`,
            borderRadius: "var(--radius-sm)",
          }}
        >
          <div style={{ fontWeight: 700, color: verificationResult.verified ? "var(--color-success)" : "var(--color-danger)", fontSize: "0.9rem" }}>
            {verificationResult.status || (verificationResult.verified ? "Chain Cryptographically Verified" : "Verification Failed")}
          </div>
          <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "0.2rem" }}>
            {verificationResult.verified
              ? `All ${verificationResult.total_blocks_verified} blocks verified with zero hash pointer tampering and valid Ed25519 signatures.`
              : `Tamper detected at block height ${verificationResult.violated_at_height}: ${verificationResult.error}`}
          </div>
        </div>
      )}

      {/* Block Stream */}
      <div className="panel-card" style={{ padding: "1.25rem" }}>
        <div style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem", marginBottom: "1rem" }}>
          <h3 style={{ fontSize: "0.85rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)", margin: 0 }}>
            Sealed Audit Block Chain ({blocks.length} Blocks)
          </h3>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {blocks.map((b) => (
            <div
              key={b.height}
              className="panel-elevated"
              style={{
                padding: "1rem 1.25rem",
                borderRadius: "var(--radius-sm)",
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span style={{ fontSize: "0.92rem", fontWeight: 700, color: "var(--brand-primary)", fontFamily: "var(--font-mono)" }}>
                    Block #{b.height}
                  </span>
                  {b.height === 0 && <span className="badge-solid badge-low" style={{ fontSize: "0.65rem" }}>Genesis</span>}
                  <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                    {b.events_count} Events Sealed
                  </span>
                </div>

                <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}>
                  {new Date(b.sealed_at).toLocaleString()}
                </span>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "0.6rem", fontSize: "0.78rem" }}>
                <div>
                  <span style={{ color: "var(--text-tertiary)" }}>Block Hash: </span>
                  <code style={{ color: "var(--color-success)", fontFamily: "var(--font-mono)" }}>{b.block_hash.slice(0, 24)}...</code>
                </div>

                <div>
                  <span style={{ color: "var(--text-tertiary)" }}>Parent Hash: </span>
                  <code style={{ color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>{b.parent_hash.slice(0, 24)}...</code>
                </div>

                <div>
                  <span style={{ color: "var(--text-tertiary)" }}>Merkle Root: </span>
                  <code style={{ color: "var(--brand-primary)", fontFamily: "var(--font-mono)" }}>{b.merkle_root.slice(0, 24)}...</code>
                </div>

                <div>
                  <span style={{ color: "var(--text-tertiary)" }}>Kernel Sig: </span>
                  <code style={{ color: "var(--color-warning)", fontFamily: "var(--font-mono)" }}>{b.kernel_signature_hex.slice(0, 24)}...</code>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default MerkleAuditChainView;
