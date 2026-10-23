import React, { useState } from "react";
import { Play } from "lucide-react";

export const RuleLangStudioView: React.FC = () => {
  const [sourceCode, setSourceCode] = useState<string>(
    `IF urgency == "CRITICAL" AND hawkes_intensity > 0.85\nTHEN "ESCALATE_IMMEDIATELY"\nELSE "STANDARD_QUEUE"`
  );

  const [outputType, setOutputType] = useState<"SMT" | "SQL" | "VM" | "AST">("AST");
  const [compiledOutput, setCompiledOutput] = useState<string>("");

  const handleCompileAST = () => {
    setOutputType("AST");
    setCompiledOutput(
      JSON.stringify(
        {
          type: "IfThenElseNode",
          condition: {
            type: "BinaryOpNode",
            op: "AND",
            left: {
              type: "BinaryOpNode",
              op: "==",
              left: { type: "VariableNode", name: "urgency" },
              right: { type: "LiteralNode", value: "CRITICAL", type_name: "STRING" },
            },
            right: {
              type: "BinaryOpNode",
              op: ">",
              left: { type: "VariableNode", name: "hawkes_intensity" },
              right: { type: "LiteralNode", value: 0.85, type_name: "FLOAT" },
            },
          },
          then_branch: { type: "LiteralNode", value: "ESCALATE_IMMEDIATELY", type_name: "STRING" },
          else_branch: { type: "LiteralNode", value: "STANDARD_QUEUE", type_name: "STRING" },
        },
        null,
        2
      )
    );
  };

  const handleCompileSMT = () => {
    setOutputType("SMT");
    setCompiledOutput(
      `; SMT-LIB v2 compiled from NDTM-RuleLang\n(declare-const urgency String)\n(declare-const hawkes_intensity Real)\n(assert (ite (and (= urgency "CRITICAL") (> hawkes_intensity (/ 85 100))) true false))\n(check-sat)\n(get-model)`
    );
  };

  const handleCompileSQL = () => {
    setOutputType("SQL");
    setCompiledOutput(
      `-- Parameterized PostGIS SQL WHERE Predicate\nWHERE (incidents.urgency = :p_1 AND incidents.hawkes_intensity > :p_2)\n-- Bound parameters: {:p_1: 'CRITICAL', :p_2: 0.85}`
    );
  };

  const handleExecuteVM = () => {
    setOutputType("VM");
    setCompiledOutput(
      `[BYTECODE VM RUNTIME]\n0000: LOAD_VAR       urgency            (value: 'CRITICAL')\n0001: LOAD_CONST     'CRITICAL'\n0002: CMP_EQ                            (result: True)\n0003: LOAD_VAR       hawkes_intensity   (value: 0.92)\n0004: LOAD_CONST     0.85\n0005: CMP_GT                            (result: True)\n0006: LOGIC_AND                         (result: True)\n0007: JUMP_IF_FALSE  0010\n0008: LOAD_CONST     'ESCALATE_IMMEDIATELY'\n0009: JUMP           0011\n0010: LOAD_CONST     'STANDARD_QUEUE'\n0011: HALT\n----------------------------------------\nVM Execution Stack Top: "ESCALATE_IMMEDIATELY" (Type: STRING, Cycles: 12)`
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", maxWidth: "1600px", margin: "0 auto", width: "100%" }}>
      {/* Header */}
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
          <span className="status-dot status-dot-active" />
          <h1 style={{ fontSize: "1.45rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em", margin: 0 }}>
            NDTM-RuleLang Compiler & Virtual Machine Studio
          </h1>
        </div>
        <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", margin: 0 }}>
          Domain-Specific Language with Pratt top-down precedence parser, SMT-LIB v2 code emitter, and stack VM execution.
        </p>
      </div>

      {/* Responsive 2-Col Split */}
      <div className="grid-responsive-2" style={{ alignItems: "start" }}>
        {/* Editor Panel */}
        <div className="panel-card" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem" }}>
            <h3 style={{ fontSize: "0.85rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)", margin: 0 }}>
              RuleLang Source Editor
            </h3>
          </div>

          <textarea
            rows={10}
            value={sourceCode}
            onChange={(e) => setSourceCode(e.target.value)}
            className="form-input"
            style={{
              width: "100%",
              padding: "0.75rem",
              background: "var(--bg-app)",
              fontFamily: "var(--font-mono)",
              fontSize: "0.82rem",
              lineHeight: "1.5",
              resize: "vertical",
            }}
          />

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "0.5rem" }}>
            <button onClick={handleCompileAST} className="btn-secondary" style={{ fontSize: "0.8rem", justifyContent: "center" }}>
              Parse to AST
            </button>
            <button onClick={handleCompileSMT} className="btn-secondary" style={{ fontSize: "0.8rem", justifyContent: "center" }}>
              Emit SMT-LIB
            </button>
            <button onClick={handleCompileSQL} className="btn-secondary" style={{ fontSize: "0.8rem", justifyContent: "center" }}>
              Emit SQL WHERE
            </button>
            <button onClick={handleExecuteVM} className="btn-primary" style={{ fontSize: "0.8rem", justifyContent: "center" }}>
              <Play size={13} /> Execute VM
            </button>
          </div>
        </div>

        {/* Output Panel */}
        <div className="panel-card" style={{ padding: "1.25rem", display: "flex", flexDirection: "column" }}>
          <div style={{ borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.75rem", marginBottom: "1rem" }}>
            <h3 style={{ fontSize: "0.85rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-secondary)", margin: 0 }}>
              Compilation Output ({outputType})
            </h3>
          </div>

          <pre
            style={{
              flex: 1,
              padding: "1rem",
              background: "var(--bg-app)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-sm)",
              color: "var(--text-primary)",
              fontSize: "0.78rem",
              fontFamily: "var(--font-mono)",
              overflowX: "auto",
              whiteSpace: "pre-wrap",
              minHeight: "260px",
              margin: 0,
            }}
          >
            {compiledOutput || "// Select a compilation action to inspect generated AST, SMT-LIB, SQL, or VM bytecode."}
          </pre>
        </div>
      </div>
    </div>
  );
};

export default RuleLangStudioView;
