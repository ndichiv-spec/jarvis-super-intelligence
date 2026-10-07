"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  Server,
  Cpu,
  Brain as BrainIcon,
  RefreshCw,
  AlertCircle,
  Check,
  X,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiClient } from "@/lib/api-client";

interface AiStatus {
  status: string;
  provider: string;
  enabled: boolean;
  silverwing_endpoint_configured?: boolean;
  silverwing_model?: string;
  brain_endpoint_configured?: boolean;
  brain_model?: string;
  brain_api_key_configured?: boolean;
  brain?: {
    configured: boolean;
    healthy: boolean;
    latency_ms: number | null;
    category: string;
    detail: string;
  };
}

interface SystemStatus {
  status: string;
  hostname: string;
  platform: string;
  python: string;
  services: string[];
  env_path?: string;
}

export function DiagnosticsTab() {
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [sysData, aiData] = await Promise.all([
        apiClient.get<SystemStatus>("/api/v1/system/status"),
        apiClient.get<AiStatus>("/api/v1/ai/status"),
      ]);
      setSystem(sysData);
      setAiStatus(aiData);
    } catch (err: any) {
      setError(err.message || "Failed to load diagnostics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  if (loading) {
    return <DiagnosticsSkeleton />;
  }

  if (error) {
    return (
      <Card className="border-destructive/50">
        <CardContent className="pt-6">
          <div className="flex items-center gap-3 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{error}</span>
          </div>
          <Button variant="outline" size="sm" className="mt-4" onClick={() => void loadData()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">Diagnostics</h2>
        <Button variant="outline" size="sm" onClick={() => void loadData()}>
          <RefreshCw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>

      {/* System info */}
      {system && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Server className="h-5 w-5 text-primary" />
              System Information
            </CardTitle>
            <CardDescription>Runtime environment for the JARVIS backend</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <SysInfoRow label="Hostname" value={system.hostname} icon={<Server className="h-4 w-4" />} />
              <SysInfoRow label="Platform" value={system.platform} icon={<Activity className="h-4 w-4" />} />
              <SysInfoRow label="Python" value={system.python} icon={<Cpu className="h-4 w-4" />} />
              <SysInfoRow label="Status" value={system.status} icon={
                system.status === "online" ? <Check className="h-4 w-4 text-success" /> : <X className="h-4 w-4 text-destructive" />
              } />
              <div className="pt-2">
                <span className="text-sm font-medium">Services:</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {system.services.map((s) => (
                    <Badge key={s} variant="outline" className="text-xs">
                      {s}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* AI status */}
      {aiStatus && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BrainIcon className="h-5 w-5 text-primary" />
              AI Provider Status
            </CardTitle>
            <CardDescription>
              Active provider: {aiStatus.provider}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <SysInfoRow label="Backend Status" value={aiStatus.status} icon={
                aiStatus.status === "ready" || aiStatus.status === "online"
                  ? <Check className="h-4 w-4 text-success" />
                  : <AlertCircle className="h-4 w-4 text-warning" />
              } />
              <SysInfoRow label="Enabled" value={aiStatus.enabled ? "true" : "false"} />
              {aiStatus.brain && (
                <>
                  <SysInfoRow label="JARVIS Brain Endpoint" value={aiStatus.brain_endpoint_configured ? "Configured" : "Not configured"} icon={<BrainIcon className="h-4 w-4" />} />
                  <SysInfoRow label="Brain Healthy" value={aiStatus.brain.healthy ? "Yes" : "No"} icon={
                    aiStatus.brain.healthy ? <Check className="h-4 w-4 text-success" /> : <X className="h-4 w-4 text-destructive" />
                  } />
                  <SysInfoRow label="Brain Detail" value={aiStatus.brain.detail} />
                </>
              )}
              {aiStatus.silverwing_endpoint_configured && (
                <SysInfoRow label="Silverwing Endpoint" value="Configured" icon={<Activity className="h-4 w-4" />} />
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function SysInfoRow({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}>
      <div className="flex items-center justify-between py-2 border-b border-border/30 last:border-0">
        <div className="flex items-center gap-3">
          {icon}
          <span className="text-sm font-medium">{label}</span>
        </div>
        <span className="text-sm text-muted-foreground">{value}</span>
      </div>
    </motion.div>
  );
}

function DiagnosticsSkeleton() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="h-5 bg-muted/30 rounded animate-pulse w-48" />
          <div className="h-4 bg-muted/30 rounded animate-pulse w-32 mt-1" />
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-12 bg-muted/30 rounded animate-pulse" />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
