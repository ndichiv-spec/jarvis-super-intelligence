"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Globe, RefreshCw, Plus, X, Download, Search,
  Settings, Eye, EyeOff, Shield, ShieldAlert, Bookmark,
  Clock, FileText, ExternalLink, Maximize2, Minimize2,
  AlertTriangle, CheckCircle, HelpCircle, Brain,
  PanelLeft, PanelRight, ChevronLeft, ChevronRight,
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
    goBack,
    goForward,
    reload,
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
  const [urlDraft, setUrlDraft] = useState<{ tabId: string | null; value: string }>({
    tabId: null,
    value: "",
  });
  const setUrlInput = useCallback((value: string) => {
    setUrlDraft({ tabId: activeTabId, value });
  }, [activeTabId]);
  const [searchInput, setSearchInput] = useState("");
  const [evidenceInput, setEvidenceInput] = useState<{ selected_passage: string; claim: string }>(
    { selected_passage: "", claim: "" }
  );
  const [showRightPanel, setShowRightPanel] = useState(false);
  const [rightPanelTab, setRightPanelTab] = useState("ai-context");
  const [readerTabId, setReaderTabId] = useState<string | null>(null);
  const lastInitialUrl = useRef<string | null>(null);

  // ---- Initialization ----
  useEffect(() => {
    if (!initialized) {
      void init();
    }
  }, [init, initialized]);

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
      const tab = await createTab(sess.id, "about:blank");
      if (tab) {
        await setActiveTab(tab.id);
      }
    } else if (!activeTabId && sess && sess.tabs.length > 0) {
      await setActiveTab(sess.tabs[0]);
    }
  }, [
    activeSessionId, sessions, activeTabId, privacyMode,
    createSession, setActiveSession, createTab, setActiveTab,
  ]);

  useEffect(() => {
    void ensureSessionAndTab();
  }, [ensureSessionAndTab]);

  useEffect(() => {
    if (!initialUrl) {
      lastInitialUrl.current = null;
      return;
    }
    if (!activeSessionId || !activeTabId || lastInitialUrl.current === initialUrl) return;

    lastInitialUrl.current = initialUrl;
    setReaderTabId(null);
    void navigate(activeSessionId, initialUrl, activeTabId, privacyMode).then((result) => {
      if (result?.blocked) {
        toast.error(`Navigation blocked: ${result.reason}`, {
          description: "Security policy prevented this navigation.",
        });
        return;
      }
      if (result?.navigated) {
        const navigatedUrl = result.url ?? initialUrl;
        setUrlInput(navigatedUrl);
        window.setTimeout(() => void extractPage(navigatedUrl), 1000);
      }
    });
  }, [initialUrl, activeSessionId, activeTabId, navigate, privacyMode, extractPage, setUrlInput]);

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
  const readerMode = activeTabId !== null && readerTabId === activeTabId;
  const urlInput = activeTab?.id === urlDraft.tabId ? urlDraft.value : activeTab?.url || "";

  useEffect(() => {
    if (activeSession?.privacy_mode && privacyMode !== activeSession.privacy_mode) {
      setPrivacyMode(activeSession.privacy_mode);
    }
  }, [activeSession?.id, activeSession?.privacy_mode, privacyMode, setPrivacyMode]);

  // ---- Event handlers ----

  const handleNavigate = useCallback(async () => {
    if (!urlInput.trim() || !activeSessionId || !activeTabId) return;

    setReaderTabId(null);
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
  }, [urlInput, activeSessionId, activeTabId, navigate, privacyMode, extractPage, setUrlInput]);

  const handleUrlKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      void handleNavigate();
    }
  }, [handleNavigate]);

  const handleNavigationControl = useCallback(async (action: "back" | "forward" | "reload") => {
    const moved = action === "back"
      ? await goBack()
      : action === "forward"
        ? await goForward()
        : await reload();
    if (!moved) {
      if (!useBrowserStore.getState().error && action !== "reload") {
        toast.info(action === "back" ? "No earlier page in this tab." : "No forward page in this tab.");
      }
      return;
    }

    const current = useBrowserStore.getState();
    const currentTab = current.activeTabId ? current.tabs[current.activeTabId] : undefined;
    if (!currentTab) return;
    setUrlInput(currentTab.url);
    clearAIContext();
    await Promise.all([
      loadHistory(),
      loadNavigationTimeline(current.activeSessionId ?? undefined),
    ]);
    if (/^https?:\/\//i.test(currentTab.url)) {
      void extractPage(currentTab.url);
    }
  }, [goBack, goForward, reload, clearAIContext, loadHistory, loadNavigationTimeline, extractPage, setUrlInput]);

  const handleNewTab = useCallback(async () => {
    if (!activeSession) return;
    const tab = await createTab(activeSession.id, "about:blank");
    if (tab) {
      await setActiveTab(tab.id);
    }
  }, [activeSession, createTab, setActiveTab]);

  const handleCloseTab = useCallback(async (tabId: string) => {
    await closeTab(tabId);
  }, [closeTab]);

  const handleTabClick = useCallback((tabId: string) => {
    setActiveTab(tabId);
  }, [setActiveTab]);

  const handleSearch = useCallback(async () => {
    const query = searchInput.trim();
    if (!query) return;
    if (!activeSession) return;
    const results = await search(query, activeSession.id);
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

  const handleOpenInTab = useCallback(async (url: string, title?: string) => {
    if (!activeSession || !/^https?:\/\//i.test(url)) {
      toast.error("Only HTTP and HTTPS pages can be opened in JARVIS Browser.");
      return;
    }
    const tab = await createTab(activeSession.id, "about:blank", title);
    if (!tab) return;

    const result = await navigate(activeSession.id, url, tab.id, privacyMode);
    if (!result?.navigated) {
      await closeTab(tab.id);
      if (result?.blocked) {
        toast.error(`Navigation blocked: ${result.reason}`, {
          description: "Security policy prevented this navigation.",
        });
      }
      return;
    }

    setReaderTabId(null);
    const openedUrl = result.url ?? url;
    window.setTimeout(() => void extractPage(openedUrl), 1000);
  }, [activeSession, createTab, navigate, privacyMode, closeTab, extractPage]);

  const handleReaderMode = useCallback(async () => {
    if (!activeTab) return;
    if (readerMode) {
      setReaderTabId(null);
      return;
    }
    if (!/^https?:\/\//i.test(activeTab.url)) {
      toast.error("Navigate to an HTTP or HTTPS page before opening Reader view.");
      return;
    }
    const context = await extractPage(activeTab.url);
    if (context) setReaderTabId(activeTab.id);
  }, [activeTab, extractPage, readerMode]);

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

  return (
    <div className={`flex flex-col h-full ${compact ? "text-sm" : ""}`}>
      {/* Top navigation / address bar */}
      <div className="flex flex-col gap-2 p-2 sm:p-3 border-b border-slate-700 bg-slate-800/50 min-w-0">
        {/* Session selector + new tab */}
        <div className="flex items-center gap-2 min-w-0">
          <select
            value={activeSessionId ?? ""}
            onChange={(e) => {
              void setActiveSession(e.target.value || null);
            }}
            aria-label="Browser session"
            className="min-w-0 max-w-[55vw] text-sm bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
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
                  variant={readerMode ? "secondary" : "ghost"}
                  className="h-7 w-7 p-0"
                  onClick={() => void handleReaderMode()}
                  disabled={!activeTab || isLoading}
                  aria-label={readerMode ? "Show webpage" : "Read page in JARVIS"}
                >
                  <FileText className="w-4 h-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{readerMode ? "Show webpage" : "Read page in JARVIS"}</TooltipContent>
            </Tooltip>
          </TooltipProvider>

          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleNewTab}
                  disabled={!activeSession || isLoading}
                  className="h-7 w-7 p-0"
                  aria-label="New tab"
                >
                  <Plus className="w-4 h-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>New tab</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        {/* Tab bar */}
        <div role="tablist" aria-label="Open browser tabs" className="flex items-center space-x-1 overflow-x-auto min-w-0">
          {visibleTabs?.map((tab) => (
            <div
              key={tab.id}
              role="tab"
              aria-selected={tab.id === activeTabId}
              tabIndex={0}
              className={
                "flex items-center space-x-1 px-3 py-1 rounded-t-lg text-sm cursor-pointer transition-all " +
                (tab.id === activeTabId
                  ? "bg-slate-700 text-white border-t-2 border-blue-400"
                  : "bg-slate-800/30 text-gray-400 hover:text-gray-300")
              }
              onClick={() => handleTabClick(tab.id)}
              onKeyDown={(event) => {
                if (event.target !== event.currentTarget) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  handleTabClick(tab.id);
                }
              }}
              onContextMenu={(e) => {
                e.preventDefault();
                void handleCloseTab(tab.id);
              }}
              title={tab.url}
            >
              {tab.prompt_injection_flagged && (
                <ShieldAlert className="w-3 h-3 mr-1 text-red-400" />
              )}
              <span className="max-w-[150px] truncate">
                {tab.title || "Untitled"}
              </span>
              {!tab.id.endsWith("about:blank") && (
                <Globe className="w-3 h-3 ml-1 opacity-50" />
              )}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  void handleCloseTab(tab.id);
                }}
                aria-label={`Close ${tab.title || "untitled"} tab`}
                className="ml-1 hover:text-red-400"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          )) ?? []}
        </div>

        {/* Address bar + controls */}
        <div className="flex flex-wrap items-center gap-2 min-w-0">
          <div className="relative flex items-center flex-1 min-w-[150px]">
            {activeTab?.prompt_injection_flagged && (
              <ShieldAlert className="absolute left-2 w-4 h-4 text-red-400 z-10" />
            )}
            <Input
              aria-label="Website address or search"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyDown={handleUrlKeyDown}
              placeholder="Enter URL or search..."
              className={
                "w-full min-w-0 text-sm bg-slate-700 border-slate-600 text-white " +
                (activeTab?.prompt_injection_flagged ? "border-red-500 pl-8" : "")
              }
              readOnly={isLoading}
            />
            {activeTab?.is_loading && (
              <RefreshCw className="absolute right-2 w-4 h-4 animate-spin text-gray-400" />
            )}
          </div>

          <div role="group" aria-label="Browser controls" className="flex items-center space-x-1 shrink-0">
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
                <TooltipContent>
                  {privacyMode === "private"
                    ? "Private mode does not save new visits to browser history. Existing history is retained."
                    : privacyMode === "authenticated"
                      ? "Authenticated mode uses server-side provider access; credentials are not exposed to the website."
                      : `Browser mode: ${privacyMode}`}
                </TooltipContent>
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
                    onClick={() => void handleNavigationControl("back")}
                    disabled={!activeTab || isLoading}
                    aria-label="Back"
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
                    onClick={() => void handleNavigationControl("forward")}
                    disabled={!activeTab || isLoading}
                    aria-label="Forward"
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
                    onClick={() => void handleNavigationControl("reload")}
                    disabled={isLoading}
                    aria-label="Reload"
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
                      aria-label="Show AI context panel"
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
                      aria-label="Hide AI context panel"
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
                    aria-label="Browser settings"
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

      <div
        role="status"
        aria-label="Browser session and website status"
        className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 px-3 py-1.5 border-b border-slate-800 bg-slate-950 text-[11px] text-slate-300"
      >
        <span className="flex min-w-0 items-center gap-2">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400" aria-hidden="true" />
          <span className="font-medium text-cyan-200">JARVIS session</span>
          <span className="truncate">{activeSession?.name || "No session"} · {privacyMode} mode</span>
        </span>
        <span className="flex min-w-0 items-center gap-2 text-slate-400">
          <Globe className="h-3 w-3 shrink-0" aria-hidden="true" />
          <span className="truncate">Embedded website view · {activeTab?.title || activeTab?.url || "No active page"}</span>
        </span>
      </div>

      {/* Main workspace */}
      <div className="relative flex flex-1 min-h-0 overflow-hidden">
        {/* Page viewport */}
        <div className="flex-1 relative bg-slate-900">
          {readerMode && aiContext ? (
            <article className="h-full overflow-y-auto bg-slate-950 px-6 py-8 text-slate-200">
              <div className="mx-auto max-w-3xl space-y-4">
                <p className="text-xs text-slate-400">{aiContext.metadata.url}</p>
                <h1 className="text-2xl font-semibold text-white">
                  {aiContext.metadata.title || activeTab?.title || "Readable page"}
                </h1>
                {aiContext.metadata.description && (
                  <p className="text-sm text-slate-400">{aiContext.metadata.description}</p>
                )}
                <Separator className="bg-slate-700" />
                <div className="whitespace-pre-wrap break-words text-sm leading-7">
                  {aiContext.text || "No readable text was found on this page."}
                </div>
              </div>
            </article>
          ) : activeTab ? (
            <iframe
              key={`${activeTab.id}:${activeTab.navigation_revision ?? 0}`}
              src={activeTab.url === "about:blank" ? "about:blank" : activeTab.url}
              title={activeTab.title || "JARVIS Browser"}
              className="w-full h-full border-none"
              sandbox={
                privacyMode === "private" || privacyMode === "authenticated"
                  ? "allow-scripts allow-same-origin allow-forms"
                  : "allow-scripts allow-same-origin allow-forms allow-popups"
              }
              onLoad={() => {
                const current = useBrowserStore.getState();
                const loadedTab = current.activeTabId ? current.tabs[current.activeTabId] : undefined;
                if (activeTab && current.activeTabId === activeTab.id && loadedTab?.is_loading) {
                  useBrowserStore.setState((state) => ({
                    tabs: {
                      ...state.tabs,
                      [loadedTab.id]: { ...loadedTab, is_loading: false },
                    },
                  }));
                }
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
              animate={{ width: "min(400px, 100vw)", opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-y-0 right-0 z-20 flex w-full flex-col border-l border-slate-700 bg-slate-900/95 overflow-hidden md:static md:z-auto md:w-[400px] md:bg-slate-800/30"
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
                                <button
                                  type="button"
                                  onClick={() => void handleOpenInTab(aiContext.metadata.url, aiContext.metadata.title)}
                                  className="ml-1 truncate text-left text-blue-400 hover:underline"
                                >
                                  {aiContext.metadata.url}
                                </button>
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
                        <label
                          className="block text-xs font-semibold text-gray-400 uppercase"
                          htmlFor="browser-search-query"
                        >
                          Search the web and JARVIS
                        </label>
                        <div className="flex space-x-2">
                          <Input
                            id="browser-search-query"
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
                            <button
                              type="button"
                              onClick={() => void handleOpenInTab(result.url, result.title)}
                              className="text-left text-sm text-blue-400 hover:underline"
                            >
                              {result.title}
                            </button>
                            <p className="text-xs text-gray-400">{result.snippet}</p>
                            <div className="flex items-center space-x-2">
                              <Badge variant="outline" className="text-xs">
                                {result.source}
                              </Badge>
                              <span className="text-xs text-gray-500">{result.domain}</span>
                            </div>
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
                            <button
                              type="button"
                              onClick={() => void handleOpenInTab(ev.url, ev.title)}
                              className="text-left text-xs text-blue-400 hover:underline"
                            >
                              {ev.domain}
                            </button>
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
                        <p className="text-xs leading-relaxed text-slate-400">
                          Private keeps newly visited URLs out of saved history; it does not delete visits saved earlier.
                          Authenticated uses server-side provider access without exposing provider credentials to websites.
                        </p>
                        {(["standard", "private", "research", "agent", "automation", "authenticated"] as PrivacyMode[]).map((mode) => (
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
                                  const updated = await store.updateSession(activeSession.id, { privacy_mode: mode });
                                  if (updated) setPrivacyMode(updated.privacy_mode);
                                }
                              }}
                              disabled={privacyMode === mode}
                              aria-label={`${privacyMode === mode ? "Current" : "Switch to"} ${mode} mode`}
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
                        {privacyMode === "private" && (
                          <p className="text-xs leading-relaxed text-slate-400">
                            Private mode stops saving new visits to history. Earlier saved history is retained and shown here.
                          </p>
                        )}
                        {history.slice(0, 15).map((h) => (
                          <div key={h.id} className="flex items-center space-x-2 text-xs">
                            <Clock className="w-3 h-3 text-gray-500" />
                            <button
                              type="button"
                              onClick={() => void handleOpenInTab(h.url, h.title)}
                              className="flex-1 truncate text-left text-gray-300 hover:text-blue-400"
                              title={h.url}
                            >
                              {h.title || h.url}
                            </button>
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
                            <button
                              type="button"
                              onClick={() => void handleOpenInTab(bm.url, bm.title)}
                              className="flex-1 truncate text-left text-gray-300 hover:text-blue-400"
                              title={bm.url}
                            >
                              {bm.title}
                            </button>
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
