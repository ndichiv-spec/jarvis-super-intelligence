"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TestTube, Trash2, RefreshCw, AlertCircle, ExternalLink } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { controlCenterApi } from "@/lib/control-center-api";
import type { ProviderConnection } from "@/lib/types/control-center";

export function ProvidersTab() {
  const [providers, setProviders] = useState<ProviderConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);

  const loadProviders = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await controlCenterApi.getProviders();
      setProviders(data);
    } catch (err: any) {
      setError(err.message || "Failed to load providers");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadProviders();
  }, []);

  const handleTest = async (id: string) => {
    setTestingId(id);
    try {
      const result = await controlCenterApi.testProvider(id);
      toast.success(`Test complete for ${result.provider}: ${result.detail}`);
    } catch (err: any) {
      toast.error(`Test failed: ${err.message}`);
    } finally {
      setTestingId(null);
    }
  };

  const handleDisconnect = async (id: string) => {
    try {
      const result = await controlCenterApi.disconnectProvider(id);
      toast.success(`${id} disconnected`);
      void loadProviders();
    } catch (err: any) {
      toast.error(`Disconnect failed: ${err.message}`);
    }
  };

  const handleConnect = async (id: string) => {
    try {
      const result = await controlCenterApi.connectProvider(id);
      if (result.auth_url_hint) {
        window.open(result.auth_url_hint, "_blank", "noopener,noreferrer");
      } else {
        toast.info(result.detail || `Connect ${id}`);
      }
    } catch (err: any) {
      toast.error(`Connect failed: ${err.message}`);
    }
  };

  if (loading) {
    return <ProvidersSkeleton />;
  }

  if (error) {
    return (
      <Card className="border-destructive/50">
        <CardContent className="pt-6">
          <div className="flex items-center gap-3 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{error}</span>
          </div>
          <Button variant="outline" size="sm" className="mt-4" onClick={() => void loadProviders()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">AI Provider Connections</h2>
        <Button variant="outline" size="sm" onClick={() => void loadProviders()}>
          <RefreshCw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>

      <div className="space-y-3">
        {providers.map((p) => (
          <ProviderRow
            key={p.provider}
            provider={p}
            isTesting={testingId === p.provider}
            onTest={() => void handleTest(p.provider)}
            onDisconnect={() => void handleDisconnect(p.provider)}
            onConnect={() => void handleConnect(p.provider)}
          />
        ))}
      </div>
    </div>
  );
}

function ProviderRow({
  provider,
  isTesting,
  onTest,
  onDisconnect,
  onConnect,
}: {
  provider: ProviderConnection;
  isTesting: boolean;
  onTest: () => void;
  onDisconnect: () => void;
  onConnect: () => void;
}) {
  const statusColor = provider.connected ? "text-success" : "text-muted-foreground";
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">{provider.display_name}</CardTitle>
              <CardDescription className="text-sm">
                {provider.detail} · {provider.model_count} models
              </CardDescription>
            </div>
            <Badge variant={provider.connected ? "default" : "secondary"}>
              {provider.connected ? "Connected" : "Not Connected"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={isTesting}
              onClick={onTest}
            >
              {isTesting ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <TestTube className="h-4 w-4" />
              )}
              Test
            </Button>
            {provider.connected ? (
              <Button size="sm" variant="outline" onClick={onDisconnect}>
                <Trash2 className="h-4 w-4" /> Disconnect
              </Button>
            ) : (
              <Button size="sm" onClick={onConnect}>
                <ExternalLink className="h-4 w-4" /> Connect
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function ProvidersSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <Card key={i} className="border-border/30">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <div className="h-4 bg-muted/30 rounded animate-pulse w-32" />
                <div className="h-3 bg-muted/30 rounded animate-pulse w-48" />
              </div>
              <div className="h-6 bg-muted/30 rounded animate-pulse w-20" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="h-8 bg-muted/30 rounded animate-pulse w-48" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
