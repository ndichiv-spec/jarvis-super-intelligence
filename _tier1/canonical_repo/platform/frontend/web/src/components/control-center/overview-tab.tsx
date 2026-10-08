"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Brain, Puzzle, Plug, Key, AlertCircle } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { controlCenterApi } from "@/lib/control-center-api";
import { cn } from "@/lib/utils";
import type { ControlCenterStatus, ProviderConnection } from "@/lib/types/control-center";

export function OverviewTab() {
  const [status, setStatus] = useState<ControlCenterStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await controlCenterApi.getStatus();
      setStatus(data);
    } catch (err: any) {
      setError(err.message || "Failed to load Control Center status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadStatus();
  }, []);

  if (loading) {
    return <OverviewSkeleton />;
  }

  if (error) {
    return (
      <Card className="border-destructive/50">
        <CardContent className="pt-6">
          <div className="flex items-center gap-3 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{error}</span>
          </div>
          <Button variant="outline" size="sm" className="mt-4" onClick={() => void loadStatus()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!status) return null;

  const summary = status.provider_summary;
  const healthyPct = summary.total > 0 ? Math.round((summary.connected / summary.total) * 100) : 0;

  return (
    <div className="space-y-6">
      {/* Provider health tiles */}
      <section>
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Brain className="h-5 w-5 text-primary" />
          AI Providers
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {status.providers.map((p) => (
            <ProviderTile key={p.provider} provider={p} />
          ))}
        </div>
      </section>

      {/* Resource counts */}
      <section>
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Puzzle className="h-5 w-5 text-primary" />
          Platform Resources
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <MetricCard
            icon={<Brain className="h-6 w-6" />}
            title="Providers"
            value={`${summary.connected}/${summary.total}`}
            subtitle={`${healthyPct}% connected`}
            color={healthyPct === 100 ? "text-success" : healthyPct > 0 ? "text-warning" : "text-muted-foreground"}
          />
          <MetricCard
            icon={<Puzzle className="h-6 w-6" />}
            title="Extensions Installed"
            value={String(status.extensions.installed_count)}
            subtitle={`${status.extensions.connected_count} connected`}
            color="text-primary"
          />
          <MetricCard
            icon={<Plug className="h-6 w-6" />}
            title="Connectors"
            value={String(status.connectors.count)}
            subtitle="Active services"
            color="text-accent"
          />
        </div>
      </section>

      {/* Credentials summary */}
      <section>
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Key className="h-5 w-5 text-primary" />
          Configured Credentials
        </h2>
        <div className="space-y-2">
          {status.providers
            .filter((p) => p.configured)
            .map((p) => (
              <div key={p.provider} className="flex items-center justify-between py-2 border-b border-border/50">
                <span className="text-sm">{p.display_name}</span>
                <Badge variant="outline" className="text-success border-success/30">
                  Configured
                </Badge>
              </div>
            ))}
          {status.providers.filter((p) => p.configured).length === 0 && (
            <p className="text-sm text-muted-foreground">No credentials configured yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function ProviderTile({ provider }: { provider: ProviderConnection }) {
  const statusColor = provider.connected
    ? "border-success/50 bg-success/5"
    : "border-border/30 bg-muted/20";
  const dotColor = provider.connected ? "bg-success" : "bg-muted-foreground/50";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.15 }}
    >
      <Card className={cn("border-2", statusColor)}>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium">{provider.display_name}</CardTitle>
            <div className={`w-2.5 h-2.5 rounded-full ${dotColor}`} />
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <p className="text-xs text-muted-foreground">{provider.detail}</p>
          {provider.model_count > 0 && (
            <p className="text-xs text-muted-foreground mt-1">{provider.model_count} models available</p>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

interface MetricCardProps {
  icon: React.ReactNode;
  title: string;
  value: string;
  subtitle: string;
  color: string;
}

function MetricCard({ icon, title, value, subtitle, color }: MetricCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardDescription className="text-sm font-medium">{title}</CardDescription>
          {icon}
        </div>
      </CardHeader>
      <CardContent>
        <div className={`text-2xl font-bold ${color}`}>{value}</div>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </CardContent>
    </Card>
  );
}

function OverviewSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="border-border/30">
            <CardHeader className="pb-2">
              <div className="h-4 bg-muted/30 rounded animate-pulse w-3/4" />
            </CardHeader>
            <CardContent>
              <div className="h-3 bg-muted/30 rounded animate-pulse w-1/2 mb-1" />
              <div className="h-3 bg-muted/30 rounded animate-pulse w-1/3" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Card className="border-border/30">
        <CardContent className="pt-6">
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-4 bg-muted/30 rounded animate-pulse" />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
