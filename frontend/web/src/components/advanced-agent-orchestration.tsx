"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, Bot, CheckCircle, Loader2, Pause, Play, Plus, RefreshCw, Square, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { API_ENDPOINTS } from "@/config/api";
import { apiClient } from "@/lib/api-client";

interface AgentNode {
  agent_id: string;
  name: string;
  role: string;
  status: string;
  capabilities: string[];
  created_at: number;
}

interface AgentRole {
  description: string;
  capabilities: string[];
  default_model: string;
}

interface GraphSummary {
  total_agents: number;
  by_status: Record<string, number>;
  by_role: Record<string, number>;
  pending_messages: Record<string, number>;
  redis_connected: boolean;
}

interface AgentMessage {
  message_id: string;
  sender_id: string;
  receiver_id: string;
  message_type: string;
  content: Record<string, unknown>;
  created_at: number;
}

interface GraphStatusResponse {
  graph: GraphSummary;
}

function formatTimestamp(timestamp: number): string {
  const date = new Date(timestamp * 1000);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleString();
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The agent service request failed.";
}

export default function AdvancedAgentOrchestration() {
  const [agents, setAgents] = useState<AgentNode[]>([]);
  const [roles, setRoles] = useState<Record<string, AgentRole>>({});
  const [graph, setGraph] = useState<GraphSummary | null>(null);
  const [results, setResults] = useState<AgentMessage[]>([]);
  const [selectedRole, setSelectedRole] = useState("researcher");
  const [taskDescription, setTaskDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [busyAgentId, setBusyAgentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [statusData, agentData, roleData, resultData] = await Promise.all([
        apiClient.get<GraphStatusResponse>(API_ENDPOINTS.agents.graph.status),
        apiClient.get<{ agents: AgentNode[] }>(API_ENDPOINTS.agents.graph.agents),
        apiClient.get<{ roles: Record<string, AgentRole> }>(API_ENDPOINTS.agents.graph.roles),
        apiClient.get<{ messages: AgentMessage[] }>(API_ENDPOINTS.agents.graph.inboxMessages, {
          params: { limit: 50 },
        }),
      ]);
      setGraph(statusData.graph);
      setAgents(agentData.agents);
      setRoles(roleData.roles);
      setResults(resultData.messages);
      setSelectedRole((current) => current in roleData.roles ? current : Object.keys(roleData.roles)[0] ?? "");
      setError(null);
    } catch (loadError) {
      setError(getErrorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void loadData(), 0);
    const interval = window.setInterval(() => void loadData(), 5000);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(interval);
    };
  }, [loadData]);

  const activeCount = graph?.by_status.running ?? 0;
  const pendingMessages = useMemo(
    () => Object.values(graph?.pending_messages ?? {}).reduce((total, count) => total + count, 0),
    [graph],
  );

  const submitTask = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const task = taskDescription.trim();
    if (!task || !selectedRole) return;

    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const name = `${selectedRole[0].toUpperCase()}${selectedRole.slice(1)} task`;
      const created = await apiClient.post<{ agent_id: string }>(API_ENDPOINTS.agents.graph.spawn, {
        name,
        role: selectedRole,
        request: { task, query: task },
      });
      setTaskDescription("");
      setNotice(`Task submitted to ${selectedRole} agent ${created.agent_id}.`);
      await loadData();
    } catch (submitError) {
      setError(getErrorMessage(submitError));
    } finally {
      setBusy(false);
    }
  };

  const controlAgent = async (agent: AgentNode, action: "pause" | "resume" | "terminate") => {
    const endpoint = API_ENDPOINTS.agents.graph[action](agent.agent_id);
    setBusyAgentId(agent.agent_id);
    setError(null);
    setNotice(null);
    try {
      const response = await apiClient.post<{ success: boolean }>(endpoint);
      if (!response.success) {
        throw new Error(`Could not ${action} agent ${agent.name}. Its current state may not allow this action.`);
      }
      setNotice(`${agent.name} ${action === "terminate" ? "terminated" : `${action}d`}.`);
      await loadData();
    } catch (actionError) {
      setError(getErrorMessage(actionError));
    } finally {
      setBusyAgentId(null);
    }
  };

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Agent Orchestration</h1>
          <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
            {error ? (
              <>
                <AlertCircle className="h-4 w-4 text-destructive" />
                Offline - agents backend unavailable
              </>
            ) : (
              <>
                <CheckCircle className="h-4 w-4 text-emerald-500" />
                Connected to the JARVIS agent graph
              </>
            )}
          </p>
        </div>
        <Button variant="outline" onClick={() => void loadData()} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center justify-between gap-4 pt-6">
            <p className="text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={() => void loadData()}>Retry</Button>
          </CardContent>
        </Card>
      )}
      {notice && <p role="status" className="text-sm text-emerald-500">{notice}</p>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Agents in graph" value={graph?.total_agents ?? "—"} icon={<Users className="h-4 w-4" />} />
        <StatCard label="Running" value={activeCount} icon={<Bot className="h-4 w-4" />} />
        <StatCard label="Paused" value={graph?.by_status.paused ?? 0} icon={<Pause className="h-4 w-4" />} />
        <StatCard label="Pending messages" value={pendingMessages} icon={<AlertCircle className="h-4 w-4" />} />
      </div>

      {graph && !graph.redis_connected && (
        <p className="text-sm text-amber-500" role="status">
          The graph is using its in-memory fallback; agents and messages may not survive a backend restart.
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Submit a task</CardTitle>
            <CardDescription>
              JARVIS will start a role-specific worker and send its result to the orchestration inbox.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={submitTask}>
              <label className="block space-y-2 text-sm">
                <span>Agent role</span>
                <select
                  className="h-10 w-full rounded-md border border-input bg-background px-3"
                  value={selectedRole}
                  onChange={(event) => setSelectedRole(event.target.value)}
                  disabled={Object.keys(roles).length === 0}
                >
                  {Object.entries(roles).map(([role, details]) => (
                    <option key={role} value={role}>{role} — {details.description}</option>
                  ))}
                </select>
              </label>
              {selectedRole && roles[selectedRole] && (
                <p className="text-xs text-muted-foreground">
                  Capabilities: {roles[selectedRole].capabilities.join(", ")}
                </p>
              )}
              <Textarea
                aria-label="Task description"
                placeholder="Describe what the agent should do"
                value={taskDescription}
                onChange={(event) => setTaskDescription(event.target.value)}
                required
              />
              <Button type="submit" disabled={busy || loading || !taskDescription.trim() || !selectedRole}>
                {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                Submit task
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Agents</CardTitle>
            <CardDescription>Live graph state with pause, resume, and terminate controls.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {agents.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {loading ? "Loading agents…" : "No agents have been created yet."}
              </p>
            ) : agents.map((agent) => (
              <div key={agent.agent_id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{agent.name}</span>
                    <Badge variant="outline">{agent.status}</Badge>
                  </div>
                  <p className="truncate text-xs text-muted-foreground">{agent.role} · {agent.agent_id}</p>
                  {agent.capabilities.length > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">{agent.capabilities.join(", ")}</p>
                  )}
                </div>
                <div className="flex gap-2">
                  {agent.status === "paused" ? (
                    <Button
                      size="sm"
                      variant="outline"
                      aria-label={`Resume ${agent.name}`}
                      disabled={busyAgentId === agent.agent_id}
                      onClick={() => void controlAgent(agent, "resume")}
                    >
                      <Play className="h-4 w-4" />
                    </Button>
                  ) : !["terminated", "stopped", "error"].includes(agent.status) ? (
                    <Button
                      size="sm"
                      variant="outline"
                      aria-label={`Pause ${agent.name}`}
                      disabled={busyAgentId === agent.agent_id}
                      onClick={() => void controlAgent(agent, "pause")}
                    >
                      <Pause className="h-4 w-4" />
                    </Button>
                  ) : null}
                  {!["terminated", "stopped"].includes(agent.status) && (
                    <Button
                      size="sm"
                      variant="outline"
                      aria-label={`Terminate ${agent.name}`}
                      disabled={busyAgentId === agent.agent_id}
                      onClick={() => void controlAgent(agent, "terminate")}
                    >
                      <Square className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Agent result inbox</CardTitle>
          <CardDescription>Responses reported by workers are refreshed automatically.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {results.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {loading ? "Loading results…" : "No agent results have been reported yet."}
            </p>
          ) : results.map((message) => (
            <div key={message.message_id} className="rounded-lg border p-3">
              <div className="mb-2 flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
                <span>{message.message_type} · {message.sender_id}</span>
                <time>{formatTimestamp(message.created_at)}</time>
              </div>
              <pre className="overflow-x-auto whitespace-pre-wrap break-words text-sm">
                {JSON.stringify(message.content.result ?? message.content, null, 2)}
              </pre>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({ label, value, icon }: { label: string; value: number | string; icon: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between pt-6">
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-semibold">{value}</p>
        </div>
        <span className="text-primary">{icon}</span>
      </CardContent>
    </Card>
  );
}
