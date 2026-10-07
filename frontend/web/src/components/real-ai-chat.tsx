"use client";

import React, { useState, useEffect, useRef } from "react";
import { useDropzone } from "react-dropzone";
import { motion, AnimatePresence } from "framer-motion";
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
  Paperclip,
  X as XIcon,
  FileText as FileTextIcon,
  MessageSquare,
  GitBranch,
  Copy,
  Mic,
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
import { getApiUrl } from "@/lib/runtime-url";
import { useChatStore } from "@/features/chat/store";
import { MarkdownMessage } from "@/components/chat/markdown-message";
import { ToolCallList } from "@/components/chat/tool-call-card";
import ConversationHistorySidebar from "@/components/conversation-sidebar";
import ModelSelector from "@/components/model-selector";
import ChatSettingsPanel from "@/components/chat-settings-panel";
import type { ToolCall } from "@/features/chat/types";

const authHeaders = (json = false): Record<string, string> => {
  return json ? { "Content-Type": "application/json" } : {};
};

const sessionFetch = (input: RequestInfo | URL, init: RequestInit = {}) =>
  fetch(input, { ...init, credentials: "include" });

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
  /**
   * Backend capabilities invoked while producing this turn, in call order.
   *
   * Populated from `activity` frames during streaming and from `tool_calls` on
   * completion, so the transcript shows *what the agent did* rather than only
   * what it said.
   */
  toolCalls?: ToolCall[];
  files?: Array<{
    name: string;
    url: string;
    type: string;
    size: number;
  }>;
}

type SendLifecycle =
  | "IDLE"
  | "CONNECTING"
  | "THINKING"
  | "STREAMING"
  | "TOOL_EXECUTION"
  | "COMPLETED"
  | "PROVIDER_UNAVAILABLE"
  | "OFFLINE"
  | "RATE_LIMITED"
  | "NETWORK_ERROR"
  | "AUTH_REQUIRED"
  | "FAILED"
  | "STREAM_INTERRUPTED";

// ---------------------------------------------------------------------------
// Tool-call normalisation
//
// The stream reports activity with free-form `status` strings, while the shared
// ToolCall type uses a closed set. Mapping here keeps the renderer total: an
// unrecognised status degrades to "running" rather than being dropped.
// ---------------------------------------------------------------------------

function normaliseToolStatus(status: unknown): ToolCall["status"] {
  switch (String(status ?? "").toLowerCase()) {
    case "complete":
    case "completed":
    case "success":
    case "succeeded":
    case "done":
    case "ok":
      return "completed";
    case "failed":
    case "failure":
    case "error":
    case "errored":
      return "failed";
    case "pending":
    case "queued":
    case "scheduled":
      return "pending";
    default:
      return "running";
  }
}

/** Coerce an arbitrary payload from the stream into a ToolCall. */
function toToolCall(raw: any): ToolCall {
  const args = raw?.arguments ?? raw?.args ?? raw?.input ?? raw?.parameters ?? {};
  return {
    id: raw?.id,
    index: Number.isInteger(raw?.index) ? raw.index : undefined,
    name: String(raw?.name ?? raw?.tool ?? raw?.stage ?? "capability"),
    // Argument bags arrive as JSON strings on some paths and as objects on
    // others; the renderer expects an object.
    arguments:
      typeof args === "string"
        ? safeParseObject(args)
        : (args && typeof args === "object" ? args : {}),
    result: raw?.result ?? raw?.output ?? raw?.content,
    status: normaliseToolStatus(raw?.status),
  };
}

function safeParseObject(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" ? parsed : { value: parsed };
  } catch {
    return { value };
  }
}

/**
 * Append a tool call, or update the existing entry with the same name.
 *
 * The backend reports start and finish as separate frames keyed only by tool
 * name, so merging by name is what turns two frames into one coherent call
 * rather than two duplicated rows.
 */
function mergeToolCall(
  existing: ToolCall[],
  incoming: ToolCall
): ToolCall[] {
  const index = existing.findIndex((call) =>
    incoming.index !== undefined
      ? call.index === incoming.index
      : incoming.id
        ? call.id === incoming.id
        : call.name === incoming.name
  );
  if (index === -1) return [...existing, incoming];

  const merged = [...existing];
  merged[index] = {
    ...merged[index],
    ...incoming,
    arguments: Object.keys(incoming.arguments ?? {}).length
      ? incoming.arguments
      : merged[index].arguments,
  };
  return merged;
}

/** Mark every still-open call as completed, for use at end of stream. */
function settleToolCalls(calls: ToolCall[]): ToolCall[] {
  return calls.map((call) =>
    call.status === "pending" || call.status === "running"
      ? { ...call, status: "completed" }
      : call
  );
}

const CATEGORY_TO_LIFECYCLE: Record<string, SendLifecycle> = {
  RATE_LIMITED: "RATE_LIMITED",
  PROVIDER_UNAVAILABLE: "PROVIDER_UNAVAILABLE",
  STREAM_INTERRUPTED: "STREAM_INTERRUPTED",
  NETWORK_ERROR: "NETWORK_ERROR",
  TIMEOUT: "OFFLINE",
  INTERNAL_ERROR: "FAILED",
  UNKNOWN_ERROR: "FAILED",
  AUTHENTICATION_ERROR: "AUTH_REQUIRED",
  AUTHORIZATION_ERROR: "AUTH_REQUIRED",
  VALIDATION_ERROR: "FAILED",
  POLICY_ERROR: "FAILED",
  RESOURCE_EXHAUSTED: "RATE_LIMITED",
};

const LIFECYCLE_LABEL: Record<SendLifecycle, string> = {
  IDLE: "",
  CONNECTING: "Connecting",
  THINKING: "Thinking",
  STREAMING: "Streaming",
  TOOL_EXECUTION: "Using tool",
  COMPLETED: "Completed",
  PROVIDER_UNAVAILABLE: "Provider unavailable",
  OFFLINE: "Offline",
  RATE_LIMITED: "Rate limited",
  NETWORK_ERROR: "Network error",
  AUTH_REQUIRED: "Authentication required",
  FAILED: "Failed",
  STREAM_INTERRUPTED: "Interrupted",
};

const LIFECYCLE_CLASS: Record<SendLifecycle, string> = {
  IDLE: "",
  CONNECTING: "border-blue-500/40 text-blue-300 animate-pulse",
  THINKING: "border-cyan-500/40 text-cyan-300",
  STREAMING: "border-cyan-500/40 text-cyan-300",
  TOOL_EXECUTION: "border-purple-500/40 text-purple-300",
  COMPLETED: "border-green-500/40 text-green-400",
  PROVIDER_UNAVAILABLE: "border-amber-500/40 text-amber-400",
  OFFLINE: "border-red-500/40 text-red-400",
  RATE_LIMITED: "border-amber-500/40 text-amber-400",
  NETWORK_ERROR: "border-red-500/40 text-red-400",
  AUTH_REQUIRED: "border-yellow-500/40 text-yellow-400",
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
  configured_provider_count?: number;
  provider_available?: boolean;
  ollama_model?: string;
  ollama_base_url?: string;
  silverwing_model?: string;
  silverwing_endpoint_configured?: boolean;
  silverwing?: SilverwingStatus;
  brain_model?: string;
  brain_endpoint_configured?: boolean;
  brain?: { configured: boolean; healthy: boolean; detail?: string; latency_ms?: number | null };
  capabilities?: string[];
}

interface AttachedFile {
  id: string;
  file: File;
  preview: string;
  uploadProgress?: number;
  uploadedUrl?: string;
}

// Allowed file types for chat attachments
const ALLOWED_FILE_TYPES = {
  "image/*": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"],
  "text/plain": [".txt", ".md", ".log"],
  "application/pdf": [".pdf"],
  "application/json": [".json"],
  "application/javascript": [".js", ".ts"],
  "text/csv": [".csv"],
};

// Helper: check if a file is an image
const isImageFile = (file: File): boolean => file.type.startsWith("image/");

// Helper: format file size
const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

// Helper: upload a single file to the multimodal backend
const uploadFile = async (
  file: File,
  onProgress?: (progress: number) => void
): Promise<string | null> => {
  const formData = new FormData();
  formData.append("file", file);
  try {
    // Use fetch with a progress-tracking wrapper for upload
    const response = await sessionFetch(getApiUrl('/api/v1/multimodal/upload/image'), {
      method: "POST",
      headers: {
        ...authHeaders(),
      },
      body: formData,
    });

    if (!response.ok) {
      console.error("Upload failed:", response.statusText);
      return null;
    }

    onProgress?.(100);
    const data = await response.json().catch(() => null);
    if (!data) return null;

    return data.url || data.file_url || data.path || data.filename || null;
  } catch (error) {
    console.error("File upload error:", error);
    return null;
  }
};

export default function RealAIChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [backendConnected, setBackendConnected] = useState(true);
  const [usingLocalFallback, setUsingLocalFallback] = useState(false);
  const [providerConfigured, setProviderConfigured] = useState(false);
  const [verifyMode, setVerifyMode] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sessionIdRef = useRef<string | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);
  const [activity, setActivity] = useState<string[]>([]);
  const retryRef = useRef<
    Map<string, { content: string; clientMessageId: string }>
  >(new Map());

  // File attachments state
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [showConversationSidebar, setShowConversationSidebar] = useState(false);

  const onFileDrop = (acceptedFiles: File[]) => {
    const newFiles = acceptedFiles.map((file) => ({
      id: `${file.name}-${Date.now()}`,
      file,
      preview: isImageFile(file) ? URL.createObjectURL(file) : "",
      uploadProgress: 0,
    }));
    setAttachedFiles((prev) => [...prev, ...newFiles]);
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ALLOWED_FILE_TYPES,
    maxSize: 10 * 1024 * 1024, // 10MB
    onDrop: onFileDrop,
    onDropRejected: () => {
      /* silent */
    },
  });

  const {
    activeModel,
    modelCatalog,
    availableProviders,
    activeSessions,
    currentSessionId,
    setActiveModel,
    loadModelCatalog,
    loadSessions,
    loadSession,
    newSession,
    updateChatSettings,
    chatSettings,
  } = useChatStore((state) => ({
    activeModel: state.activeModel,
    modelCatalog: state.modelCatalog,
    availableProviders: state.availableProviders,
    activeSessions: state.sessions,
    currentSessionId: state.currentSessionId,
    setActiveModel: state.setActiveModel,
    loadModelCatalog: state.loadModelCatalog,
    loadSessions: state.loadSessions,
    loadSession: state.loadSession,
    newSession: state.newSession,
    updateChatSettings: state.updateChatSettings,
    chatSettings: state.chatSettings,
  }));

  // Auto-load sessions on mount
  useEffect(() => {
    void loadModelCatalog();
    loadSystemStatus();
    void loadSessions();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadSystemStatus = async () => {
    try {
      const response = await sessionFetch(getApiUrl('/api/v1/ai/status'), {
        headers: authHeaders(),
      });
      const data = await safeJson(response);
      if (!data) throw new Error("Backend unavailable");

      setSystemStatus({
        status: data.status === "ready" ? "online" : (data.status === "degraded" ? "degraded" : "offline"),
        enabled: Boolean(data.enabled),
        provider: data.provider,
        configured_provider_count: data.configured_provider_count,
        provider_available: data.provider_available,
        ollama_model: data.ollama_model,
        ollama_base_url: data.ollama_base_url,
        silverwing_model: data.silverwing_model,
        silverwing_endpoint_configured: data.silverwing_endpoint_configured,
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
        brain_endpoint_configured: data.brain_endpoint_configured,
        brain: data.brain || { configured: false, healthy: false },
        capabilities: data.capabilities || ["chat", "code generation", "analysis"],
      });
      const hasConfiguredProvider = Number(data.configured_provider_count) > 0;
      setProviderConfigured(hasConfiguredProvider);
      setUsingLocalFallback(!hasConfiguredProvider);
    } catch (error) {
      console.error("Failed to load system status:", error);
      setBackendConnected(false);
      setProviderConfigured(false);
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

  // Browser-native speech recognition (Web Speech API)
  const [isListening, setIsListening] = React.useState(false);
  const recognitionRef = React.useRef<any>(null);

  const toggleListening = () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser.");
      return;
    }
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }
    const recognition = new SpeechRecognition() as any;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onresult = (event: any) => {
      let final = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          final += transcript;
        }
      }
      if (final) {
        setInput((prev) => prev + " " + final.trim());
      }
    };
    recognition.onerror = (event: any) => {
      console.error("Speech recognition error:", event.error);
      setIsListening(false);
    };
    recognition.onend = () => {
      setIsListening(false);
    };
    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  };

  const handleFork = async (messageId: string) => {
    if (isLoading || !currentSessionId) return;
    const clientMessageId = newClientMessageId();
    const assistantId = `assistant-${clientMessageId}`;

    setMessages((prev) => [
      ...prev,
      {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
        status: "CONNECTING",
        clientMessageId,
      },
    ]);
    retryRef.current.set(assistantId, { content: "", clientMessageId });
    setActivity([]);
    let received = "";

    try {
      const response = await sessionFetch(
        getApiUrl(`/api/chat/messages/${encodeURIComponent(currentSessionId)}/${encodeURIComponent(messageId)}/regenerate`),
        {
          method: "POST",
          headers: authHeaders(true),
          body: JSON.stringify({
            model: activeModel,
            client_message_id: clientMessageId,
            temperature: chatSettings.temperature,
            top_p: chatSettings.top_p,
            max_tokens: chatSettings.max_tokens,
          }),
        }
      );

      if (!response.ok || !response.body) {
        let detail = `Regenerate failed (HTTP ${response.status})`;
        try {
          const err = await response.json();
          detail = err?.detail || err?.message || detail;
        } catch {}
        updateAssistant(assistantId, { content: detail, status: "FAILED", retryable: true });
        return;
      }

      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, status: "STREAMING" } : m))
      );

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const chunk = JSON.parse(line.slice(6));
            if (chunk.type === "chunk" && chunk.text) {
              received += chunk.text;
              updateAssistant(assistantId, { content: received });
            } else if (chunk.type === "activity" && chunk.message) {
              setActivity((prev) => [...prev, chunk.message]);
            } else if (chunk.type === "status") {
              const lifecycle = CATEGORY_TO_LIFECYCLE[chunk.status] || "STREAMING";
              updateAssistant(assistantId, { status: lifecycle });
            } else if (chunk.type === "complete" || chunk.type === "done") {
              updateAssistant(assistantId, { status: "COMPLETED" });
              setIsLoading(false);
              return;
            } else if (chunk.type === "error") {
              updateAssistant(assistantId, {
                content: chunk.error || received || "Error",
                status: "FAILED",
                retryable: chunk.retryable,
              });
              setIsLoading(false);
              return;
            }
          } catch {}
        }
      }

      updateAssistant(assistantId, { status: "COMPLETED" });
      setIsLoading(false);
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      updateAssistant(assistantId, {
        content: received || msg,
        status: "FAILED",
        retryable: true,
      });
      setIsLoading(false);
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {
      console.error("Failed to copy text");
    });
  };

  const switchModel = async (providerModel: string) => {
    setActiveModel(providerModel);
    try {
      await sessionFetch(getApiUrl('/api/chat/switch'), {
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
    /**
     * Capabilities observed during this turn, accumulated from `activity`
     * frames. Kept as a local rather than read back out of React state so the
     * stream loop never waits on a render.
     */
    let observedToolCalls: ToolCall[] = [];

    const patch = (extra: Partial<ChatMessage>) => {
      received = extra.content ?? received;
      updateAssistant(assistantId, { content: received, ...extra });
    };

    try {
      const response = await sessionFetch(getApiUrl('/api/chat/stream'), {
        method: "POST",
        headers: authHeaders(true),
        signal: controller.signal,
        body: JSON.stringify({
          message: text,
          session_id: sessionIdRef.current ?? null,
          stream: true,
          model: activeModel,
          client_message_id: clientMessageId,
          temperature: chatSettings.temperature,
          top_p: chatSettings.top_p,
          max_tokens: chatSettings.max_tokens,
        }),
      });

      if (!response.ok || !response.body) {
        // Map HTTP status to a truthful lifecycle state
        let category: string | undefined;
        let detail = `Request failed (HTTP ${response.status})`;
        try {
          const err = await response.json();
          category = err?.category;
          detail = err?.detail || err?.message || err?.error || detail;
        } catch {
          /* non-JSON error body */
        }
        // Map auth-related HTTP status to AUTH_REQUIRED lifecycle
        if (response.status === 401 || response.status === 403) {
          category = "AUTHENTICATION_ERROR";
        }
        throw Object.assign(new Error(detail), { category });
      }

      setBackendConnected(true);
      setUsingLocalFallback(false);
      // Signal that the SSE stream connection is established;
      // the first backend event (typing/meta) will transition to THINKING.
      patch({ status: "CONNECTING" });

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
              case "tool_call_delta": {
                const index = Number(event.index ?? 0);
                const existing = observedToolCalls.find((call) => call.index === index);
                const argumentsSoFar =
                  typeof existing?.arguments?._partial === "string"
                    ? existing.arguments._partial
                    : "";
                observedToolCalls = mergeToolCall(observedToolCalls, {
                  id: event.id || existing?.id,
                  index,
                  name: `${existing?.name ?? ""}${event.name ?? ""}`,
                  arguments: {
                    _partial: `${argumentsSoFar}${event.arguments ?? ""}`,
                  },
                  status: "running",
                });
                patch({ toolCalls: observedToolCalls, status: "TOOL_EXECUTION" });
                break;
              }
              case "activity": {
                // Real backend tool activity (project inspection steps).
                // Also recorded structurally so the transcript can show each
                // capability the agent invoked, not just a log line.
                const name = event.tool ?? event.stage ?? "working";
                const state = event.status ?? "running";

                setActivity((prev) => [...prev, `${name} (${state})`]);

                observedToolCalls = mergeToolCall(observedToolCalls, {
                  name,
                  arguments: event.arguments ?? event.args ?? {},
                  status: normaliseToolStatus(state),
                });
                patch({ toolCalls: observedToolCalls, status: "TOOL_EXECUTION" });
                break;
              }
              case "chunk": {
                const delta = event.content ?? event.text ?? "";
                if (delta) patch({ content: received + delta, status: "STREAMING" });
                break;
              }
              case "complete": {
                  // Prefer the authoritative `tool_calls` payload when present;
                  // otherwise settle whatever activity frames observed, since a
                  // tool that ran but never reported completion would otherwise
                  // stay stuck rendering as "running".
                  const reported = Array.isArray(event.tool_calls)
                    ? event.tool_calls.map(toToolCall)
                    : null;
                  const toolCalls = reported ?? settleToolCalls(observedToolCalls);

                  patch({
                    content: event.content || received,
                    status: "COMPLETED",
                    provider: event.provider,
                    model: event.model,
                    tokens_used:
                      event.usage?.completion_tokens ?? event.usage?.output_tokens,
                    partial: false,
                    retryable: false,
                    ...(toolCalls.length ? { toolCalls } : {}),
                  });
                  retryRef.current.delete(assistantId);
                  break;
                }
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
    if ((!text || isLoading) && attachedFiles.length === 0) return;

    const clientMessageId = newClientMessageId();
    const assistantId = `assistant-${clientMessageId}`;

    // Upload any attached files and include their URLs in the message.
    const uploadPromises = attachedFiles.map(async (af) => {
      const url = await uploadFile(af.file, (progress) => {
        setAttachedFiles((prev) =>
          prev.map((f) =>
            f.id === af.id ? { ...f, uploadProgress: progress } : f
          )
        );
      });
      return { ...af, uploadedUrl: url || undefined };
    });
    const uploadedFiles = await Promise.all(uploadPromises);

    setMessages((prev) => [
      ...prev,
      {
        id: `user-${clientMessageId}`,
        role: "user",
        content: text || "(sent files)",
        timestamp: new Date().toISOString(),
        // Attach file references so they render in the transcript
        ...(uploadedFiles.length
          ? {
              files: uploadedFiles
                .filter((f) => f.uploadedUrl)
                .map((f) => ({
                  name: f.file.name,
                  url: f.uploadedUrl!,
                  type: f.file.type,
                  size: f.file.size,
                })),
            }
          : {}),
      },
      {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
        status: "CONNECTING",
        clientMessageId,
      },
    ]);
    retryRef.current.set(assistantId, { content: text, clientMessageId });
    setInput("");
    setAttachedFiles([]);
    setActivity([]);
    await runStream(
      text || "I've attached some files for analysis.",
      clientMessageId,
      assistantId
    );
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
      const response = await sessionFetch(getApiUrl('/api/v1/codegen/generate'), {
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
      const response = await sessionFetch(getApiUrl('/api/v1/ai/process'), {
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
      const response = await sessionFetch(getApiUrl('/api/v1/ai/status'), {
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

  const removeFile = (id: string) => {
    const file = attachedFiles.find((f) => f.id === id);
    if (file?.preview) URL.revokeObjectURL(file.preview);
    setAttachedFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const clearFiles = () => {
    attachedFiles.forEach((f) => {
      if (f.preview) URL.revokeObjectURL(f.preview);
    });
    setAttachedFiles([]);
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
                No provider configured
              </span>
            ) : providerConfigured && !systemStatus?.enabled ? (
              <span className="text-yellow-400 flex items-center gap-2">
                <AlertCircle className="w-4 h-4" />
                Provider configured - live inference not yet verified
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
          {/* Conversation sidebar toggle (mobile) */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 hover:bg-white/[0.05]"
            onClick={() => setShowConversationSidebar(true)}
            title="Conversations"
          >
            <MessageSquare className="h-4 w-4" />
          </Button>
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
          {/* Model selector in header */}
          <ModelSelector compact showRefresh showSettings={false} />
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
                      {/* Assistant message action buttons (fork + copy) */}
                      {message.role === "assistant" &&
                        message.status === "COMPLETED" &&
                        message.content && (
                          <div className="flex items-center gap-1 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleFork(message.id)}
                              disabled={isLoading}
                              className="h-5 px-1.5 text-[10px] text-gray-400 hover:text-cyan-300"
                              title="Continue from here (fork)"
                            >
                              <GitBranch className="h-3 w-3 mr-1" />
                              Fork
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleCopy(message.content)}
                              className="h-5 px-1.5 text-[10px] text-gray-400 hover:text-gray-300"
                              title="Copy message"
                            >
                              <Copy className="h-3 w-3" />
                            </Button>
                          </div>
                        )}

                      {message.error && (
                        <div className="mb-1.5 text-[11px] text-red-300/90">
                          {message.error}
                        </div>
                      )}
                      {/* Backend capabilities invoked for this turn */}
                      {(message.toolCalls?.length ?? 0) > 0 && (
                        <ToolCallList
                          tools={message.toolCalls ?? []}
                          className="mb-2"
                        />
                      )}
                      <div className="text-sm">
                        {message.content ? (
                          <MarkdownMessage
                            streaming={
                              message.status === "STREAMING" ||
                              message.status === "THINKING"
                            }
                          >
                            {message.content}
                          </MarkdownMessage>
                        ) : message.role === "assistant" &&
                          (message.status === "THINKING" ||
                            message.status === "STREAMING") ? (
                          <span className="text-gray-400">
                            {message.status === "THINKING"
                              ? "Thinking…"
                              : "Waiting for first token…"}
                          </span>
                        ) : null}
                      </div>

                      {/* Attached file previews in the message */}
                      {message.files && message.files.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {message.files.map((file, idx) => (
                            <div
                              key={`${file.name}-${idx}`}
                              className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2 py-1"
                            >
                              {file.type.startsWith("image/") ? (
                                <img
                                  src={file.url}
                                  alt={file.name}
                                  className="h-8 w-8 rounded object-cover"
                                />
                              ) : (
                                <FileTextIcon className="h-5 w-5 text-cyan-400/50" />
                              )}
                              <span className="text-xs truncate max-w-[120px]">
                                {file.name}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}

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
                            <div key={s.key} className="text-[11px] text-gray-400 flex items-center gap-1">
                              <span className="text-cyan-400">[{s.key}]</span>{" "}
                              {s.value ? (
                                <a
                                  href={s.value}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-cyan-300 hover:text-cyan-200 hover:underline truncate max-w-[200px] inline-block"
                                >
                                  {s.value.slice(0, 140)}
                                  {s.value.length > 140 && "…"}
                                </a>
                              ) : (
                                <span>{(s.value ?? "").slice(0, 140)}</span>
                              )}
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

            <ChatSettingsPanel />
            <div className="p-4 border-t border-white/5">
              {/* Attached files preview */}
              {attachedFiles.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-2">
                  {attachedFiles.map((af) => (
                    <div
                      key={af.id}
                      className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2 py-1"
                    >
                      {af.preview ? (
                        <img
                          src={af.preview}
                          alt={af.file.name}
                          className="h-8 w-8 rounded object-cover"
                        />
                      ) : (
                        <FileTextIcon className="h-5 w-5 text-cyan-400/50" />
                      )}
                      <div className="flex flex-col min-w-0">
                        <span className="text-xs font-medium truncate max-w-[120px]">
                          {af.file.name}
                        </span>
                        <span className="text-[10px] text-gray-500">
                          {formatFileSize(af.file.size)}
                        </span>
                      </div>
                      {af.uploadProgress !== undefined &&
                        af.uploadProgress < 100 && (
                          <div className="text-[10px] text-cyan-400">
                            {af.uploadProgress}%
                          </div>
                        )}
                      <button
                        type="button"
                        onClick={() => removeFile(af.id)}
                        className="ml-1 rounded p-0.5 hover:bg-white/[0.1]"
                      >
                        <XIcon className="h-3 w-3 text-gray-400 hover:text-red-400" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex gap-2">
                {!attachedFiles.length ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-9 w-9 p-0 border border-white/10 hover:bg-white/[0.05]"
                    onClick={() => {
                      const fileInput = document.createElement("input");
                      fileInput.type = "file";
                      fileInput.accept = Object.values(
                        ALLOWED_FILE_TYPES
                      ).flat().join(",");
                      fileInput.multiple = true;
                      fileInput.onchange = () => {
                        if (fileInput.files) onFileDrop(Array.from(fileInput.files));
                      };
                      fileInput.click();
                    }}
                    title="Attach file"
                  >
                    <Paperclip className="h-4 w-4 text-gray-400" />
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-9 w-9 p-0 border border-white/10 hover:bg-white/[0.05]"
                    onClick={() => {
                      const fileInput = document.createElement("input");
                      fileInput.type = "file";
                      fileInput.accept = Object.values(
                        ALLOWED_FILE_TYPES
                      ).flat().join(",");
                      fileInput.multiple = true;
                      fileInput.onchange = () => {
                        if (fileInput.files) onFileDrop(Array.from(fileInput.files));
                      };
                      fileInput.click();
                    }}
                    title="Attach more files"
                  >
                    <Paperclip className="h-4 w-4 text-cyan-400" />
                  </Button>
                )}
                <Textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Ask JARVIS anything..."
                  className="flex-1 bg-white/[0.05] border-white/10 text-white placeholder:text-gray-400"
                  rows={2}
                />
                {/* Voice input (browser-native Web Speech API) */}
                <Button
                  type="button"
                  variant={isListening ? "default" : "ghost"}
                  size="sm"
                  className="h-9 w-9 p-0 border border-white/10"
                  onClick={toggleListening}
                  title={isListening ? "Stop listening" : "Voice input"}
                >
                  <Mic
                    className={`h-4 w-4 ${
                      isListening ? "text-cyan-400 animate-pulse" : "text-gray-400"
                    }`}
                  />
                </Button>
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
                  disabled={(!input.trim() && attachedFiles.length === 0) || isLoading}
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

      {/* Conversation history sidebar (overlay on mobile, fixed on desktop) */}
      <ConversationHistorySidebar
        open={showConversationSidebar}
        onOpenChange={setShowConversationSidebar}
      />
    </div>
  );
}
