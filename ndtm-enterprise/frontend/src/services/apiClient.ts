import {
  CascadeSimulationResponse,
  ChaosResponse,
  CounterfactualInterventionResponse,
  DLQMessageItem,
  FederatedRoundExecuteResponse,
  FederatedStatusResponse,
  FieldTeamDTO,
  HITLApprovalItem,
  HITLSignResponse,
  IncidentSubmissionResponse,
  LiveMetricsSnapshot,
  LoRASwapResponse,
  MerkleBlockItem,
  MerkleVerifyResponse,
  RouterInferenceResponse,
  SpeculativeDecodeResponse,
  TopologyResponse,
  Z3SolveResponse,
} from "../types/api";

class ApiClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const url = endpoint.startsWith("/api/") ? endpoint : `/api/v1${endpoint}`;
    const res = await fetch(url, {
      ...options,
      headers,
    });

    if (!res.ok) {
      let errPayload: any;
      try {
        errPayload = await res.json();
      } catch {
        errPayload = { message: res.statusText };
      }
      throw { status: res.status, ...errPayload };
    }

    return res.json() as Promise<T>;
  }

  // Auth
  async login(email: string, password: string): Promise<any> {
    return this.request("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  }

  async register(email: string, password: string, role: string): Promise<any> {
    return this.request("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, role }),
    });
  }

  async refreshToken(refreshToken: string): Promise<any> {
    return this.request("/api/v1/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  }

  async getMe(): Promise<any> {
    return this.request("/api/v1/auth/me");
  }

  // Triage Gateway
  async submitIncident(payload: {
    description: string;
    category: string;
    latitude: number;
    longitude: number;
    urgency_score: number;
    image_base64?: string | null;
  }): Promise<IncidentSubmissionResponse> {
    return this.request<IncidentSubmissionResponse>("/api/v1/triage/submit", {
      method: "POST",
      headers: { "Idempotency-Key": `idemp-${Date.now()}` },
      body: JSON.stringify(payload),
    });
  }

  // DistillMesh Router
  async inferRouter(text: string): Promise<RouterInferenceResponse> {
    return this.request<RouterInferenceResponse>("/api/v1/router/infer", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  }

  async triggerRetrain(): Promise<any> {
    return this.request("/api/v1/router/retrain", {
      method: "POST",
    });
  }

  // Z3 Symbolic Scheduler
  async listTeams(): Promise<FieldTeamDTO[]> {
    return this.request<FieldTeamDTO[]>("/api/v1/scheduler/teams");
  }

  async solveZ3(payload: {
    incidents: any[];
    teams: FieldTeamDTO[];
    initial_proposal?: any[];
  }): Promise<Z3SolveResponse> {
    return this.request<Z3SolveResponse>("/api/v1/scheduler/solve", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  // System, Telemetry & SRE Chaos
  async fetchMetricsSnapshot(): Promise<LiveMetricsSnapshot> {
    return this.request<LiveMetricsSnapshot>("/api/v1/system/metrics-snapshot");
  }

  async getSystemHealth(): Promise<any> {
    return this.request("/api/v1/system/health");
  }

  async getDriftSamples(): Promise<any> {
    return this.request("/api/v1/router/drift-samples");
  }

  async triggerChaos(scenario: string): Promise<ChaosResponse> {
    return this.request<ChaosResponse>("/api/v1/system/chaos", {
      method: "POST",
      body: JSON.stringify({ scenario }),
    });
  }

  async listDLQ(): Promise<DLQMessageItem[]> {
    return this.request<DLQMessageItem[]>("/api/v1/system/dlq");
  }

  async replayDLQ(messageId: string): Promise<any> {
    return this.request(`/api/v1/system/dlq/${messageId}/replay`, {
      method: "POST",
    });
  }

  // ===========================================================================
  // V2 FRONTIER EXPANSION ENDPOINTS
  // ===========================================================================

  // Causal Digital Twin
  async getCausalTopology(): Promise<TopologyResponse> {
    return this.request<TopologyResponse>("/api/v2/causal/topology");
  }

  async simulateCascade(payload: {
    failed_node_code: string;
    time_horizon_minutes?: number;
  }): Promise<CascadeSimulationResponse> {
    return this.request<CascadeSimulationResponse>("/api/v2/causal/simulate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async evaluateCounterfactual(payload: {
    failed_node_code: string;
    intervened_node_code: string;
    intervention_action?: string;
  }): Promise<CounterfactualInterventionResponse> {
    return this.request<CounterfactualInterventionResponse>("/api/v2/causal/counterfactual", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  // MCP JSON-RPC & Byzantine HITL Consensus
  async callMcpRpc(payload: {
    method: string;
    params?: Record<string, any>;
    id: string | number;
  }): Promise<any> {
    return this.request("/api/v2/mcp/rpc", {
      method: "POST",
      body: JSON.stringify({ jsonrpc: "2.0", ...payload }),
    });
  }

  async listMcpTools(): Promise<any> {
    return this.request("/api/v2/mcp/tools");
  }

  async listPendingHITL(): Promise<HITLApprovalItem[]> {
    return this.request<HITLApprovalItem[]>("/api/v2/hitl/pending");
  }

  async signHITL(
    requestId: string,
    payload: {
      approver_email: string;
      public_key_hex: string;
      ed25519_signature_hex: string;
    }
  ): Promise<HITLSignResponse> {
    return this.request<HITLSignResponse>(`/api/v2/hitl/${requestId}/sign`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  // Federated Mesh Learning & Privacy
  async getFederatedStatus(): Promise<FederatedStatusResponse> {
    return this.request<FederatedStatusResponse>("/api/v2/federated/status");
  }

  async executeFederatedRound(): Promise<FederatedRoundExecuteResponse> {
    return this.request<FederatedRoundExecuteResponse>("/api/v2/federated/round/execute", {
      method: "POST",
    });
  }

  async submitEdgeGradient(payload: {
    edge_node_id: string;
    round_number: number;
    gradient_vector: number[];
  }): Promise<any> {
    return this.request("/api/v2/federated/submit", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  // Merkle State Ledger & Speculative Kernel
  async getMerkleLedgerChain(): Promise<MerkleBlockItem[]> {
    return this.request<MerkleBlockItem[]>("/api/v2/ledger/chain");
  }

  async verifyMerkleChain(): Promise<MerkleVerifyResponse> {
    return this.request<MerkleVerifyResponse>("/api/v2/ledger/verify", {
      method: "POST",
    });
  }

  async runSpeculativeDecode(payload: {
    prompt: string;
    max_tokens?: number;
    draft_lookahead_k?: number;
  }): Promise<SpeculativeDecodeResponse> {
    return this.request<SpeculativeDecodeResponse>("/api/v2/kernel/speculative", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async swapLoRAAdapter(adapterName: string): Promise<LoRASwapResponse> {
    return this.request<LoRASwapResponse>("/api/v2/kernel/lora/swap", {
      method: "POST",
      body: JSON.stringify({ adapter_name: adapterName }),
    });
  }

  async listLoRAAdapters(): Promise<{ active_adapter: string; available_adapters: string[] }> {
    return this.request<{ active_adapter: string; available_adapters: string[] }>(
      "/api/v2/kernel/adapters"
    );
  }
}

export const apiClient = new ApiClient();
