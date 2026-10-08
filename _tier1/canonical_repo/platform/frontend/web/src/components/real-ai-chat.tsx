"use client";

import React, { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import {
  Send,
  Bot,
  User,
  Loader2,
  Code,
  FileText,
  Zap,
  AlertCircle,
  CheckCircle,
  Square,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { getAuthToken } from "@/lib/api-client";
import { useChatStore } from "@/features/chat/store";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

const authHeaders = (json = false): Record<string, string> => {
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (json) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
};

const safeJson = async (response: Response): Promise<any | null> => {
  if (!response.ok) return null;
  const ct = response.headers.get("content-type") || "";
  if (!ct.includes("application/json")) return null;
  try {
    return await response.json();
  } catch {
    return null;
  }
};

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  model?: string;
  provider?: string;
  tokens_used?: number;
  sources?: { key?: string; value?: string }[];
  verification?: string;
  status?: SendLifecycle;
  partial?: boolean;
  retryable?: boolean;
  error?: string;
  clientMessageId?: string;
}

type SendLifecycle =
  | "IDLE"
  | "THINKING"
  | "STREAMING"
  | "COMPLETED"
  | "PROVIDER_UNAVAILABLE"
  | "OFFLINE"
  | "RATE_LIMITED"
  | "FAILED"
  | "STREAM_INTERRUPTED";

const CATEGORY_TO_LIFECYCLE: Record<string, SendLifecycle> = {
  RATE_LIMITED: "RATE_LIMITED",
  PROVIDER_UNAVAILABLE: "PROVIDER_UNAVAILABLE",
  STREAM_INTERRUPTED: "STREAM_INTERRUPTED",
  NETWORK_ERROR: "OFFLINE",
  TIMEOUT: "OFFLINE",
  INTERNAL_ERROR: "FAILED",
  UNKNOWN_ERROR: "FAILED",
  AUTHENTICATION_ERROR: "FAILED",
  AUTHORIZATION_ERROR: "FAILED",
  VALIDATION_ERROR: "FAILED",
  POLICY_ERROR: "FAILED",
  RESOURCE_EXHAUSTED: "RATE_LIMITED",
};

const LIFECYCLE_LABEL: Record<SendLifecycle, string> = {
  IDLE: "",
  THINKING: "Thinking",
  STREAMING: "Streaming",
  COMPLETED: "Completed",
  PROVIDER_UNAVAILABLE: "Provider unavailable",
  OFFLINE: "Offline",
  RATE_LIMITED: "Rate limited",
  FAILED: "Failed",
  STREAM_INTERRUPTED: "Interrupted",
};

const LIFECYCLE_CLASS: Record<SendLifecycle, string> = {
  IDLE: "",
  THINKING: "border-cyan-500/40 text-cyan-300",
  STREAMING: "border-cyan-500/40 text-cyan-300",
  COMPLETED: "border-green-500/40 text-green-400",
  PROVIDER_UNAVAILABLE: "border-amber-500/40 text-amber-400",
  OFFLINE: "border-red-500/40 text-red-400",
  RATE_LIMITED: "border-amber-500/40 text-amber-400",
  FAILED: "border-red-500/40 text-red-400",
  STREAM_INTERRUPTED: "border-yellow-500/40 text-yellow-400",
};

const newClientMessageId = (): string => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `cm-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

interface SilverwingStatus {
  configured: boolean;
  reachable: boolean;
  healthy: boolean;
  status: string;
  last_checked: string | null;
  errors: string | null;
  model: string;
}

interface SystemStatus {
  status: string;
  enabled?: boolean;
  provider?: string;
  ollama_model?: string;
  ollama_base_url?: string;
  silverwing_model?: string;
  silverwing_endpoint?: string | null;
  silverwing?: SilverwingStatus;
  brain_model?: string;
  brain_endpoint?: string | null;
  brain?: { configured: boolean; healthy: boolean };
  capabilities?: string[];
}

export default function RealAIChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [backendConnected, setBackendConnected] = useState(true);
  const [usingLocalFallback, setUsingLocalFallback] = useState(false);
  const [verifyMode, setVerifyMode] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sessionIdRef = useRef<string | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);
  const [activity, setActivity] = React.useState<string[]>([]);
  const retryRef = useRef<
    Map<string, { content: string; clientMessageId: string }>
  >(new Map());

  const {
    activeModel,
    modelCatalog,
    availableProviders,
    setActiveModel,
    loadModelCatalog,
  } = useChatStore();

  useEffect(() => {
    void loadModelCatalog();
    loadSystemStatus();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadSystemStatus = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/ai/status`, {
        headers: authHeaders(),
      });
      const data = await safeJson(response);
      if (!data) throw new Error("Backend unavailable");

      setSystemStatus({
        status: data.status === "ready" ? "online" : "offline",
        enabled: Boolean(data.enabled),
        provider: data.provider,
        ollama_model: data.ollama_model,
        ollama_base_url: data.ollama_base_url,
        silverwing_model: data.silverwing_model,
        silverwing_endpoint: data.silverwing_endpoint,
        silverwing: data.silverwing || {
          configured: false,
          reachable: false,
          healthy: false,
          status: "unreachable",
          last_checked: null,
          errors: "not configured",
          model: data.silverwing_model || "silverwing-120m-base-v1",
        },
        brain_model: data.brain_model,
        brain_endpoint: data.brain_endpoint,
        brain: data.brain || { configured: false, healthy: false },
        capabilities: data.capabilities || ["chat", "code generation", "analysis"],
      });
      setUsingLocalFallback(!data.enabled);
    } catch (error) {
      console.error("Failed to load system status:", error);
      setBackendConnected(false);
      setUsingLocalFallback(true);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const updateAssistant = (
    id: string,
    patch: Partial<ChatMessage>,
  ) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...patch } : m)),
    );
  };

  const stopStreaming = () => {
    abortRef.current?.abort();
  };

  const switchModel = async (providerModel: string) => {
    setActiveModel(providerModel);
    try {
      await fetch(`${API_BASE}/api/chat/switch`, {
        method: "POST",
        headers: authHeaders(true),
        body: JSON.stringify({ model: providerModel }),
      });
    } catch {
      // The next /api/chat/stream call still carries the selected model, so a
      // failed switch round-trip must not block the selection.
    }
  };

  const runStream = async (
    text: string,
    clientMessageId: string,
    assistantId: string,
  ) => {
    const controller = new AbortController();
    abortRef.current = controller;
    setIsLoading(true);

    let received = "";
    const patch = (extra: Partial<ChatMessage>) => {
      received = extra.content ?? received;
      updateAssistant(assistantId, { content: received, ...extra });
    };

    try {
      const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: authHeaders(true),
        signal: controller.signal,
        body: JSON.stringify({
          message: text,
          session_id: sessionIdRef.current ?? null,
          stream: true,
          model: activeModel,
          client_message_id: clientMessageId,
        }),
      });

      if (!response.ok || !response.body) {
        let category: string | undefined;
        let detail = `Request failed (HTTP ${response.status})`;
        try {
          const err = await response.json();
          category = err?.category;
          detail = err?.detail || err?.message || err?.error || detail;
        } catch {
          /* non-JSON error body */
        }
        throw Object.assign(new Error(detail), { category });
      }

      setBackendConnected(true);
      setUsingLocalFallback(false);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let boundary = buffer.indexOf("\n\n");
        while (boundary !== -1) {
          const frame = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          for (const line of frame.split("\n")) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data:")) continue;
            const raw = trimmed.slice(5).trim();
            if (!raw) continue;
            let event: any;
            try {
              event = JSON.parse(raw);
            } catch {
              continue;
            }

            switch (event.type) {
              case "typing":
                patch({ status: "THINKING" });
                break;
              case "meta":
                if (event.session_id) sessionIdRef.current = event.session_id;
                patch({ status: "THINKING" });
                break;
              case "reasoning":
                patch({ status: "THINKING" });
                break;
              case "activity":
                // Real backend tool activity (project inspection steps).
                // Rendered verbatim; no simulated progress.
                setActivity((prev) => [
                  ...prev,
                  `${event.stage ?? event.tool ?? "working"} (${
                    event.status ?? "running"
                  })`,
                ]);
                patch({ status: "THINKING" });
                break;
              case "chunk": {
                const delta = event.content ?? event.text ?? "";
                if (delta) patch({ content: received + delta, status: "STREAMING" });
                break;
              }
              case "complete":
                patch({
                  content: event.content || received,
                  status: "COMPLETED",
                  provider: event.provider,
                  model: event.model,
                  tokens_used:
                    event.usage?.completion_tokens ?? event.usage?.output_tokens,
                  partial: false,
                  retryable: false,
                });
                retryRef.current.delete(assistantId);
                break;
              case "error": {
                const category = event.category ?? "UNKNOWN_ERROR";
                const lifecycle =
                  CATEGORY_TO_LIFECYCLE[category] ?? "FAILED";
                patch({
                  status: lifecycle,
                  error: event.message || event.error || "Request failed",
                  retryable:
                    event.retryable !== undefined
                      ? Boolean(event.retryable)
                      : lifecycle !== "FAILED",
                  partial: received.length > 0,
                });
                break;
              }
              default:
                break;
            }
          }
          boundary = buffer.indexOf("\n\n");
        }
      }
    } catch (error: any) {
      const aborted = error?.name === "AbortError";
      const lifecycle: SendLifecycle = aborted
        ? "STREAM_INTERRUPTED"
        : CATEGORY_TO_LIFECYCLE[error?.category] ??
          (navigator.onLine === false || error instanceof TypeError
            ? "OFFLINE"
            : "FAILED");
      patch({
        status: lifecycle,
        error: aborted
          ? "Stopped by you."
          : error?.message || "The request could not be completed.",
        retryable: true,
        partial: received.length > 0,
      });
      if (lifecycle === "OFFLINE") setBackendConnected(false);
    } finally {
      abortRef.current = null;
      setIsLoading(false);
    }
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    const clientMessageId = newClientMessageId();
    const assistantId = `assistant-${clientMessageId}`;

    setMessages((prev) => [
      ...prev,
      {
        id: `user-${clientMessageId}`,
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
      },
      {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
        status: "THINKING",
        clientMessageId,
      },
    ]);
    retryRef.current.set(assistantId, { content: text, clientMessageId });
    setInput("");
    setActivity([]);
    await runStream(text, clientMessageId, assistantId);
  };

  const retryMessage = (assistantId: string) => {
    const pending = retryRef.current.get(assistantId);
    if (!pending || isLoading) return;
    setMessages((prev) => prev.filter((m) => m.id !== assistantId));
    void runStream(pending.content, pending.clientMessageId, assistantId);
  };

  const generateCode = async (prompt: string, language: string = "python") => {
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/codegen/generate`, {
        method: "POST",
        headers: authHeaders(true),
        body: JSON.stringify({
          description: prompt,
          language,
          model: activeModel,
        }),
      });

      const data = await safeJson(response);

      if (data && data.code) {
        const assistantMessage: ChatMessage = {
          id: Date.now().toString(),
          role: "assistant",
          content: `**Generated ${language} code:**\n\n\`\`\`${language}\n${data.code}\n\`\`\``,
          timestamp: new Date().toISOString(),
          model: data.model,
          tokens_used: data.tokens_used,
        };

        setMessages((prev) => [...prev, assistantMessage]);
      } else {
        throw new Error(data?.error || "Failed to generate code");
      }
    } catch (error) {
      console.error("Code generation error:", error);

      const errorMessage: ChatMessage = {
        id: Date.now().toString(),
        role: "assistant",
        content: `Sorry, code generation failed: ${error instanceof Error ? error.message : "Unknown error"}`,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const analyzeText = async (text: string, analysisType: string = "sentiment") => {
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/ai/process`, {
        method: "POST",
        headers: authHeaders(true),
        body: JSON.stringify({
          message: `Analyze the following text (${analysisType} analysis):\n\n${text}`,
          model: activeModel,
        }),
      });

      const data = await safeJson(response);

      if (data && data.response) {
        const assistantMessage: ChatMessage = {
          id: Date.now().toString(),
          role: "assistant",
          content: `**Text Analysis (${analysisType}):**\n\n${data.response}`,
          timestamp: new Date().toISOString(),
          model: data.model,
          tokens_used: data.tokens_used,
        };

        setMessages((prev) => [...prev, assistantMessage]);
      } else {
        throw new Error(data?.error || "Failed to analyze text");
      }
    } catch (error) {
      console.error("Text analysis error:", error);

      const errorMessage: ChatMessage = {
        id: Date.now().toString(),
        role: "assistant",
        content: `Sorry, text analysis failed: ${error instanceof Error ? error.message : "Unknown error"}`,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const testCapabilities = async () => {
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/ai/status`, {
        method: "GET",
        headers: authHeaders(),
      });

      const data = await safeJson(response);

      if (data) {
        const capabilities = ["chat", "code generation", "text analysis", "voice"];
        const results = capabilities
          .map(
            (capability) =>
              `- ${capability}: ${data.status === "ready" ? "available" : "degraded"}`
          )
          .join("\n");

        const assistantMessage: ChatMessage = {
          id: Date.now().toString(),
          role: "assistant",
          content: `**System Capabilities Test Results:**\n\n${results}\n\nProvider: ${data.provider || "auto"}\nModel: ${data.ollama_model || data.silverwing_model || "auto"}\nAI Enabled: ${Boolean(data.enabled)}`,
          timestamp: new Date().toISOString(),
        };

        setMessages((prev) => [...prev, assistantMessage]);
      } else {
        throw new Error("Failed to test capabilities");
      }
    } catch (error) {
      console.error("Capabilities test error:", error);

      const errorMessage: ChatMessage = {
        id: Date.now().toString(),
        role: "assistant",
        content: `Sorry, capabilities test failed: ${error instanceof Error ? error.message : "Unknown error"}`,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const selectedProviderEntry = modelCatalog?.providers.find((p) => p.model === activeModel) || null;
  const modelOptionsForSelected = selectedProviderEntry?.models ?? [];

  const handleProviderChange = (providerModel: string) => {
    void switchModel(providerModel);
  };

  return (
    <div className="p-6 space-y-6 font-mono text-sm text-[#90ff90] bg-[#0a0a0f]">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-cyan-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
            Real AI Chat
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            {usingLocalFallback ? (
              <span className="text-yellow-400 flex items-center gap-2">
                <AlertCircle className="w-4 h-4" />
                Offline â no AI provider configured
              </span>
            ) : (
              <span className="text-green-400 flex items-center gap-2">
                <CheckCircle className="w-4 h-4" />
                Backend Connected
              </span>
            )}
          </p>
        </div>

        <div className="flex items-center space-x-4">
          {systemStatus && (
            <div className="flex items-center space-x-2">
              <div
                className={`w-2 h-2 rounded-full ${
                  systemStatus.status === "online"
                    ? "bg-green-400"
                    : "bg-red-400"
                }`}
              />
              <span className="text-sm">
                {availableProviders.length} providers available
              </span>
            </div>
          )}
        </div>
      </motion.div>

      {systemStatus && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
        >
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-400">
                System Status
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="text-center">
                  <div className="text-2xl font-bold text-white">
                    {availableProviders.length}
                  </div>
                  <div className="text-xs text-gray-400">Providers Live</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-white">
                    {(systemStatus.capabilities ?? []).length}
                  </div>
                  <div className="text-xs text-gray-400">Capabilities</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-white">
                    {messages.length}
                  </div>
                  <div className="text-xs text-gray-400">Messages</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-white">
                    {messages.reduce(
                      (sum, msg) => sum + (msg.tokens_used || 0),
                      0
                    )}
                  </div>
                  <div className="text-xs text-gray-400">Tokens Used</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-3">
          <Card className="bg-white/[0.02] border-white/5 h-[600px] flex flex-col">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2">
                <Bot className="h-5 w-5 text-cyan-400" />
                JARVIS AI Conversation
              </CardTitle>
              <CardDescription>
                Real AI model responses with actual inference
              </CardDescription>
            </CardHeader>

            <CardContent className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground/40">
                  <Bot className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-semibold mb-2">
                    Start a conversation
                  </h3>
                  <p className="text-sm">
                    Ask JARVIS anything using real AI models
                  </p>
                </div>
              ) : (
                messages.map((message) => (
                  <motion.div
                    key={message.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`flex gap-3 ${
                      message.role === "user"
                        ? "justify-end"
                        : "justify-start"
                    }`}
                  >
                    {message.role === "assistant" && (
                      <div className="w-8 h-8 rounded-lg bg-cyan-500/20 flex items-center justify-center">
                        <Bot className="w-4 h-4 text-cyan-400" />
                      </div>
                    )}

                    <div
                      className={`max-w-[80%] p-3 rounded-lg ${
                        message.role === "user"
                          ? "bg-blue-500/20 text-blue-100"
                          : "bg-white/[0.05] text-white"
                      }`}
                    >
                      {message.role === "assistant" && message.status && (
                        <div className="mb-1.5 flex flex-wrap items-center gap-2">
                          <Badge
                            variant="outline"
                            className={`text-[10px] ${
                              LIFECYCLE_CLASS[message.status]
                            }`}
                          >
                            {(message.status === "THINKING" ||
                              message.status === "STREAMING") && (
                              <Loader2 className="mr-1 inline h-2.5 w-2.5 animate-spin" />
                            )}
                            {LIFECYCLE_LABEL[message.status]}
                          </Badge>
                          {message.partial && (
                            <span className="text-[10px] text-yellow-400/80">
                              partial output
                            </span>
                          )}
                          {message.retryable &&
                            message.status !== "COMPLETED" &&
                            message.status !== "THINKING" &&
                            message.status !== "STREAMING" && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => retryMessage(message.id)}
                                disabled={isLoading}
                                className="h-6 px-2 text-[10px]"
                              >
                                Retry
                              </Button>
                            )}
                        </div>
                      )}
                      {message.role === "assistant" && message.error && (
                        <div className="mb-1.5 text-[11px] text-red-300/90">
                          {message.error}
                        </div>
                      )}
                      <div className="whitespace-pre-wrap text-sm">
                        {message.content ||
                          (message.role === "assistant" &&
                          (message.status === "THINKING" ||
                            message.status === "STREAMING") ? (
                            <span className="text-gray-400">
                              {message.status === "THINKING"
                                ? "Thinking…"
                                : "Waiting for first token…"}
                            </span>
                          ) : null)}
                      </div>

                      {message.verification && (
                        <div className="mt-2">
                          <Badge
                            variant="outline"
                            className={`text-[10px] ${
                              message.verification === "verified"
                                ? "border-green-500/40 text-green-400"
                                : "border-yellow-500/40 text-yellow-400"
                            }`}
                          >
                            {message.verification === "verified"
                              ? "Verified"
                              : "Unverified"}
                          </Badge>
                        </div>
                      )}
                      {(message.sources ?? []).length > 0 && (
                        <div className="mt-1.5 space-y-1">
                          {(message.sources ?? []).map((s) => (
                            <div key={s.key} className="text-[11px] text-gray-400">
                              <span className="text-cyan-400">[
                                {s.key}
                              ]</span>{" "}
                              {(s.value ?? "").slice(0, 140)}
                            </div>
                          ))}
                        </div>
                      )}

                      <div className="flex items-center justify-between mt-2 text-xs text-gray-400">
                        <span>
                          {new Date(message.timestamp).toLocaleTimeString()}
                        </span>
                        <span className="flex items-center gap-3">
                          {message.provider && (
                            <span>Provider: {message.provider}</span>
                          )}
                          {message.model && <span>Model: {message.model}</span>}
                          {message.tokens_used ? (
                            <span>Tokens: {message.tokens_used}</span>
                          ) : null}
                        </span>
                      </div>
                    </div>

                    {message.role === "user" && (
                      <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center">
                        <User className="w-4 h-4 text-blue-400" />
                      </div>
                    )}
                  </motion.div>
                ))
              )}

              {activity.length > 0 && (
                <div className="text-[11px] text-cyan-300/80 space-y-0.5 border-l-2 border-cyan-500/30 pl-2">
                  {activity.map((a, i) => (
                    <div key={`${a}-${i}`}>{a}</div>
                  ))}
                </div>
              )}

              <div ref={messagesEndRef} />
            </CardContent>

            <div className="p-4 border-t border-white/5">
              <div className="flex gap-2">
                <Textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Ask JARVIS anything..."
                  className="flex-1 bg-white/[0.05] border-white/10 text-white placeholder:text-gray-400"
                  rows={2}
                />
                {isLoading ? (
                  <Button
                    onClick={stopStreaming}
                    variant="outline"
                    className="border-red-500/40 text-red-300 hover:bg-red-500/10"
                    title="Stop streaming"
                  >
                    <Square className="w-4 h-4" />
                  </Button>
                ) : null}
                <Button
                  onClick={sendMessage}
                  disabled={!input.trim() || isLoading}
                  className="bg-cyan-500 hover:bg-cyan-600"
                >
                  {isLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                </Button>
              </div>
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          {/* Provider Selection */}
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-400">
                Provider / Model
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {modelCatalog ? (
                <>
                  <Select
                    value={activeModel}
                    onValueChange={handleProviderChange}
                    disabled={isLoading}
                  >
                    <SelectTrigger className="bg-white/[0.05] border-white/10">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">Auto Select (JARVIS routing)</SelectItem>
                      {modelCatalog.providers
                        .filter((p) => p.available)
                        .map((p) => (
                          <SelectItem
                            key={p.provider}
                            value={`${p.provider}:${p.model}`}
                          >
                            <span className="flex items-center justify-between w-full">
                              <span>{p.provider}</span>
                              <Badge
                                variant={
                                  p.authorized ? "default" : "outline"
                                }
                                className="ml-2 text-xs"
                              >
                                {p.authorized ? "ready" : "auth needed"}
                              </Badge>
                            </span>
                          </SelectItem>
                        ))}
                      {modelCatalog.providers
                        .filter((p) => !p.available)
                        .map((p) => (
                          <SelectItem
                            key={p.provider}
                            value={`${p.provider}:${p.model}`}
                            disabled
                          >
                            <span className="flex items-center justify-between w-full opacity-50">
                              <span>{p.provider} (unavailable)</span>
                              <Badge variant="outline" className="ml-2 text-xs">
                                inactive
                              </Badge>
                            </span>
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>

                  {selectedProviderEntry &&
                    modelOptionsForSelected.length > 1 && (
                      <Select
                        value={activeModel.split(":").slice(1).join(":") || ""}
                        onValueChange={(m) =>
                          setActiveModel(`${selectedProviderEntry.provider}:${m}`)
                        }
                        disabled={isLoading}
                      >
                        <SelectTrigger className="bg-white/[0.05] border-white/10">
                          <SelectValue placeholder="Model variant" />
                        </SelectTrigger>
                        <SelectContent>
                          {modelOptionsForSelected.map((m) => (
                            <SelectItem
                              key={m}
                              value={`${selectedProviderEntry.provider}:${m}`}
                            >
                              {m}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}

                  <div className="flex items-center justify-between">
                    <span
                      className="text-xs text-gray-400"
                      title="Ground answers in retrieved knowledge and verify arithmetic with the calculator before responding"
                    >
                      Verified answers
                    </span>
                    <Switch
                      checked={verifyMode}
                      onCheckedChange={setVerifyMode}
                    />
                  </div>
                </>
              ) : (
                <div className="text-xs text-gray-400 flex items-center gap-2">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Loading provider catalog...
                </div>
              )}
            </CardContent>
          </Card>

          {/* Quick Actions */}
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-400">
                Quick Actions
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button
                variant="outline"
                size="sm"
                className="w-full justify-start"
                onClick={() =>
                  generateCode(
                    "Create a simple REST API with authentication",
                    "python"
                  )
                }
                disabled={isLoading || usingLocalFallback}
              >
                <Code className="w-4 h-4 mr-2" />
                Generate Python Code
              </Button>

              <Button
                variant="outline"
                size="sm"
                className="w-full justify-start"
                onClick={() =>
                  analyzeText(
                    "I love using JARVIS AI! It's amazing and helps me so much.",
                    "sentiment"
                  )
                }
                disabled={isLoading || usingLocalFallback}
              >
                <FileText className="w-4 h-4 mr-2" />
                Analyze Sentiment
              </Button>

              <Button
                variant="outline"
                size="sm"
                className="w-full justify-start"
                onClick={testCapabilities}
                disabled={isLoading}
              >
                <Zap className="w-4 h-4 mr-2" />
                Test Capabilities
              </Button>
            </CardContent>
          </Card>

          {/* Available Models */}
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-gray-400">
                Available Models
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {modelCatalog ? (
                modelCatalog.providers.map((model) => (
                  <div
                    key={model.provider}
                    className="flex items-center justify-between p-2 rounded bg-white/[0.02]"
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className={`w-2 h-2 rounded-full ${
                          model.available ? "bg-green-400" : "bg-red-400"
                        }`}
                      />
                      <span className="text-sm">
                        {model.provider}
                        <span className="text-gray-500">
                          {" "}
                          · {model.model}
                        </span>
                      </span>
                    </div>
                    <Badge variant="outline" className="text-xs">
                      {model.authorized ? "ready" : "auth needed"}
                    </Badge>
                  </div>
                ))
              ) : (
                <div className="text-xs text-gray-400 flex items-center gap-2">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Loading...
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
