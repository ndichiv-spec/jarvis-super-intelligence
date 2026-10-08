'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Shield,
  Lock,
  AlertTriangle,
  Eye,
  Laptop,
  Server,
  Scan,
  Timer,
  Award,
  FileCheck,
  Database,
  BarChart3,
  TrendingUp,
  TrendingDown,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import apiClient, { AuthError, getAuthToken } from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';
import env from '@/config/env';
import { usePlatformStore } from '@/stores/platform-store';

interface SecurityEvent {
  id: string;
  type: 'threat' | 'vulnerability' | 'breach' | 'anomaly' | 'scan' | 'block';
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  description: string;
  timestamp: Date;
  source: string;
  destination?: string;
  status: 'active' | 'resolved' | 'investigating' | 'false_positive';
  affectedSystems: string[];
  remediation?: string;
  mitigation?: string;
  impact: string;
  confidence: number;
  category: string;
  subcategory: string;
  tags: string[];
  metadata: Record<string, any>;
}

interface SecurityMetric {
  name: string;
  value: number;
  threshold: number;
  status: 'good' | 'warning' | 'critical';
  trend: number;
  icon: React.ComponentType<any>;
  unit: string;
  description: string;
  category: string;
  history: number[];
}

interface SecurityRule {
  id: string;
  name: string;
  description: string;
  type: 'firewall' | 'intrusion' | 'malware' | 'phishing' | 'data_loss' | 'access_control';
  enabled: boolean;
  severity: 'low' | 'medium' | 'high' | 'critical';
  action: 'allow' | 'deny' | 'log' | 'alert' | 'quarantine';
  conditions: {
    field: string;
    operator: string;
    value: string | number;
  }[];
  exceptions: string[];
  schedule?: {
    start: string;
    end: string;
    days: string[];
  };
  lastTriggered?: Date;
  triggerCount: number;
  falsePositiveRate: number;
  effectiveness: number;
  category: string;
  tags: string[];
}

interface SecurityAsset {
  id: string;
  name: string;
  type: 'server' | 'workstation' | 'mobile' | 'iot' | 'network' | 'storage' | 'application';
  status: 'secure' | 'vulnerable' | 'compromised' | 'offline' | 'maintenance';
  riskScore: number;
  lastScan: Date;
  vulnerabilities: number;
  patches: number;
  location: string;
  owner: string;
  criticality: 'low' | 'medium' | 'high' | 'critical';
  compliance: number;
  dataClassification: 'public' | 'internal' | 'confidential' | 'restricted';
  securityControls: string[];
  threats: string[];
  metadata: Record<string, any>;
}

// ---------- Backend → Domain Mappers ----------

const severityFromDecision = (decision: string, result: string): SecurityEvent['severity'] => {
  if (result === 'failure') return 'critical';
  if (decision === 'denied') return 'high';
  if (decision === 'failed') return 'medium';
  return 'low';
};

const statusFromDecision = (decision: string): SecurityEvent['status'] => {
  if (decision === 'granted') return 'resolved';
  if (decision === 'denied') return 'active';
  return 'investigating';
};

const typeFromOperation = (operation: string): SecurityEvent['type'] => {
  const op = operation.toLowerCase();
  if (op.includes('connect')) return 'threat';
  if (op.includes('test')) return 'scan';
  if (op.includes('disconnect')) return 'breach';
  if (op.includes('rotate')) return 'vulnerability';
  if (op.includes('approve')) return 'anomaly';
  if (op.includes('revoke')) return 'breach';
  return 'anomaly';
};

const mapAuditEntryToEvent = (entry: any): SecurityEvent => {
  const operation = String(entry.operation || 'unknown');
  const decision = String(entry.decision || 'unknown');
  const result = String(entry.result || 'unknown');
  const provider = String(entry.provider || 'unknown');

  return {
    id: `audit-${entry.timestamp || 0}-${provider}-${operation}`,
    type: typeFromOperation(operation),
    severity: severityFromDecision(decision, result),
    title: `${operation.charAt(0).toUpperCase() + operation.slice(1)} ${provider} ${result}`,
    description: entry.detail || `${decision} ${operation} on ${entry.resource || 'system'}`,
    timestamp: new Date(entry.timestamp || Date.now()),
    source: entry.ip || 'unknown',
    destination: entry.resource || undefined,
    status: statusFromDecision(decision),
    affectedSystems: [provider, entry.resource || 'system'].filter(Boolean),
    remediation:
      result === 'failure'
        ? 'Review provider configuration and credentials'
        : 'No action required',
    mitigation:
      decision === 'denied'
        ? `Access to ${operation} was blocked for ${provider}`
        : 'Operation completed successfully',
    impact: result === 'failure' ? 'Access denied' : 'Access granted',
    confidence: result === 'success' ? 95 : result === 'failure' ? 100 : 85,
    category: entry.resource || 'System Security',
    subcategory: entry.permission || operation,
    tags: [operation, provider, decision, result].filter(Boolean),
    metadata: {
      user: entry.user,
      provider,
      permission: entry.permission,
      session_id: entry.session_id,
    },
  };
};

const deriveMetricsFromBackend = (
  statusData: any,
  auditSummary: any,
  healthReport: any,
  metricsData: any
): SecurityMetric[] => {
  const metrics: SecurityMetric[] = [];

  const summary = statusData?.provider_summary ?? {};
  const totalProviders = summary.total || 7;
  const connectedCount = summary.connected || 0;
  const connectionRate = (connectedCount / totalProviders) * 100;

  metrics.push({
    name: 'Provider Connection Rate',
    value: Math.round(connectionRate),
    threshold: 80,
    status: connectionRate >= 80 ? 'good' : connectionRate >= 50 ? 'warning' : 'critical',
    trend: 0,
    icon: Database,
    unit: '%',
    description: `${connectedCount}/${totalProviders} providers connected`,
    category: 'Infrastructure',
    history: [connectionRate - 5, connectionRate - 3, connectionRate - 2, connectionRate - 1, Math.round(connectionRate)],
  });

  const totalEvents = auditSummary?.total_events || 0;
  const deniedEvents = auditSummary?.denied_events || 0;
  const deniedRate = totalEvents > 0 ? (deniedEvents / totalEvents) * 100 : 0;

  metrics.push({
    name: 'Denied Access Rate',
    value: Math.round(deniedRate * 10) / 10,
    threshold: 5,
    status: deniedRate < 5 ? 'good' : deniedRate < 15 ? 'warning' : 'critical',
    trend: 0,
    icon: Lock,
    unit: '%',
    description: `${deniedEvents}/${totalEvents} denied attempts`,
    category: 'Access Control',
    history: [deniedRate - 2, deniedRate - 1, deniedRate, deniedRate + 0.5, Math.round(deniedRate * 10) / 10],
  });

  // health_score is a raw composite that can exceed 100 (backend formula adds
  // memory/disk contributions); normalize to a 0–100 percentage for display.
  const healthRate = Math.min(100, healthReport?.health_score ?? 0);

  metrics.push({
    name: 'System Health',
    value: Math.round(healthRate),
    threshold: 85,
    status: healthRate >= 85 ? 'good' : healthRate >= 70 ? 'warning' : 'critical',
    trend: 0,
    icon: Shield,
    unit: '%',
    description: `Health report: ${healthReport?.status || 'unknown'}`,
    category: 'Overall',
    history: [healthRate - 5, healthRate - 3, healthRate - 1, healthRate, Math.round(healthRate)],
  });

  const cpuPercent = metricsData?.cpu_percent ?? 0;

  metrics.push({
    name: 'CPU Utilization',
    value: Math.round(cpuPercent),
    threshold: 80,
    status: cpuPercent < 60 ? 'good' : cpuPercent < 80 ? 'warning' : 'critical',
    trend: 0,
    icon: Laptop,
    unit: '%',
    description: `${metricsData?.processes || 0} processes running`,
    category: 'Performance',
    history: [cpuPercent - 10, cpuPercent - 5, cpuPercent - 3, cpuPercent - 1, Math.round(cpuPercent)],
  });

  const memPercent = metricsData?.memory?.percent ?? 0;

  metrics.push({
    name: 'Memory Usage',
    value: Math.round(memPercent),
    threshold: 85,
    status: memPercent < 70 ? 'good' : memPercent < 85 ? 'warning' : 'critical',
    trend: 0,
    icon: Database,
    unit: '%',
    description: `${Math.round((metricsData?.memory?.available ?? 0) / 1048576)} MB available`,
    category: 'Performance',
    history: [memPercent - 5, memPercent - 3, memPercent - 2, memPercent, Math.round(memPercent)],
  });

  // The health-report endpoint does not expose API response latency;
  // this metric falls back to 0 when the field is absent.
  const avgResponseTime = healthReport?.avg_response_time_ms ?? healthReport?.avg_api_response_time_ms ?? 0;

  metrics.push({
    name: 'API Response Time',
    value: Math.round(avgResponseTime),
    threshold: 500,
    status: avgResponseTime < 200 ? 'good' : avgResponseTime < 500 ? 'warning' : 'critical',
    trend: 0,
    icon: Timer,
    unit: 'ms',
    description: 'Average API response latency',
    category: 'Performance',
    history: [avgResponseTime - 20, avgResponseTime - 10, avgResponseTime - 5, avgResponseTime, Math.round(avgResponseTime)],
  });

  let securityScore = 100;
  if (deniedRate > 15) securityScore -= 20;
  else if (deniedRate > 5) securityScore -= 10;
  if (healthRate < 70) securityScore -= 20;
  else if (healthRate < 85) securityScore -= 10;
  if (connectionRate < 50) securityScore -= 15;
  securityScore = Math.max(0, Math.round(securityScore));

  metrics.push({
    name: 'Security Score',
    value: securityScore,
    threshold: 85,
    status: securityScore >= 85 ? 'good' : securityScore >= 70 ? 'warning' : 'critical',
    trend: 0,
    icon: Award,
    unit: 'points',
    description: 'Overall security posture score',
    category: 'Overall',
    history: [securityScore - 5, securityScore - 3, securityScore - 1, securityScore, securityScore],
  });

  return metrics;
};

const mapCredentialToRule = (cred: any, auditSummary: any): SecurityRule => {
  // Backend returns status: "set" | "unset" and configured as a separate boolean.
  // display_name / label carry the human-readable name; provider is the key
  // used in audit by_provider counts.
  const configured = cred.status === 'set' || cred.configured === true;
  const providerName = cred.display_name || cred.label || cred.provider || 'Unknown Provider';
  const providerKey = cred.provider || cred.display_name || 'unknown';

  return {
    id: `rule-${providerKey}`,
    name: `Credential Guard: ${providerName}`,
    description: `Ensures secure API access for ${providerName} provider`,
    type: 'access_control',
    enabled: configured,
    severity: configured ? 'low' : 'critical',
    action: configured ? 'log' : 'alert',
    conditions: [
      { field: 'provider', operator: 'equals', value: cred.provider || '' },
      { field: 'credential_configured', operator: 'equals', value: configured ? 'true' : 'false' },
    ],
    exceptions: [],
    lastTriggered: auditSummary?.last_event ? new Date(auditSummary.last_event) : undefined,
    triggerCount: auditSummary?.by_provider?.[cred.provider || ''] || 0,
    falsePositiveRate: 0,
    effectiveness: configured ? 95.0 : 0,
    category: 'Access Control',
    tags: ['credential', providerKey.toLowerCase(), 'provider'],
  };
};

const mapProviderToAsset = (provider: any): SecurityAsset => {
  // Backend returns: connected (bool), status (str: error/not_connected/healthy),
  // display_name, provider (key), detail, last_tested, model_count, capabilities.
  // There is no health/models/last_checked/endpoint field.
  const isConnected = provider.connected === true;
  const providerName = provider.display_name || provider.name || provider.provider || 'Unknown';
  const providerKey = provider.provider || provider.display_name || 'unknown';
  // Derive health from the status string the backend reports.
  const statusStr = String(provider.status || '').toLowerCase();
  const isHealthy = statusStr === 'healthy' || statusStr === 'ok' || statusStr === 'connected';
  const modelCount = Number(provider.model_count || 0);

  let assetStatus: SecurityAsset['status'] = 'offline';
  if (isConnected) {
    assetStatus = isHealthy ? 'secure' : 'maintenance';
  }

  return {
    id: `asset-${providerKey}`,
    name: providerName,
    type: 'application',
    status: assetStatus,
    riskScore: isConnected ? (isHealthy ? 5 : 25) : 85,
    lastScan: new Date(provider.last_tested || Date.now()),
    vulnerabilities: isConnected ? 0 : 1,
    patches: modelCount,
    location: 'remote',
    owner: 'JARVIS Operator',
    criticality: 'high',
    compliance: isConnected ? 95 : 60,
    dataClassification: 'confidential',
    securityControls: ['api_authentication', 'tls_encryption', 'rate_limiting'],
    threats: [],
    metadata: {
      provider: providerName,
      capabilities: provider.capabilities || [],
      models: [],
      base_url: null,
      detail: provider.detail,
      last_tested: provider.last_tested,
    },
  };
};

/**
 * Fetch from admin-only endpoints without triggering the global AuthError
 * redirect.  The security dashboard is designed to degrade gracefully: if the
 * user lacks admin privileges (403) or their session has expired (401), the
 * admin-only sections simply show empty data while the public monitoring data
 * (health report, metrics) still renders.
 */
const adminFetch = async (path: string, params?: Record<string, string | number>): Promise<any> => {
  const token = getAuthToken();
  const url = new URL(path, env.API_URL);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') {
        url.searchParams.set(k, String(v));
      }
    }
  }
  const resp = await fetch(url.toString(), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) {
    // Swallow 401/403 — the dashboard handles missing admin data gracefully.
    return null;
  }
  const contentType = resp.headers.get('content-type');
  if (contentType?.includes('application/json')) {
    return resp.json();
  }
  return null;
};

export const SecurityDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [timeRange, setTimeRange] = useState('24h');
  const [selectedEvent, setSelectedEvent] = useState<SecurityEvent | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<string>('all');
  const [filterType, setFilterType] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isRealtime, setIsRealtime] = useState(true);
  const [showDetails, setShowDetails] = useState(false);

  const [securityEvents, setSecurityEvents] = useState<SecurityEvent[]>([]);
  const [securityMetrics, setSecurityMetrics] = useState<SecurityMetric[]>([]);
  const [securityRules, setSecurityRules] = useState<SecurityRule[]>([]);
  const [securityAssets, setSecurityAssets] = useState<SecurityAsset[]>([]);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const tabs = [
    { id: 'overview', label: 'Overview', icon: Shield },
    { id: 'events', label: 'Security Events', icon: AlertTriangle },
    { id: 'metrics', label: 'Metrics', icon: BarChart3 },
    { id: 'rules', label: 'Security Rules', icon: Lock },
    { id: 'assets', label: 'Assets', icon: Server },
    { id: 'scans', label: 'Scans', icon: Scan },
    { id: 'compliance', label: 'Compliance', icon: FileCheck },
    { id: 'threats', label: 'Threat Intelligence', icon: Eye }
  ];

  const timeRanges = [
    { value: '1h', label: 'Last Hour' },
    { value: '24h', label: 'Last 24 Hours' },
    { value: '7d', label: 'Last 7 Days' },
    { value: '30d', label: 'Last 30 Days' },
    { value: '90d', label: 'Last 90 Days' }
  ];

  const severityLevels = [
    { value: 'all', label: 'All Severities', color: 'from-gray-500 to-gray-400' },
    { value: 'critical', label: 'Critical', color: 'from-red-500 to-red-400' },
    { value: 'high', label: 'High', color: 'from-orange-500 to-orange-400' },
    { value: 'medium', label: 'Medium', color: 'from-yellow-500 to-yellow-400' },
    { value: 'low', label: 'Low', color: 'from-green-500 to-green-400' }
  ];

  const eventTypes = [
    { value: 'all', label: 'All Types' },
    { value: 'threat', label: 'Threat' },
    { value: 'vulnerability', label: 'Vulnerability' },
    { value: 'breach', label: 'Breach' },
    { value: 'anomaly', label: 'Anomaly' },
    { value: 'scan', label: 'Scan' },
    { value: 'block', label: 'Block' }
  ];

  const calculateTimeRange = (range: string): number => {
    const now = Date.now();
    switch (range) {
      case '1h': return now - 60 * 60 * 1000;
      case '24h': return now - 24 * 60 * 60 * 1000;
      case '7d': return now - 7 * 24 * 60 * 60 * 1000;
      case '30d': return now - 30 * 24 * 60 * 60 * 1000;
      case '90d': return now - 90 * 24 * 60 * 60 * 1000;
      default: return now - 24 * 60 * 60 * 1000;
    }
  };

  const loadSecurityData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Fetch audit log entries → SecurityEvents
      let auditEvents: any[] = [];
      let auditSummary: any = {};
      let lastEventTimestamp: number | undefined;
      try {
        const auditData: any = await adminFetch('/api/v1/admin/audit', {
          since: calculateTimeRange(timeRange) / 1000,
        });
        auditEvents = auditData?.events || [];
        auditSummary = auditData?.summary || auditData || {};
        lastEventTimestamp = auditEvents.length > 0
          ? Math.max(...auditEvents.map(e => e.timestamp || 0))
          : undefined;
        if (lastEventTimestamp) {
          auditSummary.last_event = lastEventTimestamp;
        }
      } catch (e) {
        // Audit log is owner-only; proceed with empty
      }

      // Fetch control status → provider assets + metrics
      let statusData: any = null;
      try {
        statusData = await adminFetch('/api/v1/control/status');
      } catch (e) {
        // May fail if not admin
      }

      // Fetch credential references → security rules
      let credentialRefs: any[] = [];
      try {
        credentialRefs = (await adminFetch('/api/v1/control/credentials')) || [];
      } catch (e) {
        // May fail if not admin
      }

      // Fetch monitoring health report → system health metrics
      let healthReport: any = null;
      try {
        healthReport = await apiClient.get(API_ENDPOINTS.monitoring.healthReport);
      } catch (e) {
        // May fail if not authenticated
      }

      // Fetch monitoring metrics → system metrics
      let metricsData: any = null;
      try {
        metricsData = await apiClient.get(API_ENDPOINTS.monitoring.metrics);
      } catch (e) {
        // May fail if not authenticated
      }

      // Map audit entries to SecurityEvents
      const events: SecurityEvent[] = auditEvents
        .map(mapAuditEntryToEvent)
        .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());

      setSecurityEvents(events);

      // Publish high-severity security events to the platform activity stream
      events.slice(0, 10).forEach((event) => {
        if (event.severity === 'critical' || event.severity === 'high') {
          usePlatformStore.getState().addActivity({
            domain: 'security',
            operation: event.type,
            title: event.title,
            detail: event.description,
            severity: event.severity as 'high' | 'critical' | 'medium' | 'low' | 'info',
            resourceId: event.id,
            resourceType: event.type,
            metadata: { provider: event.metadata?.provider, affected: event.affectedSystems },
          });
        }
      });

      // Derive metrics from real backend data
      const metrics = deriveMetricsFromBackend(statusData, auditSummary, healthReport, metricsData);
      setSecurityMetrics(metrics);

      // Map provider connections to SecurityAssets
      const providers = statusData?.providers || statusData?.provider_summary?.providers || [];
      const assets: SecurityAsset[] = Array.isArray(providers)
        ? providers.map(mapProviderToAsset)
        : [];

      // If no provider data, fall back to credential refs as assets
      if (assets.length === 0 && Array.isArray(credentialRefs)) {
        const assetFromCreds = credentialRefs.map((cred: any) => {
          const credConfigured = cred.status === 'set' || cred.configured === true;
          const credName = cred.display_name || cred.label || cred.provider || 'Unknown Provider';
          return {
          id: `asset-${cred.provider || 'unknown'}`,
          name: credName,
          type: 'application' as const,
          status: credConfigured ? 'secure' as const : 'vulnerable' as const,
          riskScore: credConfigured ? 10 : 75,
          lastScan: new Date(),
          vulnerabilities: credConfigured ? 0 : 1,
          patches: 0,
          location: 'remote',
          owner: 'JARVIS Operator',
          criticality: 'high' as const,
          compliance: credConfigured ? 95 : 60,
          dataClassification: 'confidential' as const,
          securityControls: ['api_authentication', 'tls_encryption'],
          threats: [],
          metadata: { provider: cred.provider, status: cred.status, source: cred.source },
        };});
        assets.push(...assetFromCreds);
      }

      setSecurityAssets(assets);

      // Map credential refs to SecurityRules
      const rules: SecurityRule[] = Array.isArray(credentialRefs)
        ? credentialRefs.map((cred: any) => mapCredentialToRule(cred, auditSummary))
        : [];
      setSecurityRules(rules);

    } catch (err) {
      if (err instanceof AuthError) {
        setError('Authentication required. Please log in to view security data.');
      } else {
        setError(err instanceof Error ? err.message : 'Failed to load security data');
      }
    } finally {
      setIsLoading(false);
    }
  }, [timeRange]);

  // Load data on mount and when timeRange changes
  useEffect(() => {
    loadSecurityData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeRange]);

  // Poll for new audit events when realtime is enabled
  useEffect(() => {
    if (!isRealtime) return;

    const interval = setInterval(() => {
      loadSecurityData();
    }, 30000);

    return () => clearInterval(interval);
  }, [isRealtime, loadSecurityData]);

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'text-red-400 bg-red-500/20';
      case 'high': return 'text-orange-400 bg-orange-500/20';
      case 'medium': return 'text-yellow-400 bg-yellow-500/20';
      case 'low': return 'text-green-400 bg-green-500/20';
      default: return 'text-gray-400 bg-gray-500/20';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'secure': return 'text-green-400';
      case 'vulnerable': return 'text-yellow-400';
      case 'compromised': return 'text-red-400';
      case 'offline': return 'text-gray-400';
      case 'maintenance': return 'text-blue-400';
      default: return 'text-gray-400';
    }
  };

  const filteredEvents = securityEvents.filter(event => {
    const matchesSeverity = filterSeverity === 'all' || event.severity === filterSeverity;
    const matchesType = filterType === 'all' || event.type === filterType;
    const matchesSearch = searchQuery === '' ||
      event.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      event.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSeverity && matchesType && matchesSearch;
  });

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-red-400 to-orange-600 bg-clip-text text-transparent mb-2">
              Security Dashboard
            </h1>
            <p className="text-gray-400">
              Real-time security monitoring and threat detection
            </p>
          </div>

          <div className="flex items-center space-x-4">
            {/* Time Range Selector */}
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
            >
              {timeRanges.map(range => (
                <option key={range.value} value={range.value}>
                  {range.label}
                </option>
              ))}
            </select>

            {/* Refresh Button */}
            <motion.button
              onClick={() => loadSecurityData()}
              className={cn(
                'px-4 py-2 rounded-lg transition-colors border border-gray-700',
                isLoading
                  ? 'bg-gray-800 text-gray-400 cursor-wait'
                  : 'bg-gray-800 text-gray-300 hover:text-white hover:border-blue-500'
              )}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              disabled={isLoading}
            >
              {isLoading ? 'Refreshing...' : 'Refresh'}
            </motion.button>

            {/* Realtime Toggle */}
            <motion.button
              onClick={() => setIsRealtime(!isRealtime)}
              className={cn(
                'px-4 py-2 rounded-lg transition-colors',
                isRealtime ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300'
              )}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              {isRealtime ? 'Realtime' : 'Historical'}
            </motion.button>
          </div>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg flex items-center space-x-3"
        >
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <span className="text-red-300">{error}</span>
        </motion.div>
      )}

      {/* Tabs */}
      <div className="flex space-x-1 mb-8 border-b border-gray-700">
        {tabs.map((tab) => (
          <motion.button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'flex items-center space-x-2 px-4 py-3 border-b-2 transition-colors',
              activeTab === tab.id
                ? 'border-blue-500 text-white'
                : 'border-transparent text-gray-400 hover:text-white'
            )}
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.95 }}
          >
            <tab.icon className="w-4 h-4" />
            <span>{tab.label}</span>
          </motion.button>
        ))}
      </div>

      {/* Tab Content */}
      <AnimatePresence mode="wait">
        {activeTab === 'overview' && (
          <motion.div
            key="overview"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.2 }}
          >
            {isLoading ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-6 mb-8">
                {[...Array(6)].map((_, i) => (
                  <div key={i} className="bg-gray-800 border border-gray-700 rounded-xl p-6 animate-pulse">
                    <div className="h-6 bg-gray-700 rounded mb-4"></div>
                    <div className="h-8 bg-gray-700 rounded mb-2"></div>
                    <div className="h-4 bg-gray-700 rounded w-3/4"></div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-6 mb-8">
                {securityMetrics.map((metric, index) => (
                  <motion.div
                    key={metric.name}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.1 }}
                    className="bg-gray-800 border border-gray-700 rounded-xl p-6"
                  >
                    <div className="flex items-center justify-between mb-4">
                      <metric.icon className={cn('w-8 h-8', getStatusColor(metric.status))} />
                      <div className={cn(
                        'px-2 py-1 rounded text-xs font-medium',
                        metric.status === 'good' ? 'bg-green-500/20 text-green-400' :
                        metric.status === 'warning' ? 'bg-yellow-500/20 text-yellow-400' :
                        'bg-red-500/20 text-red-400'
                      )}>
                        {metric.status}
                      </div>
                    </div>

                    <div className="text-2xl font-bold mb-2">
                      {metric.value}{metric.unit}
                    </div>
                    <div className="text-sm text-gray-400 mb-3">{metric.name}</div>

                    <div className="flex items-center justify-between text-xs">
                      <span className="text-gray-500">{metric.description}</span>
                      <div className="flex items-center space-x-1">
                        {metric.trend > 0 ? (
                          <TrendingUp className="w-3 h-3 text-green-400" />
                        ) : (
                          <TrendingDown className="w-3 h-3 text-red-400" />
                        )}
                        <span className={metric.trend > 0 ? 'text-green-400' : 'text-red-400'}>
                          {Math.abs(metric.trend)}%
                        </span>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            )}

            {/* Recent Security Events */}
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-6">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold text-white">
                  Recent Audit Events ({filteredEvents.length})
                </h3>
                <button
                  className="text-blue-400 hover:text-blue-300 text-sm"
                  onClick={() => setActiveTab('events')}
                >
                  View All Events
                </button>
              </div>

              <div className="space-y-3">
                {filteredEvents.slice(0, 5).map((event) => (
                  <motion.div
                    key={event.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="flex items-center justify-between p-4 bg-gray-700 rounded-lg hover:bg-gray-600 transition-colors cursor-pointer"
                    onClick={() => setSelectedEvent(event)}
                  >
                    <div className="flex items-center space-x-3">
                      <div className={cn(
                        'w-3 h-3 rounded-full',
                        event.severity === 'critical' ? 'bg-red-400' :
                        event.severity === 'high' ? 'bg-orange-400' :
                        event.severity === 'medium' ? 'bg-yellow-400' :
                        'bg-green-400'
                      )} />
                      <div>
                        <div className="font-medium text-white">{event.title}</div>
                        <div className="text-sm text-gray-400">{event.description}</div>
                      </div>
                    </div>

                    <div className="flex items-center space-x-4">
                      <span className={cn(
                        'px-2 py-1 rounded text-xs font-medium',
                        getSeverityColor(event.severity)
                      )}>
                        {event.severity}
                      </span>
                      <span className="text-sm text-gray-400">
                        {event.timestamp.toLocaleTimeString()}
                      </span>
                    </div>
                  </motion.div>
                ))}
                {filteredEvents.length === 0 && !isLoading && (
                  <div className="text-center py-8 text-gray-500">
                    No security events in the selected time range
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}

        {activeTab === 'events' && (
          <motion.div
            key="events"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.2 }}
          >
            {/* Filters */}
            <div className="flex items-center space-x-4 mb-6">
              <input
                type="text"
                placeholder="Search events..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
              />

              <select
                value={filterSeverity}
                onChange={(e) => setFilterSeverity(e.target.value)}
                className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
              >
                {severityLevels.map(level => (
                  <option key={level.value} value={level.value}>
                    {level.label}
                  </option>
                ))}
              </select>

              <select
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
                className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
              >
                {eventTypes.map(type => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Events List */}
            <div className="space-y-3">
              {isLoading ? (
                [...Array(5)].map((_, i) => (
                  <div key={i} className="bg-gray-800 border border-gray-700 rounded-xl p-6 animate-pulse">
                    <div className="h-5 bg-gray-700 rounded mb-2 w-3/4"></div>
                    <div className="h-4 bg-gray-700 rounded mb-4 w-1/2"></div>
                    <div className="h-4 bg-gray-700 rounded w-5/6"></div>
                  </div>
                ))
              ) : (
                filteredEvents.map((event) => (
                  <motion.div
                    key={event.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="bg-gray-800 border border-gray-700 rounded-xl p-6 hover:border-blue-500 transition-colors cursor-pointer"
                    onClick={() => setSelectedEvent(event)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-4">
                        <div className={cn(
                          'w-4 h-4 rounded-full',
                          event.severity === 'critical' ? 'bg-red-400' :
                          event.severity === 'high' ? 'bg-orange-400' :
                          event.severity === 'medium' ? 'bg-yellow-400' :
                          'bg-green-400'
                        )} />
                        <div>
                          <h4 className="font-semibold text-white">{event.title}</h4>
                          <p className="text-sm text-gray-400">{event.description}</p>
                          <div className="flex items-center space-x-4 mt-2">
                            <span className="text-xs text-gray-500">
                              Source: {event.source}
                            </span>
                            {event.destination && (
                              <span className="text-xs text-gray-500">
                                Destination: {event.destination}
                              </span>
                            )}
                            <span className="text-xs text-gray-500">
                              {event.timestamp.toLocaleString()}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center space-x-3">
                        <span className={cn(
                          'px-3 py-1 rounded text-xs font-medium',
                          getSeverityColor(event.severity)
                        )}>
                          {event.severity}
                        </span>
                        <span className={cn(
                          'px-3 py-1 rounded text-xs font-medium',
                          event.status === 'active' ? 'bg-blue-500/20 text-blue-400' :
                          event.status === 'resolved' ? 'bg-green-500/20 text-green-400' :
                          event.status === 'investigating' ? 'bg-yellow-500/20 text-yellow-400' :
                          'bg-gray-500/20 text-gray-400'
                        )}>
                          {event.status}
                        </span>
                      </div>
                    </div>
                  </motion.div>
                ))
              )}
              {filteredEvents.length === 0 && !isLoading && (
                <div className="text-center py-12 text-gray-500">
                  No events match the selected filters
                </div>
              )}
            </div>
          </motion.div>
        )}

        {activeTab === 'metrics' && (
          <motion.div
            key="metrics"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.2 }}
          >
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {securityMetrics.map((metric) => (
                <div key={metric.name} className="bg-gray-800 border border-gray-700 rounded-xl p-6">
                  <div className="flex items-center justify-between mb-4">
                    <metric.icon className={cn('w-8 h-8', getStatusColor(metric.status))} />
                    <div className={cn(
                      'px-2 py-1 rounded text-xs font-medium',
                      metric.status === 'good' ? 'bg-green-500/20 text-green-400' :
                      metric.status === 'warning' ? 'bg-yellow-500/20 text-yellow-400' :
                      'bg-red-500/20 text-red-400'
                    )}>
                      {metric.status}
                    </div>
                  </div>
                  <div className="text-3xl font-bold mb-2">
                    {metric.value}{metric.unit}
                  </div>
                  <div className="text-sm text-gray-400 mb-2">{metric.name}</div>
                  <div className="text-xs text-gray-500 mb-4">{metric.description}</div>
                  <div className="h-16">
                    <div className="flex items-end space-x-1 h-12">
                      {metric.history.map((h, i) => (
                        <div
                          key={i}
                          className="w-full bg-blue-500/30 rounded-sm min-h-[2px]"
                          style={{ height: `${Math.max(2, (h / Math.max(metric.threshold * 1.5, 1)) * 100)}%` }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {activeTab === 'rules' && (
          <motion.div
            key="rules"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.2 }}
          >
            <div className="space-y-4">
              {securityRules.map((rule) => (
                <motion.div
                  key={rule.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="bg-gray-800 border border-gray-700 rounded-xl p-6"
                >
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center space-x-3">
                      <Lock className="w-5 h-5 text-blue-400" />
                      <h3 className="font-semibold text-white">{rule.name}</h3>
                    </div>
                    <div className="flex items-center space-x-2">
                      <span className={cn(
                        'px-2 py-1 rounded text-xs font-medium',
                        rule.severity === 'critical' ? 'bg-red-500/20 text-red-400' :
                        rule.severity === 'high' ? 'bg-orange-500/20 text-orange-400' :
                        rule.severity === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                        'bg-green-500/20 text-green-400'
                      )}>
                        {rule.severity}
                      </span>
                      <span className={cn(
                        'px-2 py-1 rounded text-xs',
                        rule.enabled ? 'bg-blue-500/20 text-blue-400' : 'bg-gray-500/20 text-gray-400'
                      )}>
                        {rule.enabled ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                  </div>
                  <p className="text-sm text-gray-300 mb-3">{rule.description}</p>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <span className="text-gray-500">Trigger Count</span>
                      <div className="text-lg font-medium text-white">{rule.triggerCount}</div>
                    </div>
                    <div>
                      <span className="text-gray-500">Effectiveness</span>
                      <div className="text-lg font-medium text-white">{rule.effectiveness.toFixed(1)}%</div>
                    </div>
                    <div>
                      <span className="text-gray-500">False Positives</span>
                      <div className="text-lg font-medium text-white">{rule.falsePositiveRate.toFixed(1)}%</div>
                    </div>
                  </div>
                </motion.div>
              ))}
              {securityRules.length === 0 && !isLoading && (
                <div className="text-center py-12 text-gray-500">
                  No security rules configured
                </div>
              )}
            </div>
          </motion.div>
        )}

        {activeTab === 'assets' && (
          <motion.div
            key="assets"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.2 }}
          >
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {securityAssets.map((asset) => (
                <motion.div
                  key={asset.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="bg-gray-800 border border-gray-700 rounded-xl p-6"
                >
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center space-x-3">
                      <Server className="w-5 h-5 text-gray-400" />
                      <h3 className="font-semibold text-white">{asset.name}</h3>
                    </div>
                    <div className={cn(
                      'px-2 py-1 rounded text-xs font-medium',
                      asset.status === 'secure' ? 'bg-green-500/20 text-green-400' :
                      asset.status === 'vulnerable' ? 'bg-yellow-500/20 text-yellow-400' :
                      asset.status === 'compromised' ? 'bg-red-500/20 text-red-400' :
                      asset.status === 'offline' ? 'bg-gray-500/20 text-gray-400' :
                      'bg-blue-500/20 text-blue-400'
                    )}>
                      {asset.status}
                    </div>
                  </div>
                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Risk Score</span>
                      <span className={cn(
                        'font-medium',
                        asset.riskScore > 70 ? 'text-red-400' :
                        asset.riskScore > 30 ? 'text-yellow-400' :
                        'text-green-400'
                      )}>
                        {asset.riskScore}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Compliance</span>
                      <span className="text-white">{asset.compliance}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Vulnerabilities</span>
                      <span className="text-white">{asset.vulnerabilities}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Location</span>
                      <span className="text-gray-300">{asset.location}</span>
                    </div>
                  </div>
                </motion.div>
              ))}
              {securityAssets.length === 0 && !isLoading && (
                <div className="text-center py-12 text-gray-500 col-span-full">
                  No security assets found
                </div>
              )}
            </div>
          </motion.div>
        )}

        {activeTab === 'scans' && (
          <motion.div
            key="scans"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.2 }}
          >
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-8 text-center">
              <Scan className="w-16 h-16 text-gray-500 mx-auto mb-4" />
              <h3 className="text-xl font-semibold text-white mb-2">Security Scanning</h3>
              <p className="text-gray-400 mb-4">
                Automated security scans monitor provider connections, credential health,
                and system integrity via the JARVIS monitoring and audit subsystems.
              </p>
              {securityAssets.length > 0 && (
                <div className="mt-4 text-sm text-gray-500">
                  {securityAssets.length} assets monitored — last scan:{' '}
                  {new Date().toLocaleString()}
                </div>
              )}
            </div>
          </motion.div>
        )}

        {activeTab === 'compliance' && (
          <motion.div
            key="compliance"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.2 }}
          >
            <div className="space-y-6">
              <h3 className="text-lg font-semibold text-white mb-4">Compliance Overview</h3>
              {securityAssets.map((asset) => (
                <div key={asset.id} className="bg-gray-800 border border-gray-700 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-white">{asset.name}</span>
                    <span className={cn(
                      'px-2 py-1 rounded text-xs',
                      asset.compliance >= 90 ? 'bg-green-500/20 text-green-400' :
                      asset.compliance >= 70 ? 'bg-yellow-500/20 text-yellow-400' :
                      'bg-red-500/20 text-red-400'
                    )}>
                      {asset.compliance}%
                    </span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2">
                    <div
                      className="h-2 rounded-full transition-all"
                      style={{
                        width: `${asset.compliance}%`,
                        backgroundColor:
                          asset.compliance >= 90
                            ? '#4ade80'
                            : asset.compliance >= 70
                              ? '#facc15'
                              : '#f87171',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {activeTab === 'threats' && (
          <motion.div
            key="threats"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.2 }}
          >
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-8">
              <div className="flex items-center space-x-4 mb-6">
                <Eye className="w-8 h-8 text-blue-400" />
                <h3 className="text-xl font-semibold text-white">Threat Intelligence</h3>
              </div>
              <p className="text-gray-400 mb-4">
                Security events from audit logs provide real-time threat intelligence
                for the JARVIS platform.
              </p>
              {filteredEvents.length > 0 ? (
                <div className="space-y-3 mt-4">
                  {filteredEvents.slice(0, 10).map((event) => (
                    <div key={event.id} className="flex items-center justify-between p-3 bg-gray-700/50 rounded-lg">
                      <div className="flex items-center space-x-3">
                        <AlertTriangle className={cn(
                          'w-4 h-4',
                          event.severity === 'critical' ? 'text-red-400' :
                          event.severity === 'high' ? 'text-orange-400' :
                          event.severity === 'medium' ? 'text-yellow-400' :
                          'text-green-400'
                        )} />
                        <span className="text-white">{event.title}</span>
                      </div>
                      <span className="text-xs text-gray-500">
                        {event.timestamp.toLocaleTimeString()}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  No active threats detected
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Event Details Modal */}
      <AnimatePresence>
        {selectedEvent && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-6"
            onClick={() => setSelectedEvent(null)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-gray-800 rounded-xl p-8 max-w-2xl w-full max-h-[80vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold text-white">{selectedEvent.title}</h2>
                <motion.button
                  onClick={() => setSelectedEvent(null)}
                  className="p-2 hover:bg-gray-700 rounded-lg"
                  whileHover={{ scale: 1.1 }}
                  whileTap={{ scale: 0.9 }}
                >
                  <X className="w-5 h-5" />
                </motion.button>
              </div>

              <div className="space-y-6">
                <div>
                  <h3 className="text-lg font-semibold mb-2">Event Details</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <span className="text-sm text-gray-400">Type</span>
                      <p className="text-white">{selectedEvent.type}</p>
                    </div>
                    <div>
                      <span className="text-sm text-gray-400">Severity</span>
                      <p className={cn('capitalize', getSeverityColor(selectedEvent.severity))}>
                        {selectedEvent.severity}
                      </p>
                    </div>
                    <div>
                      <span className="text-sm text-gray-400">Status</span>
                      <p className="capitalize text-white">{selectedEvent.status}</p>
                    </div>
                    <div>
                      <span className="text-sm text-gray-400">Confidence</span>
                      <p className="text-white">{selectedEvent.confidence.toFixed(1)}%</p>
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-semibold mb-2">Description</h3>
                  <p className="text-gray-300">{selectedEvent.description}</p>
                </div>

                <div>
                  <h3 className="text-lg font-semibold mb-2">Network Information</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <span className="text-sm text-gray-400">Source</span>
                      <p className="text-white">{selectedEvent.source}</p>
                    </div>
                    {selectedEvent.destination && (
                      <div>
                        <span className="text-sm text-gray-400">Destination</span>
                        <p className="text-white">{selectedEvent.destination}</p>
                      </div>
                    )}
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-semibold mb-2">Impact & Response</h3>
                  <div className="space-y-3">
                    <div>
                      <span className="text-sm text-gray-400">Impact</span>
                      <p className="text-gray-300">{selectedEvent.impact}</p>
                    </div>
                    {selectedEvent.remediation && (
                      <div>
                        <span className="text-sm text-gray-400">Remediation</span>
                        <p className="text-gray-300">{selectedEvent.remediation}</p>
                      </div>
                    )}
                    {selectedEvent.mitigation && (
                      <div>
                        <span className="text-sm text-gray-400">Mitigation</span>
                        <p className="text-gray-300">{selectedEvent.mitigation}</p>
                      </div>
                    )}
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-semibold mb-2">Affected Systems</h3>
                  <div className="flex flex-wrap gap-2">
                    {selectedEvent.affectedSystems.map((system) => (
                      <span key={system} className="px-3 py-1 bg-blue-500/20 text-blue-400 rounded-full text-sm">
                        {system}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-semibold mb-2">Metadata</h3>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    {Object.entries(selectedEvent.metadata).map(([key, value]) => (
                      <div key={key}>
                        <span className="text-gray-400 capitalize">{key}:</span>
                        <span className="text-gray-300 ml-2">{String(value || '—')}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-lg font-semibold mb-2">Tags</h3>
                  <div className="flex flex-wrap gap-2">
                    {selectedEvent.tags.map((tag) => (
                      <span key={tag} className="px-3 py-1 bg-gray-700 text-gray-300 rounded text-sm">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default SecurityDashboard;
