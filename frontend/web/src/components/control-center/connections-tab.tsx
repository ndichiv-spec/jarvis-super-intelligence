"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Mail,
  RefreshCw,
  AlertCircle,
  TestTube,
  Edit,
  Trash2,
  Check,
  X,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";

interface ConnectorInfo {
  kind: string;
  name: string;
  enabled: boolean;
  capabilities: string[];
  connected: boolean;
  configured?: boolean;
  host: string | null;
  port: number | null;
  username: string | null;
  password_set: boolean;
  encryption: string;
}

export function ConnectionsTab() {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);

  const loadConnectors = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.get<{ connectors: any[] }>("/api/v1/connectors");
      // The API returns each connector as `{ configured, enabled, config: <public_config> }`
      // where real credentials are masked at rest — the client only ever sees a
      // `password_set` flag, never the real password. Map that into the flat
      // shape the list below expects so Test/Configure behave correctly.
      const mapped: ConnectorInfo[] = (data.connectors || []).map((c: any) => {
        const config = c.config || {};
        return {
          kind: c.kind,
          name: c.label || c.kind,
          enabled: !!c.enabled,
          capabilities: Array.isArray(c.capabilities) ? c.capabilities : [],
          connected: !!config.last_test_ok,
          configured: !!c.configured,
          host: config.imap_host || config.host || null,
          port: typeof config.imap_port === "number" ? config.imap_port : null,
          username: config.imap_user || null,
          password_set: !!config.password_set,
          encryption: config.imap_ssl === false ? "STARTTLS" : "SSL/TLS",
        };
      });
      setConnectors(mapped);
    } catch (err: any) {
      setError(err.message || "Failed to load connectors");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadConnectors();
  }, []);

  const handleTest = async (connector: ConnectorInfo) => {
    // The real password is stored encrypted server-side and is never sent to
    // the client (only a `password_set` flag is exposed). For an already-
    // configured connector we POST an empty body and the backend re-tests the
    // stored credentials. An unconfigured connector can't be tested here —
    // point the user at the configuration UI instead of surfacing a cryptic
    // backend 400 ("IMAP host, username, and password are required to test").
    if (!connector.configured || !connector.password_set) {
      toast.info("Configure your email credentials first (dashboard → Connections)");
      return;
    }
    setTestingId(connector.kind);
    try {
      const result = await apiClient.post<{
        ok?: boolean;
        message?: string;
        imap?: { ok?: boolean; message?: string };
        smtp?: { ok?: boolean; message?: string };
      }>(`/api/v1/connectors/${connector.kind}/test`, {});
      const ok = result.ok ?? true;
      const msg = result.message || (ok ? "ok" : "test failed");
      ok
        ? toast.success(`Test passed for ${connector.kind}: ${msg}`)
        : toast.error(`Test failed for ${connector.kind}: ${msg}`);
    } catch (err: any) {
      toast.error(`Test failed: ${err.message}`);
    } finally {
      setTestingId(null);
    }
  };

  if (loading) {
    return <ConnectionsSkeleton />;
  }

  if (error) {
    return (
      <Card className="border-destructive/50">
        <CardContent className="pt-6">
          <div className="flex items-center gap-3 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{error}</span>
          </div>
          <Button variant="outline" size="sm" className="mt-4" onClick={() => void loadConnectors()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">Connected Services</h2>
        <Button variant="outline" size="sm" onClick={() => void loadConnectors()}>
          <RefreshCw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>

      {connectors.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">No connectors configured.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {connectors.map((c) => (
            <ConnectorRow
              key={c.kind}
              connector={c}
              isTesting={testingId === c.kind}
              onTest={() => void handleTest(c)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ConnectorRow({
  connector,
  isTesting,
  onTest,
}: {
  connector: ConnectorInfo;
  isTesting: boolean;
  onTest: () => void;
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Mail className="h-4 w-4" />
                {connector.name}
              </CardTitle>
              <CardDescription className="text-sm">
                {connector.host}{connector.port ? `:${connector.port}` : ""} · {connector.encryption}
              </CardDescription>
            </div>
            <Badge variant={connector.connected ? "default" : "secondary"}>
              {connector.connected ? "Connected" : "Not Connected"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {connector.capabilities.map((cap) => (
              <Badge key={cap} variant="outline" className="text-xs">
                {cap}
              </Badge>
            ))}
          </div>
          <div className="flex gap-2 mt-3">
            <Button size="sm" variant="outline" disabled={isTesting} onClick={onTest}>
              {isTesting ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <TestTube className="h-4 w-4" />
              )}
              Test
            </Button>
            <Button size="sm" variant="outline" asChild>
              <a href="/dashboard/connections" className="flex items-center gap-2">
                <Edit className="h-4 w-4" />
                {connector.password_set ? "Edit" : "Configure"}
              </a>
            </Button>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function ConnectionsSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 3 }).map((_, i) => (
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
            <div className="h-8 bg-muted/30 rounded animate-pulse w-64" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
