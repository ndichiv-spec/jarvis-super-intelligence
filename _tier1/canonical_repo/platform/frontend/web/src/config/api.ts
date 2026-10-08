import env from './env';

const API_PREFIX = '/api/v1';

export const API_ENDPOINTS = {
  health: `${env.API_URL}/health`,

  auth: {
    login: `${env.API_URL}${API_PREFIX}/auth/login`,
    register: `${env.API_URL}${API_PREFIX}/auth/register`,
    logout: `${env.API_URL}${API_PREFIX}/auth/logout`,
    me: `${env.API_URL}${API_PREFIX}/auth/me`,
    forgotPassword: `${env.API_URL}${API_PREFIX}/auth/forgot-password`,
    resetPassword: `${env.API_URL}${API_PREFIX}/auth/reset-password`,
    changePassword: `${env.API_URL}${API_PREFIX}/auth/change-password`,
    sessions: `${env.API_URL}${API_PREFIX}/auth/sessions`,
    apiKeys: `${env.API_URL}${API_PREFIX}/auth/api-keys`,
  },

  chat: {
    send: `${env.API_URL}/api/chat`,
    stream: `${env.API_URL}/api/chat/stream`,
    generate: `${env.API_URL}${API_PREFIX}/ai/generate`,
    feedback: `${env.API_URL}/api/chat/messages`,
    status: `${env.API_URL}${API_PREFIX}/ai/status`,
    sessions: `${env.API_URL}/api/chat/sessions`,
    history: (sessionId: string) => `${env.API_URL}/api/chat/history/${sessionId}`,
    export: (sessionId: string) => `${env.API_URL}/api/chat/sessions/${sessionId}/export`,
    regenerate: (sessionId: string, messageId: string) =>
      `${env.API_URL}/api/chat/messages/${sessionId}/${messageId}/regenerate`,
    feedbackMessage: (sessionId: string, messageId: string) =>
      `${env.API_URL}/api/chat/messages/${sessionId}/${messageId}/feedback`,
    restore: (sessionId: string) =>
      `${env.API_URL}/api/chat/sessions/${sessionId}/restore`,
    editAndResend: (sessionId: string, messageId: string) =>
      `${env.API_URL}/api/chat/messages/${sessionId}/${messageId}/resend`,
    switchModel: `${env.API_URL}/api/chat/switch`,
  },

  agents: {
    list: `${env.API_URL}${API_PREFIX}/agents`,
    task: `${env.API_URL}${API_PREFIX}/agents/task`,
    tasks: `${env.API_URL}${API_PREFIX}/agents/tasks`,
    stats: `${env.API_URL}${API_PREFIX}/agents/stats`,
    scheduler: `${env.API_URL}${API_PREFIX}/agents/scheduler/status`,
    schedulerToggle: `${env.API_URL}${API_PREFIX}/agents/scheduler/toggle`,
    executions: `${env.API_URL}${API_PREFIX}/agents/executions`,
    collaboration: {
      agents: `${env.API_URL}${API_PREFIX}/agents/collaboration/agents/list`,
      tasks: `${env.API_URL}${API_PREFIX}/agents/collaboration/tasks/list`,
      create: `${env.API_URL}${API_PREFIX}/agents/collaboration/task/create`,
      execute: `${env.API_URL}${API_PREFIX}/agents/collaboration/task/execute`,
      metrics: `${env.API_URL}${API_PREFIX}/agents/collaboration/metrics`,
      selfOrganize: `${env.API_URL}${API_PREFIX}/agents/collaboration/self-organize`,
    },
    serviceTailoring: `${env.API_URL}${API_PREFIX}/agents/service-tailoring`,
  },

  monitoring: {
    healthReport: `${env.API_URL}${API_PREFIX}/monitoring/health-report`,
    metrics: `${env.API_URL}${API_PREFIX}/monitoring/metrics`,
    optimizationReport: `${env.API_URL}${API_PREFIX}/monitoring/optimization-report`,
    optimize: `${env.API_URL}${API_PREFIX}/monitoring/optimize`,
    diagnostics: `${env.API_URL}${API_PREFIX}/monitoring/system/diagnostics`,
    recoveryHistory: `${env.API_URL}${API_PREFIX}/monitoring/recovery-history`,
    triggerRecovery: `${env.API_URL}${API_PREFIX}/monitoring/trigger-recovery`,
  },

  integrations: {
    providers: `${env.API_URL}${API_PREFIX}/integrations/providers`,
  },

  connectors: {
    list: `${env.API_URL}${API_PREFIX}/connectors`,
    activity: `${env.API_URL}${API_PREFIX}/connectors/activity`,
    github: {
      connection: `${env.API_URL}${API_PREFIX}/connectors/github/connection`,
      authorize: `${env.API_URL}${API_PREFIX}/connectors/github/oauth/authorize`,
      test: `${env.API_URL}${API_PREFIX}/connectors/github/test`,
      repositories: (page = 1) =>
        `${env.API_URL}${API_PREFIX}/connectors/github/repositories?page=${page}`,
      repository: (owner: string, name: string) =>
        `${env.API_URL}${API_PREFIX}/connectors/github/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`,
      file: (owner: string, name: string, path: string) =>
        `${env.API_URL}${API_PREFIX}/connectors/github/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/contents?path=${encodeURIComponent(path)}`,
      disconnect: `${env.API_URL}${API_PREFIX}/connectors/github/connection`,
    },
  },

  system: {
    status: `${env.API_URL}${API_PREFIX}/system/status`,
    capabilities: `${env.API_URL}${API_PREFIX}/system/capabilities`,
    processes: `${env.API_URL}${API_PREFIX}/system/processes`,
    providerSettings: `${env.API_URL}${API_PREFIX}/system/provider-settings`,
    files: `${env.API_URL}${API_PREFIX}/system/files`,
  },

  voice: {
    speak: `${env.API_URL}${API_PREFIX}/voice/speak`,
    listen: `${env.API_URL}${API_PREFIX}/voice/listen`,
    transcribe: `${env.API_URL}${API_PREFIX}/voice/transcribe`,
    profiles: `${env.API_URL}${API_PREFIX}/voice/profile`,
    voices: `${env.API_URL}${API_PREFIX}/voice/voices`,
    status: `${env.API_URL}${API_PREFIX}/voice/status`,
  },

  memory: {
    store: `${env.API_URL}${API_PREFIX}/cognitive/memory/store`,
    recall: `${env.API_URL}${API_PREFIX}/cognitive/memory/recall`,
    stats: `${env.API_URL}${API_PREFIX}/cognitive/memory/stats`,
    consolidate: `${env.API_URL}${API_PREFIX}/cognitive/memory/consolidate`,
    cognitiveReport: `${env.API_URL}${API_PREFIX}/cognitive/consciousness/report`,
    cognitiveProcess: `${env.API_URL}${API_PREFIX}/cognitive/process`,
    emotionAnalyze: `${env.API_URL}${API_PREFIX}/cognitive/emotion/analyze`,
    knowledgeGraph: `${env.API_URL}${API_PREFIX}/cognitive/knowledge/search`,
  },

  automation: {
    tasks: `${env.API_URL}${API_PREFIX}/automation`,
    runTask: (taskId: string) => `${env.API_URL}${API_PREFIX}/automation/task/${taskId}/run`,
  },

  knowledge: {
    search: `${env.API_URL}${API_PREFIX}/knowledge/search`,
    entries: `${env.API_URL}${API_PREFIX}/knowledge`,
    patterns: `${env.API_URL}${API_PREFIX}/knowledge/patterns`,
  },

  stark: {
    chat: `${env.API_URL}${API_PREFIX}/stark/chat`,
    tool: `${env.API_URL}${API_PREFIX}/stark/tool`,
    status: `${env.API_URL}${API_PREFIX}/stark/status`,
    health: `${env.API_URL}${API_PREFIX}/stark/health`,
  },

  global: {
    knowledgeSearch: `${env.API_URL}${API_PREFIX}/global/knowledge/global/search`,
    trends: `${env.API_URL}${API_PREFIX}/global/knowledge/global/trends`,
    codeSearch: `${env.API_URL}${API_PREFIX}/global/knowledge/global/code`,
    sources: `${env.API_URL}${API_PREFIX}/global/knowledge/global/sources`,
    observationStatus: `${env.API_URL}${API_PREFIX}/global/observation/status`,
    observationReport: `${env.API_URL}${API_PREFIX}/global/observation/report`,
    observationEvents: `${env.API_URL}${API_PREFIX}/global/observation/events`,
    observationMetrics: `${env.API_URL}${API_PREFIX}/global/observation/metrics`,
    rssFeeds: `${env.API_URL}${API_PREFIX}/global/rss/feeds`,
    rssLatest: `${env.API_URL}${API_PREFIX}/global/rss/latest`,
    rssRefresh: `${env.API_URL}${API_PREFIX}/global/rss/refresh`,
  },

  rbac: {
    users: `${env.API_URL}${API_PREFIX}/rbac/users`,
    roles: `${env.API_URL}${API_PREFIX}/rbac/roles`,
    permissions: `${env.API_URL}${API_PREFIX}/rbac/permissions`,
    auditLogs: `${env.API_URL}${API_PREFIX}/rbac/audit-logs`,
    tenantSettings: `${env.API_URL}${API_PREFIX}/rbac/tenant/settings`,
  },

  llm: {
    chat: `${env.API_URL}${API_PREFIX}/llm/chat`,
    status: `${env.API_URL}${API_PREFIX}/llm/status`,
  },

  models: {
    catalog: `${env.API_URL}${API_PREFIX}/ai/models`,
    status: `${env.API_URL}${API_PREFIX}/ai/status`,
  },

  browser: {
    sessions: `${env.API_URL}${API_PREFIX}/browser/sessions`,
    tabs: `${env.API_URL}${API_PREFIX}/browser/tabs`,
    navigate: `${env.API_URL}${API_PREFIX}/browser/navigate`,
    extract: `${env.API_URL}${API_PREFIX}/browser/extract`,
    search: `${env.API_URL}${API_PREFIX}/browser/search`,
    status: `${env.API_URL}${API_PREFIX}/browser/status`,
    page: `${env.API_URL}${API_PREFIX}/browser/page`,
    autonomous: `${env.API_URL}${API_PREFIX}/browser/autonomous`,
    security: {
      promptInjection: `${env.API_URL}${API_PREFIX}/browser/security/prompt-injection`,
      report: `${env.API_URL}${API_PREFIX}/browser/security/report`,
      highRiskDom: `${env.API_URL}${API_PREFIX}/browser/security/high-risk-dom`,
    },
    // Evidence → Knowledge / Mission / Memory (spec §27–31)
    evidencePromote: (evidenceId: string) => `${env.API_URL}${API_PREFIX}/browser/evidence/${evidenceId}/promote`,
    evidenceToMission: (evidenceId: string) => `${env.API_URL}${API_PREFIX}/browser/evidence/${evidenceId}/to-mission`,
    evidenceToMemory: (evidenceId: string) => `${env.API_URL}${API_PREFIX}/browser/evidence/${evidenceId}/to-memory`,
    // Mission integration
    missions: {
      context: (missionId: string) => `${env.API_URL}${API_PREFIX}/browser/missions/${missionId}/context`,
      browserTask: (missionId: string) => `${env.API_URL}${API_PREFIX}/browser/missions/${missionId}/browser-task`,
    },
    evidence: `${env.API_URL}${API_PREFIX}/browser/evidence`,
    history: `${env.API_URL}${API_PREFIX}/browser/history`,
    bookmarks: `${env.API_URL}${API_PREFIX}/browser/bookmarks`,
    downloads: `${env.API_URL}${API_PREFIX}/browser/downloads`,
    // Browser AI-native execution layer (spec §3–§42)
    actions: `${env.API_URL}${API_PREFIX}/browser/actions`,
    observeAct: `${env.API_URL}${API_PREFIX}/browser/observe-act`,
    pageState: `${env.API_URL}${API_PREFIX}/browser/page-state`,
    tasks: `${env.API_URL}${API_PREFIX}/browser/tasks`,
    taskPlan: (taskId: string) => `${env.API_URL}${API_PREFIX}/browser/tasks/${taskId}/plan`,
    workspaces: `${env.API_URL}${API_PREFIX}/browser/workspaces`,
    telemetry: `${env.API_URL}${API_PREFIX}/browser/telemetry`,
    sourceGraph: `${env.API_URL}${API_PREFIX}/browser/source-graph`,
    timeline: `${env.API_URL}${API_PREFIX}/browser/timeline`,
    // Model routing (spec §9, §44)
    modelRoute: `${env.API_URL}${API_PREFIX}/browser/model-route`,
    // Auth state (spec §19)
    authState: `${env.API_URL}${API_PREFIX}/browser/auth-state`,
    // Remote browser (spec §40)
    remoteBrowser: {
      status: `${env.API_URL}${API_PREFIX}/browser/remote-browser/status`,
      sessions: `${env.API_URL}${API_PREFIX}/browser/remote-browser/sessions`,
    },
    // Summon browser (spec §49)
    summon: `${env.API_URL}${API_PREFIX}/browser/summon`,
    // Artifacts (spec §50)
    artifacts: `${env.API_URL}${API_PREFIX}/browser/artifacts`,
    // Resource usage (spec §41)
    resourceUsage: `${env.API_URL}${API_PREFIX}/browser/resource-usage`,
    // Network Intelligence Layer — diagnostics (spec §51)
    browserHealth: `${env.API_URL}${API_PREFIX}/browser/health`,
    diagnosticsDns: `${env.API_URL}${API_PREFIX}/browser/diagnostics/dns`,
    diagnosticsProxy: `${env.API_URL}${API_PREFIX}/browser/diagnostics/proxy`,
    diagnosticsNetwork: `${env.API_URL}${API_PREFIX}/browser/diagnostics/network`,
    recover: `${env.API_URL}${API_PREFIX}/browser/recover`,
    networkEvents: `${env.API_URL}${API_PREFIX}/browser/network/events`,
    navigationTimeline: `${env.API_URL}${API_PREFIX}/browser/network/timeline`,
    // Navigation context classification (spec §7, §8, §9)
    navigateContext: `${env.API_URL}${API_PREFIX}/browser/navigate/context`,
    classifyFailure: `${env.API_URL}${API_PREFIX}/browser/navigate/classify-failure`,
    openContext: `${env.API_URL}${API_PREFIX}/browser/open-context`,
    pageUnderstand: `${env.API_URL}${API_PREFIX}/browser/page/understand`,
    profiles: `${env.API_URL}${API_PREFIX}/browser/profiles`,
    profilesByName: (profileName: string) => `${env.API_URL}${API_PREFIX}/browser/profiles/${profileName}`,
    engine: `${env.API_URL}${API_PREFIX}/browser/engine`,
  },

  search: {
    global: `${env.API_URL}${API_PREFIX}/search`,
    domains: `${env.API_URL}${API_PREFIX}/search/domains`,
    suggest: `${env.API_URL}${API_PREFIX}/search/suggest`,
    status: `${env.API_URL}${API_PREFIX}/search/status`,
    inspect: (source: string, itemId: string) =>
      `${env.API_URL}${API_PREFIX}/search/inspect/${source}/${itemId}`,
    toBrowser: `${env.API_URL}${API_PREFIX}/search/to/browser`,
    toResearch: `${env.API_URL}${API_PREFIX}/search/to/research`,
    toKnowledge: `${env.API_URL}${API_PREFIX}/search/to/knowledge`,
  },

  ws: {
    chat: `${env.WS_URL}/ws/chat`,
    health: `${env.WS_URL}/ws/health`,
    agents: `${env.WS_URL}/ws/agents`,
    voice: `${env.WS_URL}/api/v1/voice/ws/chat`,
    stark: `${env.WS_URL}/api/v1/stark/ws/chat`,
    monitoring: `${env.WS_URL}/ws/monitoring`,
  },
};

export default API_ENDPOINTS;
