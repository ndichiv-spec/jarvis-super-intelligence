"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Globe, RefreshCw, Plus, X, Navigation, Download, Search,
  Settings, Eye, EyeOff, Shield, ShieldAlert, Bookmark,
  Clock, FileText, ExternalLink, Maximize2, Minimize2,
  AlertTriangle, CheckCircle, HelpCircle, Brain,
  PanelLeft, PanelRight, ChevronLeft, ChevronRight, Loader2,
  Copy, Link2, Trash2, History, Tag,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "sonner";

import useBrowserStore from "@/features/browser/store";
import type {
  BrowserTab, AIContext, BrowserSession, PrivacyMode, SearchResult, BrowserEvidence,
  NetworkDiagnosticResult, DnsDiagnosticsResult, ProxyDiagnosticsResult,
  BrowserHealthStatus, RecoveryResult, NetworkEventEntry, NavigationTimelineEntry,
  BrowserErrorCategory,
} from "@/features/browser/types";
import { usePlatformStore } from "@/stores/platform-store";
import API_ENDPOINTS from "@/config/api";
import apiClient from "@/lib/api-client";
import { glassCard, glassCardHover, statusToVariant, severityToColorClass } from "@/lib/design-system";

// ---------------------------------------------------------------------------
// EmbeddedBrowser — AI-native browser workspace
// ---------------------------------------------------------------------------

interface EmbeddedBrowserProps {
  /** When true, renders in a compact embedded mode (smaller UI chrome). */
  compact?: boolean;
  /** Session ID to load (for cross-platform summonability). */
  sessionId?: string;
  /** Initial URL to navigate to. */
  initialUrl?: string;
  /** Callback when browser needs to communicate to the host (e.g. close). */
  onEvent?: (event: { type: string; data?: unknown }) => void;
}

interface BrowserEnginePayload {
  engine?: unknown;
  capabilities?: unknown;
}

type BrowserEngineStatus =
  | { state: "loading" }
  | { state: "reported"; engine: string; capabilities: string[] }
  | { state: "unavailable"; message: string };

export default function EmbeddedBrowser({
  compact = false,
  sessionId: propSessionId,
  initialUrl,
  onEvent,
}: EmbeddedBrowserProps) {
  // ---- Store ----
  const store = useBrowserStore();
  const {
    sessions,
    tabs,
    activeSessionId,
    activeTabId,
    isLoading,
    error,
    privacyMode,
    showAIContext,
    showResearchControls,
    showEvidencePanel,
    showSecurityPanel,
    showDownloadsPanel,
    showBookmarksPanel,
    showHistoryPanel,
    aiContext,
    bookmarks,
    history,
    downloads,
    evidence,
    searchResults,
    searchQuery,
    isSearching,
    securityReport,
    status,
    initialized,
    // Methods
    init,
    createSession,
    createTab,
    loadTabs,
    setActiveSession,
    setActiveTab,
    closeTab,
    navigate,
    extractPage,
    clearAIContext,
    search,
    captureEvidence,
    loadBookmarks,
    addBookmark,
    loadHistory,
    loadDownloads,
    checkPromptInjection,
    loadSecurityReport,
    loadStatus,
    setShowAIContext,
    setShowResearchControls,
    setShowEvidencePanel,
    setShowSecurityPanel,
    setShowDownloadsPanel,
    setShowBookmarksPanel,
    setShowHistoryPanel,
    setPrivacyMode,
    clearError,
    // Network Intelligence Layer
    runNetworkDiagnostics,
    runDnsDiagnostics,
    runProxyDiagnostics,
    checkBrowserHealth,
    recoverNavigation,
    loadNetworkEvents,
    loadNavigationTimeline,
    loadBrowserHealth,
    networkEvents,
    navigationTimeline,
    browserHealth,
    lastDiagnosticsResult,
    isRecovering,
    recoveryError,
  } = store;

  // ---- Local UI state ----
  const [urlInput, setUrlInput] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [evidenceInput, setEvidenceInput] = useState<{ selected_passage: string; claim: string }>(
    { selected_passage: "", claim: "" }
  );
  const [showRightPanel, setShowRightPanel] = useState(true);
  const [rightPanelTab, setRightPanelTab] = useState("ai-context");
  const [engineStatus, setEngineStatus] = useState<BrowserEngineStatus>({ state: "loading" });
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // ---- Initialization ----
  useEffect(() => {
    if (!initialized) {
      void init();
    }
  }, [init, initialized]);

  useEffect(() => {
    let active = true;
    void apiClient.get<BrowserEnginePayload>(API_ENDPOINTS.browser.engine)
      .then((payload) => {
        if (!active) return;
        const engine = typeof payload.engine === "string" ? payload.engine : "";
        const capabilities = Array.isArray(payload.capabilities)
          ? payload.capabilities.filter((capability): capability is string => typeof capability === "string")
          : [];
        if (!engine) {
          setEngineStatus({ state: "unavailable", message: "The backend did not report an active browser engine." });
          return;
        }
        setEngineStatus({ state: "reported", engine, capabilities });
      })
      .catch((error: unknown) => {
        if (active) {
          setEngineStatus({
            state: "unavailable",
            message: error instanceof Error ? error.message : "Engine capability status could not be loaded.",
          });
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    // If a session ID was passed via prop, use it
    if (propSessionId && propSessionId !== activeSessionId) {
      void setActiveSession(propSessionId);
    }
  }, [propSessionId, activeSessionId, setActiveSession]);

  // ---- Session/tab bootstrap ----
  const ensureSessionAndTab = useCallback(async () => {
    if (!activeSessionId && sessions.length === 0) {
      const sess = await createSession("Browser Session", privacyMode, undefined, undefined);
      if (sess) {
        await setActiveSession(sess.id);
      }
    } else if (!activeSessionId && sessions.length > 0) {
      await setActiveSession(sessions[0].id);
    }

    // Ensure there's at least one tab
    const sess = activeSessionId ? sessions.find((s) => s.id === activeSessionId) : null;
    if (sess && sess.tabs.length === 0 && !activeTabId) {
      const url = initialUrl || "about:blank";
      const tab = await createTab(sess.id, url);
      if (tab) {
        await setActiveTab(tab.id);
      }
    } else if (!activeTabId && sess && sess.tabs.length > 0) {
      await setActiveTab(sess.tabs[0]);
    }
  }, [
    activeSessionId, sessions, activeTabId, privacyMode,
    createSession, setActiveSession, createTab, setActiveTab, initialUrl,
  ]);

  useEffect(() => {
    void ensureSessionAndTab();
  }, [ensureSessionAndTab]);

  // ---- Computed values ----
  const activeSession: BrowserSession | undefined = activeSessionId
    ? sessions.find((s) => s.id === activeSessionId)
    : sessions[0];

  // Deduplicate tabs to prevent React key collision warnings
  const visibleTabs = React.useMemo(() => {
    if (!activeSession?.tabs) return [];
    const uniqueTabIds = [...new Set(activeSession?.tabs || [])];
    return uniqueTabIds
      .map((tid) => tabs[tid])
      .filter(Boolean) as BrowserTab[];
  }, [activeSession?.tabs, tabs]);

  const activeTab: BrowserTab | undefined = activeTabId ? tabs[activeTabId] : undefined;

  // ---- Event handlers ----

  const handleNavigate = useCallback(async () => {
    if (!urlInput.trim() || !activeSessionId || !activeTabId) return;

    const result = await navigate(activeSessionId, urlInput, activeTabId, privacyMode);
    if (result?.blocked) {
      toast.error(`Navigation blocked: ${result.reason}`, {
        description: "Security policy prevented this navigation.",
      });
    } else if (result?.navigated) {
      setUrlInput(result?.url ?? urlInput);
      // Trigger extraction to get AI context
      if (activeTabId) {
        setTimeout(() => {
          void extractPage(result.url ?? "");
        }, 1000);
      }
    }
  }, [urlInput, activeSessionId, activeTabId, navigate, privacyMode, extractPage]);

  const handleUrlKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      void handleNavigate();
    }
  }, [handleNavigate]);

  const handleNewTab = useCallback(async () => {
    if (!activeSession) return;
    const tab = await createTab(activeSession.id, "about:blank");
    if (tab) {
      await setActiveTab(tab.id);
      setUrlInput("about:blank");
    }
  }, [activeSession, createTab, setActiveTab]);

  const handleCloseTab = useCallback(async (tabId: string) => {
    await closeTab(tabId);
  }, [closeTab]);

  const handleTabClick = useCallback((tabId: string) => {
    setActiveTab(tabId);
    const tab = tabs[tabId];
    if (tab) {
      setUrlInput(tab.url);
    }
  }, [tabs, setActiveTab]);

  const handleSearch = useCallback(async () => {
    if (!searchInput.trim() || !activeSession) return;
    const results = await search(searchInput, activeSession.id);
    if (results.length > 0) {
      // Show results in the AI context panel
      setShowRightPanel(true);
      setRightPanelTab("search");
    }
  }, [searchInput, activeSession, search, setShowRightPanel, setRightPanelTab]);

  const handleSearchKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      void handleSearch();
    }
  }, [handleSearch]);

  const handleCaptureEvidence = useCallback(async () => {
    if (!activeTab || !evidenceInput.selected_passage.trim()) {
      toast.error("Please enter a passage to capture as evidence");
      return;
    }
    const ev = await captureEvidence({
      url: activeTab.url,
      title: activeTab.title,
      selected_passage: evidenceInput.selected_passage,
      page_context: aiContext?.text.slice(0, 500) ?? "",
      claim: evidenceInput.claim || null,
      verification_status: "unchecked",
      research_session_id: activeSession?.research_session_id ?? null,
      mission_id: activeSession?.mission_id ?? null,
    });
    if (ev) {
      toast.success("Evidence captured", { description: ev.id });
      setEvidenceInput({ selected_passage: "", claim: "" });
    }
  }, [activeTab, evidenceInput, aiContext, activeSession, captureEvidence]);

  const handlePromptInjectionCheck = useCallback(async () => {
    if (!activeTab) return;
    const result = await checkPromptInjection(
      aiContext?.text ?? activeTab.extracted_content ?? ""
    );
    if (result.flagged) {
      toast.warning("Prompt injection detected", {
        description: `Confidence: ${result.confidence}. Matches: ${result.matches.join("; ")}`,
      });
      setShowSecurityPanel(true);
      setShowRightPanel(true);
    } else {
      toast.success("No prompt injection detected");
    }
  }, [activeTab, aiContext, checkPromptInjection, setShowSecurityPanel, setShowRightPanel]);

  const handleBookmark = useCallback(async () => {
    if (!activeTab) return;
    const bm = await addBookmark({
      url: activeTab.url,
      title: activeTab.title,
      tags: ["browser"],
    });
    if (bm) {
      toast.success("Bookmarked", { description: bm.title });
    }
  }, [activeTab, addBookmark]);

  const handleAutonomyToggle = useCallback(async () => {
    if (!activeSession) return;
    const current = activeSession.privacy_mode;
    const next: PrivacyMode = current === "agent" || current === "automation" ? "standard" : "agent";
    await store.updateSession(activeSession.id, { privacy_mode: next });
    setPrivacyMode(next);
    toast.success(`Privacy mode: ${next}`, {
      description: next === "agent" ? "Autonomous browsing enabled (high-risk actions still require consent)" : "Autonomous browsing disabled",
    });
  }, [activeSession, store.updateSession, setPrivacyMode]);

  // ---- Iframe rendering ----
  const iframeSrc = activeTab?.url || "";

  return (
    <div className={`flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-[#0b111b] ${compact ? "text-sm" : ""}`}>
      {!compact && (
        <header className="shrink-0 border-b border-white/[0.07] px-4 py-4 md:px-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200/70">JARVIS · Research workspace</p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight text-slate-100 md:text-2xl">Web browser</h1>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-slate-400">
            Inspect pages, extract text, and keep research evidence with your browser session.
          </p>
        </header>
      )}

      {/* Top navigation / address bar */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-white/[0.07] bg-[#0d1520] p-3">
        {/* Session selector + new tab */}
        <div className="flex shrink-0 items-center gap-2">
          <select
            value={activeSessionId ?? ""}
            onChange={(e) => {
              void setActiveSession(e.target.value || null);
            }}
            aria-label="Browser session"
            className="max-w-40 rounded-md border border-white/10 bg-black/20 px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-cyan-200/50"
          >
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>

          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleNewTab}
                  disabled={!activeSession || isLoading}
                  aria-label="New browser tab"
                  className="h-8 w-8 p-0"
                >
                  <Plus className="w-4 h-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>New tab</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        {/* Tab bar */}
        <div role="group" aria-label="Open browser tabs" className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
          {visibleTabs?.map((tab) => (
            <div
              key={tab.id}
              className={`flex min-w-0 items-center gap-1 rounded-md border border-transparent px-1.5 py-1 transition-colors ${
                tab.id === activeTabId ? "border-cyan-200/15 bg-cyan-200/[0.06]" : ""
              }`}
              onContextMenu={(event) => {
                event.preventDefault();
                void handleCloseTab(tab.id);
              }}
            >
              <button
                type="button"
                onClick={() => handleTabClick(tab.id)}
                aria-pressed={tab.id === activeTabId}
                aria-controls="browser-page-preview"
                title={tab.url}
                className={`flex min-w-0 items-center gap-1 rounded px-1 py-0.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200/50 ${
                  tab.id === activeTabId
                    ? "text-slate-100"
                    : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200"
                }`}
              >
                {tab.prompt_injection_flagged && (
                  <ShieldAlert className="h-3 w-3 shrink-0 text-red-400" />
                )}
                <span className="max-w-[150px] truncate">{tab.title || "Untitled"}</span>
                {!tab.id.endsWith("about:blank") && <Globe className="h-3 w-3 shrink-0 opacity-50" />}
              </button>
              <button
                type="button"
                onClick={() => void handleCloseTab(tab.id)}
                aria-label={`Close ${tab.title || "untitled"} tab`}
                className="rounded p-0.5 text-slate-500 hover:text-rose-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200/50"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          )) ?? []}
        </div>

        {/* Address bar + controls */}
        <div className="flex min-w-0 basis-full items-center gap-2 sm:ml-auto sm:basis-auto">
          <div className="relative flex min-w-0 flex-1 items-center sm:flex-initial">
            {activeTab?.prompt_injection_flagged && (
              <ShieldAlert className="absolute left-2 w-4 h-4 text-red-400 z-10" />
            )}
            <Input
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyDown={handleUrlKeyDown}
              aria-label="Address or search"
              placeholder="Enter URL or search..."
              className={
                "w-full min-w-0 border-white/10 bg-black/20 text-xs text-slate-100 sm:w-64 lg:w-80 " +
                (activeTab?.prompt_injection_flagged ? "border-red-500 pl-8" : "")
              }
              readOnly={isLoading}
            />
            {activeTab?.is_loading && (
              <RefreshCw className="absolute right-2 w-4 h-4 animate-spin text-gray-400" />
            )}
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-0.5">
            {/* Privacy mode indicator */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge
                    variant={
                      privacyMode === "agent" || privacyMode === "automation"
                        ? "default"
                        : privacyMode === "private"
                        ? "secondary"
                        : "outline"
                    }
                  >
                    {privacyMode === "agent" && <Shield className="w-3 h-3 mr-1" />}
                    {privacyMode}
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>Privacy mode: {privacyMode}</TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {/* Back / Forward / Reload */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={() => {
                      if (iframeRef.current?.contentWindow) {
                        iframeRef.current.contentWindow.history.back();
                      }
                    }}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Back</TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={() => {
                      if (iframeRef.current?.contentWindow) {
                        iframeRef.current.contentWindow.history.forward();
                      }
                    }}
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Forward</TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={() => {
                      if (iframeRef.current) {
                        iframeRef.current.src = iframeRef.current.src;
                      }
                    }}
                    disabled={isLoading}
                  >
                    <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Reload</TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <Separator orientation="vertical" className="h-5" />

            {/* Panel toggles */}
            {!showRightPanel && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0"
                      onClick={() => setShowRightPanel(true)}
                    >
                      <PanelRight className="w-4 h-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Show AI context panel</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
            {showRightPanel && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0"
                      onClick={() => setShowRightPanel(false)}
                    >
                      <PanelLeft className="w-4 h-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Hide panel</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}

            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={() => setShowRightPanel(true)}
                  >
                    <Settings className="w-4 h-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Browser settings</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-start gap-2 border-b border-white/[0.06] bg-black/10 px-3 py-2.5 text-xs" role="status" aria-live="polite">
        <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 ${
          engineStatus.state === "reported"
            ? "border-cyan-200/15 bg-cyan-200/[0.04] text-cyan-100"
            : engineStatus.state === "unavailable"
              ? "border-amber-200/15 bg-amber-200/[0.04] text-amber-100"
              : "border-white/[0.08] text-slate-300"
        }`}>
          {engineStatus.state === "loading" && <Loader2 aria-hidden="true" className="h-3 w-3 animate-spin motion-reduce:animate-none" />}
          {engineStatus.state === "reported"
            ? `Backend engine · ${engineStatus.engine}`
            : engineStatus.state === "unavailable"
              ? "Backend engine · unverified"
              : "Checking backend engine"}
        </span>
        {engineStatus.state === "reported" && (
          <span className="flex flex-wrap gap-1.5">
            {engineStatus.capabilities.length > 0
              ? engineStatus.capabilities.map((capability) => (
                  <Badge key={capability} variant="outline" className="border-white/[0.08] px-2 py-1 text-[11px] text-slate-300">
                    {capability === "http_fetch"
                      ? "HTTP fetch"
                      : capability === "page_extraction"
                        ? "Page extraction"
                        : capability}
                  </Badge>
                ))
              : <span className="py-1 text-slate-400">No capabilities reported</span>}
          </span>
        )}
        {engineStatus.state === "unavailable" && (
          <span className="min-w-0 py-1 text-amber-100/80">{engineStatus.message}</span>
        )}
        <p className="basis-full text-[11px] leading-relaxed text-slate-400">
          JARVIS uses backend HTTP fetch and page extraction; the page preview is a regular browser iframe. Some sites block iframe previews. No alternate browser engines are available.
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center space-x-2 p-2 bg-red-900/20 border-b border-red-700 text-red-300 text-sm">
          <AlertTriangle className="w-4 h-4" />
          <span>{error}</span>
          <button onClick={clearError} className="ml-auto text-xs underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Main workspace */}
      <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
        {/* Page viewport */}
        <div id="browser-page-preview" role="region" aria-label="Page preview in a browser iframe" className="relative min-w-0 flex-1 bg-slate-900">
          {activeTab ? (
            <iframe
              ref={iframeRef}
              src={activeTab.url === "about:blank" ? "about:blank" : activeTab.url}
              title={activeTab.title || "JARVIS Browser"}
              className="w-full h-full border-none"
              sandbox={
                privacyMode === "private" || privacyMode === "authenticated"
                  ? "allow-scripts allow-same-origin allow-forms"
                  : "allow-scripts allow-same-origin allow-forms allow-popups"
              }
              onLoad={() => {
                // Tab loading state is managed via store; iframe load is informational
                void fetch('/api/v1/browser/status').then(() => {});
              }}
              onError={() => {
                toast.error("Failed to load page", {
                  description: "Click 'Diagnose' to run network diagnostics.",
                  action: {
                    label: "Diagnose",
                    onClick: () => {
                      if (activeTab) {
                        void runNetworkDiagnostics(activeTab.url, 10.0);
                      }
                    },
                  },
                });
              }}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400">
              <Globe className="w-12 h-12 mb-4 opacity-30" />
              <p>No active tab</p>
            </div>
          )}
        </div>

        {/* Right panel — AI context, research, evidence, security */}
        <AnimatePresence initial={false}>
          {showRightPanel && (
            <motion.div
              key="right-panel"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 400, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              style={{ maxWidth: compact ? "70vw" : "80vw" }}
              className="flex min-w-0 flex-col overflow-hidden border-l border-white/[0.07] bg-[#0d1520]"
            >
              <Tabs
                value={rightPanelTab}
                onValueChange={setRightPanelTab}
                className="flex-1 flex flex-col"
              >
                <TabsList className="grid grid-cols-6 bg-slate-900 m-2 h-auto">
                  <TabsTrigger value="ai-context" className="text-xs py-1">
                    <Brain className="w-3 h-3 mr-1" />
                    AI
                  </TabsTrigger>
                  <TabsTrigger value="research" className="text-xs py-1">
                    <Search className="w-3 h-3 mr-1" />
                    Research
                  </TabsTrigger>
                  <TabsTrigger value="evidence" className="text-xs py-1">
                    <FileText className="w-3 h-3 mr-1" />
                    Evidence
                  </TabsTrigger>
                  <TabsTrigger value="security" className="text-xs py-1">
                    <Shield className="w-3 h-3 mr-1" />
                    Security
                  </TabsTrigger>
                  <TabsTrigger value="downloads" className="text-xs py-1">
                    <Download className="w-3 h-3 mr-1" />
                    Tools
                  </TabsTrigger>
                  <TabsTrigger value="network-diagnostics" className="text-xs py-1">
                    <Globe className="w-3 h-3 mr-1" />
                    Network
                  </TabsTrigger>
                </TabsList>

                {/* AI Context Panel */}
                <TabsContent value="ai-context" className="flex-1 overflow-y-auto m-0">
                  <ScrollArea className="h-full">
                    <div className="p-4 space-y-4">
                      {!aiContext ? (
                        <div className="text-center py-8 text-gray-500">
                          <Brain className="w-8 h-8 mx-auto mb-2 opacity-30" />
                          <p>No AI context available.</p>
                          <p className="text-xs mt-1">Navigate to a page or select text to analyze.</p>
                        </div>
                      ) : (
                        <>
                          {/* Page metadata */}
                          <div className="space-y-2">
                            <h3 className="text-xs font-semibold text-gray-400 uppercase">
                              Page Understanding
                            </h3>
                            <div className="space-y-1 text-sm">
                              <div>
                                <span className="text-gray-500">Title:</span>
                                <span className="text-white ml-1 truncate">{aiContext.metadata.title || "Untitled"}</span>
                              </div>
                              <div>
                                <span className="text-gray-500">URL:</span>
                                <a
                                  href={aiContext.metadata.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-blue-400 ml-1 hover:underline truncate"
                                >
                                  {aiContext.metadata.url}
                                </a>
                              </div>
                              {aiContext.metadata.description && (
                                <div>
                                  <span className="text-gray-500">Description:</span>
                                  <span className="text-gray-300 ml-1 text-xs">{aiContext.metadata.description}</span>
                                </div>
                              )}
                              <div>
                                <span className="text-gray-500">Words:</span>
                                <span className="text-gray-300 ml-1">{aiContext.metadata.word_count.toLocaleString()}</span>
                              </div>
                            </div>
                          </div>

                          <Separator className="bg-slate-700" />

                          {/* Page structure */}
                          {aiContext.structure && (
                            <div className="space-y-2">
                              <h4 className="text-xs font-semibold text-gray-400 uppercase">
                                Structure
                              </h4>
                              <div className="grid grid-cols-2 gap-2 text-xs">
                                <div className="flex justify-between">
                                  <span className="text-gray-500">Links:</span>
                                  <span className="text-gray-300">{aiContext.structure.links}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-gray-500">Images:</span>
                                  <span className="text-gray-300">{aiContext.structure.images}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-gray-500">Headings:</span>
                                  <span className="text-gray-300">{aiContext.structure.headings.length}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-gray-500">Tables:</span>
                                  <span className="text-gray-300">{aiContext.structure.tables}</span>
                                </div>
                              </div>
                              {aiContext.structure.headings.length > 0 && (
                                <div className="space-y-1">
                                  {aiContext.structure.headings.slice(0, 5).map((h, i) => (
                                    <div
                                      key={i}
                                      className={`text-xs pl-${h.level < 5 ? h.level : 4} text-gray-300`}
                                    >
                                      {h.text || "(empty)"}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}

                          <Separator className="bg-slate-700" />

                          {/* Entities */}
                          {aiContext.entities && aiContext.entities.length > 0 && (
                            <div className="space-y-2">
                              <h4 className="text-xs font-semibold text-gray-400 uppercase">
                                Entities ({aiContext.entities.length})
                              </h4>
                              <div className="flex flex-wrap gap-1">
                                {aiContext.entities.slice(0, 15).map((e, i) => (
                                  <Badge
                                    key={i}
                                    variant="outline"
                                    className="text-xs"
                                    title={e.type}
                                  >
                                    {e.value}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          )}

                          <Separator className="bg-slate-700" />

                          {/* AI actions */}
                          <div className="grid grid-cols-2 gap-2">
                            {[
                              { label: "Explain", icon: HelpCircle },
                              { label: "Summarize", icon: FileText },
                              { label: "Research", icon: Search },
                              { label: "Extract", icon: Copy },
                              { label: "Verify", icon: Shield },
                              { label: "Save Evidence", icon: Bookmark },
                            ].map((action) => {
                              const Icon = action.icon;
                              return (
                                <Button
                                  key={action.label}
                                  size="sm"
                                  variant="ghost"
                                  className="justify-start text-xs"
                                  onClick={() => {
                                    if (action.label === "Summarize") {
                                      if (aiContext?.text) {
                                        navigator.clipboard.writeText(aiContext.text.slice(0, 500));
                                        toast.success("Page summary copied to clipboard");
                                      }
                                    } else if (action.label === "Extract") {
                                      if (aiContext?.text) {
                                        navigator.clipboard.writeText(aiContext.text);
                                        toast.success("Page text copied");
                                      }
                                    } else if (action.label === "Save Evidence") {
                                      setShowEvidencePanel(true);
                                      setShowRightPanel(true);
                                      setRightPanelTab("evidence");
                                    } else if (action.label === "Research") {
                                      setShowResearchControls(true);
                                      setShowRightPanel(true);
                                      setRightPanelTab("research");
                                    } else if (action.label === "Verify") {
                                      void handlePromptInjectionCheck();
                                    } else if (action.label === "Explain") {
                                      if (aiContext?.text) {
                                        toast.info("Send this page to Chat to explain", {
                                          description: "Use the chat panel with the page content as context",
                                        });
                                        void usePlatformStore.getState().addActivity({
                                          domain: "chat",
                                          operation: "page_context_requested",
                                          title: "Explain page content",
                                          detail: aiContext.metadata.title,
                                          severity: "info",
                                        });
                                      }
                                    }
                                  }}
                                >
                                  <Icon className="w-3 h-3 mr-1" />
                                  {action.label}
                                </Button>
                              );
                            })}
                          </div>

                          {/* Selected content */}
                          {aiContext.selected_content && (
                            <>
                              <Separator className="bg-slate-700" />
                              <div className="space-y-1">
                                <h4 className="text-xs font-semibold text-gray-400 uppercase">
                                  Selected Content
                                </h4>
                                <div className="text-xs text-gray-300 p-2 bg-slate-900/50 rounded max-h-24 overflow-y-auto">
                                  {aiContext.selected_content}
                                </div>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="text-xs"
                                  onClick={() => {
                                    navigator.clipboard.writeText(aiContext.selected_content || "");
                                    toast.success("Selection copied");
                                  }}
                                >
                                  <Copy className="w-3 h-3 mr-1" />
                                  Copy
                                </Button>
                              </div>
                            </>
                          )}

                          {/* Prompt injection warning */}
                          {aiContext.prompt_injection.flagged && (
                            <div className="p-2 bg-red-900/20 border border-red-700 rounded text-xs text-red-300">
                              <ShieldAlert className="w-3 h-3 inline mr-1" />
                              Prompt injection detected (confidence: {aiContext.prompt_injection.confidence})
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  </ScrollArea>
                </TabsContent>

                {/* Research / Search panel */}
                <TabsContent value="research" className="flex-1 overflow-y-auto m-0">
                  <ScrollArea className="h-full">
                    <div className="p-4 space-y-4">
                      <div className="space-y-2">
                        <h3 className="text-xs font-semibold text-gray-400 uppercase">
                          Web Search
                        </h3>
                        <div className="flex space-x-2">
                          <Input
                            value={searchInput}
                            onChange={(e) => setSearchInput(e.target.value)}
                            onKeyDown={handleSearchKeyDown}
                            placeholder="Search the web..."
                            className="text-xs bg-slate-700 border-slate-600 text-white"
                          />
                          <Button
                            size="sm"
                            onClick={handleSearch}
                            disabled={isSearching || !searchInput.trim()}
                          >
                            <Search className="w-3 h-3" />
                          </Button>
                        </div>
                      </div>

                      {isSearching && (
                        <div className="text-center py-4 text-gray-400 text-xs">
                          <RefreshCw className="w-4 h-4 mx-auto animate-spin mb-2" />
                          Searching...
                        </div>
                      )}

                      <div className="space-y-2">
                        {searchResults.map((result, i) => (
                          <div key={i} className="space-y-1">
                            <a
                              href={result.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-sm text-blue-400 hover:underline"
                            >
                              {result.title}
                            </a>
                            <p className="text-xs text-gray-400">{result.snippet}</p>
                            <div className="flex items-center space-x-2">
                              <Badge variant="outline" className="text-xs">
                                {result.source}
                              </Badge>
                              <span className="text-xs text-gray-500">{result.domain}</span>
                            </div>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-xs"
                              onClick={async () => {
                                if (activeSession) {
                                  await createTab(activeSession.id, result.url, result.title);
                                }
                              }}
                            >
                              <Plus className="w-3 h-3 mr-1" />
                              Open in tab
                            </Button>
                          </div>
                        ))}
                      </div>

                      {searchResults.length === 0 && !isSearching && searchQuery && (
                        <p className="text-xs text-gray-500">No results found.</p>
                      )}

                      {/* Research tools */}
                      {activeTab && (
                        <>
                          <Separator className="bg-slate-700" />
                          <div className="space-y-2">
                            <h4 className="text-xs font-semibold text-gray-400 uppercase">
                              Research Tools
                            </h4>
                            <div className="grid grid-cols-2 gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-xs justify-start"
                                onClick={handlePromptInjectionCheck}
                              >
                                <Shield className="w-3 h-3 mr-1" />
                                Scan for injection
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-xs justify-start"
                                onClick={handleBookmark}
                              >
                                <Bookmark className="w-3 h-3 mr-1" />
                                Bookmark page
                              </Button>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  </ScrollArea>
                </TabsContent>

                {/* Evidence panel */}
                <TabsContent value="evidence" className="flex-1 overflow-y-auto m-0">
                  <ScrollArea className="h-full">
                    <div className="p-4 space-y-4">
                      {/* Capture form */}
                      {activeTab && (
                        <div className="space-y-2">
                          <h3 className="text-xs font-semibold text-gray-400 uppercase">
                            Capture Evidence
                          </h3>
                          <div className="space-y-2">
                            <Textarea
                              value={evidenceInput.selected_passage}
                              onChange={(e) => setEvidenceInput({ ...evidenceInput, selected_passage: e.target.value })}
                              placeholder="Selected passage or claim to verify..."
                              className="text-xs bg-slate-700 border-slate-600 text-white min-h-[60px]"
                              readOnly={!aiContext}
                            />
                            <Input
                              value={evidenceInput.claim}
                              onChange={(e) => setEvidenceInput({ ...evidenceInput, claim: e.target.value })}
                              placeholder="Claim to verify..."
                              className="text-xs bg-slate-700 border-slate-600 text-white"
                            />
                            <Button
                              size="sm"
                              onClick={() => void handleCaptureEvidence()}
                              disabled={!evidenceInput.selected_passage.trim() || isLoading}
                              className="w-full"
                            >
                              <FileText className="w-3 h-3 mr-1" />
                              Capture Evidence
                            </Button>
                          </div>
                        </div>
                      )}

                      <Separator className="bg-slate-700" />

                      {/* Evidence list */}
                      <div className="space-y-2">
                        <h4 className="text-xs font-semibold text-gray-400 uppercase">
                          Saved Evidence ({evidence.length})
                        </h4>
                        {evidence.slice(0, 20).map((ev) => (
                          <div key={ev.id} className="text-xs p-2 bg-slate-900/50 rounded space-y-1">
                            <div className="flex justify-between">
                              <Badge variant="outline" className="text-xs">
                                {ev.verification_status}
                              </Badge>
                              <span className="text-gray-500">{new Date(ev.captured_at).toLocaleTimeString()}</span>
                            </div>
                            <p className="text-gray-300 line-clamp-2">{ev.selected_passage}</p>
                            {ev.claim && (
                              <p className="text-yellow-300">Claim: {ev.claim}</p>
                            )}
                            <a
                              href={ev.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-blue-400 hover:underline"
                            >
                              {ev.domain}
                            </a>
                          </div>
                        ))}
                        {evidence.length === 0 && (
                          <p className="text-xs text-gray-500">No evidence captured yet.</p>
                        )}
                      </div>
                    </div>
                  </ScrollArea>
                </TabsContent>

                {/* Security panel */}
                <TabsContent value="security" className="flex-1 overflow-y-auto m-0">
                  <ScrollArea className="h-full">
                    <div className="p-4 space-y-4">
                      <div className="space-y-2">
                        <h3 className="text-xs font-semibold text-gray-400 uppercase">
                          Security Status
                        </h3>
                        <div className="flex items-center space-x-2">
                          <Badge
                            variant={
                              privacyMode === "agent" || privacyMode === "automation"
                                ? "default"
                                : privacyMode === "private"
                                ? "secondary"
                                : "outline"
                            }
                          >
                            Privacy: {privacyMode}
                          </Badge>
                          {activeTab?.prompt_injection_flagged && (
                            <Badge variant="destructive">Injection detected</Badge>
                          )}
                        </div>
                      </div>

                      {/* Privacy mode controls */}
                      <div className="space-y-1">
                        <h4 className="text-xs font-semibold text-gray-400 uppercase">
                          Privacy Modes
                        </h4>
                        {(["standard", "private", "research", "agent", "automation"] as PrivacyMode[]).map((mode) => (
                          <div
                            key={mode}
                            className={
                              "flex items-center justify-between p-2 rounded text-xs " +
                              (privacyMode === mode ? "bg-blue-900/20 border border-blue-700" : "bg-slate-800/20")
                            }
                          >
                            <span className={privacyMode === mode ? "text-blue-300" : "text-gray-300"}>
                              {mode}
                            </span>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-xs"
                              onClick={async () => {
                                if (activeSession) {
                                  await store.updateSession(activeSession.id, { privacy_mode: mode });
                                  setPrivacyMode(mode);
                                }
                              }}
                              disabled={privacyMode === mode}
                            >
                              {privacyMode === mode ? "Active" : "Switch"}
                            </Button>
                          </div>
                        ))}
                      </div>

                      {/* Security issues */}
                      {securityReport && (
                        <div className="space-y-1">
                          <h4 className="text-xs font-semibold text-gray-400 uppercase">
                            Security Issues ({securityReport.issue_count})
                          </h4>
                          {securityReport.security_issues.map((issue, i) => (
                            <div
                              key={i}
                              className={`p-2 rounded text-xs border ${
                                issue.severity === "critical"
                                  ? "bg-red-900/20 border-red-700 text-red-300"
                                  : "bg-orange-900/20 border-orange-700 text-orange-300"
                              }`}
                            >
                              <div className="flex justify-between">
                                <strong className="capitalize">{issue.type}</strong>
                                <Badge variant="destructive" className="text-xs">
                                  {issue.severity}
                                </Badge>
                              </div>
                              <p className="truncate">{issue.url}</p>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Autonomous browsing */}
                      <div className="space-y-2">
                        <h4 className="text-xs font-semibold text-gray-400 uppercase">
                          Autonomous Browsing
                        </h4>
                        <Button
                          size="sm"
                          variant={
                            privacyMode === "agent" || privacyMode === "automation"
                              ? "default"
                              : "outline"
                          }
                          className="w-full text-xs"
                          onClick={handleAutonomyToggle}
                        >
                          {privacyMode === "agent" || privacyMode === "automation"
                            ? "Autonomous mode ON"
                            : "Enable autonomous browsing"}
                        </Button>
                        <p className="text-xs text-gray-500">
                          High-risk actions (purchases, deletions, form submissions) require explicit confirmation.
                        </p>
                      </div>
                    </div>
                  </ScrollArea>
                </TabsContent>

                {/* Tools / Downloads panel */}
                <TabsContent value="downloads" className="flex-1 overflow-y-auto m-0">
                  <ScrollArea className="h-full">
                    <div className="p-4 space-y-4">
                      <div className="space-y-2">
                        <h3 className="text-xs font-semibold text-gray-400 uppercase">
                          Browser Tools
                        </h3>
                        <div className="grid grid-cols-2 gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-xs justify-start"
                            onClick={handleBookmark}
                          >
                            <Bookmark className="w-3 h-3 mr-1" />
                            Bookmark
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-xs justify-start"
                            onClick={() => {
                              void loadBookmarks();
                              void loadHistory();
                              void loadDownloads();
                            }}
                          >
                            <RefreshCw className="w-3 h-3 mr-1" />
                            Refresh Data
                          </Button>
                        </div>
                      </div>

                      <Separator className="bg-slate-700" />

                      {/* Downloads */}
                      <div className="space-y-2">
                        <h4 className="text-xs font-semibold text-gray-400 uppercase">
                          Downloads ({downloads.length})
                        </h4>
                        {downloads.map((dl) => (
                          <div key={dl.id} className="text-xs p-2 bg-slate-900/50 rounded space-y-1">
                            <div className="flex justify-between">
                              <span className="text-gray-300 truncate">{dl.filename}</span>
                              <Badge variant="outline" className="text-xs">
                                {dl.status}
                              </Badge>
                            </div>
                            <div className="text-gray-500">
                              {(dl.size_bytes / 1024).toFixed(1)} KB • {dl.risk_level}
                            </div>
                          </div>
                        ))}
                        {downloads.length === 0 && (
                          <p className="text-xs text-gray-500">No downloads yet.</p>
                        )}
                      </div>

                      <Separator className="bg-slate-700" />

                      {/* History */}
                      <div className="space-y-2">
                        <h4 className="text-xs font-semibold text-gray-400 uppercase">
                          History ({history.length})
                        </h4>
                        {history.slice(0, 15).map((h) => (
                          <div key={h.id} className="flex items-center space-x-2 text-xs">
                            <Clock className="w-3 h-3 text-gray-500" />
                            <a
                              href={h.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-gray-300 hover:text-blue-400 truncate flex-1"
                              title={h.url}
                            >
                              {h.title || h.url}
                            </a>
                          </div>
                        ))}
                        {history.length === 0 && (
                          <p className="text-xs text-gray-500">No history yet.</p>
                        )}
                      </div>

                      <Separator className="bg-slate-700" />

                      {/* Bookmarks */}
                      <div className="space-y-2">
                        <h4 className="text-xs font-semibold text-gray-400 uppercase">
                          Bookmarks ({bookmarks.length})
                        </h4>
                        {bookmarks.slice(0, 15).map((bm) => (
                          <div key={bm.id} className="flex items-center space-x-2 text-xs">
                            <Bookmark className="w-3 h-3 text-gray-400" />
                            <a
                              href={bm.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-gray-300 hover:text-blue-400 truncate flex-1"
                              title={bm.url}
                            >
                              {bm.title}
                            </a>
                            {bm.tags.length > 0 && (
                              <Badge variant="outline" className="text-xs">
                              {bm.tags[0]}
                            </Badge>
                            )}
                          </div>
                        ))}
                        {bookmarks.length === 0 && (
                          <p className="text-xs text-gray-500">No bookmarks yet.</p>
                        )}
                      </div>
                    </div>
                  </ScrollArea>
                </TabsContent>

                {/* Network Inspector Panel (spec §51) */}
                <TabsContent value="network-diagnostics" className="flex-1 overflow-y-auto m-0">
                  <ScrollArea className="h-full">
                    <div className="p-4 space-y-4">
                      {/* Browser Health Summary */}
                      <div className="space-y-2">
                        <h3 className="text-sm font-medium text-gray-300">Browser Health</h3>
                        {browserHealth ? (
                          <div className="space-y-1">
                            <Badge
                              variant={
                                browserHealth.overall === 'healthy' ? 'default' :
                                browserHealth.overall === 'degraded' ? 'secondary' : 'destructive'
                              }
                              className="text-xs"
                            >
                              {browserHealth.overall.toUpperCase()}
                            </Badge>
                            <div className="space-y-1 mt-2">
                              {browserHealth.checks.map((check, idx) => (
                                <div key={idx} className="flex items-center justify-between text-xs">
                                  <span className="text-gray-400">{check.name}</span>
                                  <span className={`flex items-center ${check.passed ? 'text-green-400' : 'text-red-400'}`}>
                                    {check.passed ? <CheckCircle className="w-3 h-3 mr-1" /> : <AlertTriangle className="w-3 h-3 mr-1" />}
                                    {check.passed ? 'PASS' : 'FAIL'}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void checkBrowserHealth()}
                            className="text-xs"
                          >
                            Run health check
                          </Button>
                        )}
                      </div>

                      <Separator />

                      {/* Network Events */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <h3 className="text-sm font-medium text-gray-300">Recent Network Events ({networkEvents.length})</h3>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => void loadNetworkEvents()}
                            className="text-xs h-6"
                          >
                            <RefreshCw className="w-3 h-3" />
                          </Button>
                        </div>
                        {networkEvents.length > 0 ? (
                          <div className="space-y-1">
                            {networkEvents.slice(0, 20).map((evt) => (
                              <div key={evt.id} className="text-xs p-2 bg-slate-800/30 rounded border border-slate-700">
                                <div className="flex items-center justify-between">
                                  <Badge
                                    variant={
                                      evt.severity === 'error' ? 'destructive' :
                                      evt.severity === 'warning' ? 'secondary' : 'outline'
                                    }
                                    className="text-xs"
                                  >
                                    {evt.type}
                                  </Badge>
                                  <span className={`text-xs ${
                                    evt.category ? 'text-orange-400' : 'text-gray-500'
                                  }`}>
                                    {evt.category || 'NO_CATEGORY'}
                                  </span>
                                </div>
                                <div className="text-gray-400 mt-1 break-all">{evt.url}</div>
                                <div className="text-gray-500 mt-1">{evt.detail}</div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-gray-500">No network events recorded.</p>
                        )}
                      </div>

                      <Separator />

                      {/* Diagnostics Actions */}
                      <div className="space-y-2">
                        <h3 className="text-sm font-medium text-gray-300">Run Diagnostics</h3>
                        {activeTab && activeTab.url && activeTab.url !== "about:blank" ? (
                          <div className="flex flex-col space-y-2">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void runNetworkDiagnostics(activeTab.url, 10.0)}
                              disabled={isLoading}
                              className="text-xs justify-start"
                            >
                              Full network diagnostics
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void runDnsDiagnostics(activeTab.url)}
                              className="text-xs justify-start"
                            >
                              DNS diagnostics
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void runProxyDiagnostics(activeTab.url)}
                              className="text-xs justify-start"
                            >
                              Proxy diagnostics
                            </Button>
                          </div>
                        ) : (
                          <p className="text-xs text-gray-500">Navigate to a URL to run diagnostics.</p>
                        )}
                      </div>

                      {/* Diagnostics Result */}
                      {lastDiagnosticsResult && (
                        <>
                          <Separator />

                          <div className="space-y-2">
                            <h3 className="text-sm font-medium text-gray-300">Diagnostic Result</h3>
                            <div className="space-y-1 text-xs">
                              <div className="flex justify-between">
                                <span className="text-gray-400">URL:</span>
                                <span className="text-gray-300 break-all">{lastDiagnosticsResult.url}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-gray-400">Category:</span>
                                <Badge variant="secondary" className="text-xs">
                                  {lastDiagnosticsResult.error_category}
                                </Badge>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-gray-400">Diagnosis:</span>
                                <span className="text-gray-300">{lastDiagnosticsResult.diagnosis}</span>
                              </div>
                              {lastDiagnosticsResult.recommendations && lastDiagnosticsResult.recommendations.length > 0 && (
                                <div className="mt-2">
                                  <span className="text-gray-400">Recommendations:</span>
                                  <ul className="list-disc list-inside text-gray-300 ml-2 mt-1">
                                    {lastDiagnosticsResult.recommendations.map((rec, idx) => (
                                      <li key={idx}>{rec}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {lastDiagnosticsResult.recovery_plan && (
                                <div className="mt-2 p-2 bg-slate-800/30 rounded border border-slate-700">
                                  <div className="flex justify-between items-center">
                                    <span className="text-gray-400">Recovery:</span>
                                    <Badge variant="outline" className="text-xs">
                                      {lastDiagnosticsResult.recovery_plan.action} (max {lastDiagnosticsResult.recovery_plan.max_attempts})
                                    </Badge>
                                  </div>
                                  <p className="text-gray-400 mt-1">{lastDiagnosticsResult.recovery_plan.description}</p>
                                  {lastDiagnosticsResult.recovery_plan.safe ? (
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      onClick={() => void recoverNavigation(activeTab?.url ?? '', 'auto', lastDiagnosticsResult.recovery_plan?.max_attempts ?? 3)}
                                      disabled={isRecovering}
                                      className="text-xs mt-2"
                                    >
                                      {isRecovering ? 'Recovering...' : 'Attempt recovery'}
                                    </Button>
                                  ) : (
                                    <p className="text-xs text-yellow-400 mt-1">Recovery requires manual intervention.</p>
                                  )}
                                </div>
                              )}
                              {recoveryError && (
                                <p className="text-xs text-red-400">{recoveryError}</p>
                              )}
                            </div>
                          </div>
                        </>
                      )}

                      <Separator />

                      {/* Navigation Timeline */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <h3 className="text-sm font-medium text-gray-300">Navigation Timeline ({navigationTimeline.length})</h3>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => void loadNavigationTimeline()}
                            className="text-xs h-6"
                          >
                            <RefreshCw className="w-3 h-3" />
                          </Button>
                        </div>
                        {navigationTimeline.length > 0 ? (
                          <div className="space-y-1">
                            {navigationTimeline.slice(0, 20).map((entry) => (
                              <div key={entry.id} className="text-xs p-2 bg-slate-800/30 rounded border border-slate-700">
                                <div className="flex justify-between">
                                  <span className="text-gray-400">{entry.action}</span>
                                  <span className="text-gray-500">{entry.timestamp}</span>
                                </div>
                                {entry.category && (
                                  <Badge variant="secondary" className="text-xs mt-1">
                                    {entry.category}
                                  </Badge>
                                )}
                                <div className="text-gray-400 mt-1 break-all">{entry.url}</div>
                                {entry.detail && <div className="text-gray-500 mt-1">{entry.detail}</div>}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-gray-500">No navigation timeline entries.</p>
                        )}
                      </div>
                    </div>
                  </ScrollArea>
                </TabsContent>

              </Tabs>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
