"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Puzzle,
  ExternalLink,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { controlCenterApi } from "@/lib/control-center-api";
import type { ExtensionCatalog, ExtensionManifest } from "@/lib/types/control-center";

export function ExtensionsTab() {
  const [catalog, setCatalog] = useState<ExtensionCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectDialog, setConnectDialog] = useState<ExtensionManifest | null>(null);

  const loadExtensions = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await controlCenterApi.getExtensions();
      setCatalog(data);
    } catch (err: any) {
      setError(err.message || "Failed to load extensions");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadExtensions();
  }, []);

  const handleInstall = async (ext: ExtensionManifest) => {
    try {
      await controlCenterApi.installExtension(ext.id);
      toast.success(`${ext.name} installed`);
      void loadExtensions();
    } catch (err: any) {
      toast.error(`Install failed: ${err.message}`);
    }
  };

  const handleConnectSubmit = async (ext: ExtensionManifest, apiKey?: string) => {
    try {
      const result = await controlCenterApi.connectExtension(ext.id, apiKey);
      if (result.launch_url) {
        window.open(String(result.launch_url), "_blank", "noopener,noreferrer");
      }
      toast.success(`${ext.name} connected`);
      setConnectDialog(null);
      void loadExtensions();
    } catch (err: any) {
      toast.error(`Connect failed: ${err.message}`);
    }
  };

  const handleConnect = (ext: ExtensionManifest) => {
    if (ext.connect_type === "api_key") {
      setConnectDialog(ext);
    } else {
      void handleConnectSubmit(ext);
    }
  };

  if (loading) {
    return <ExtensionsSkeleton />;
  }

  if (error) {
    return (
      <Card className="border-destructive/50">
        <CardContent className="pt-6">
          <div className="flex items-center gap-3 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{error}</span>
          </div>
          <Button variant="outline" size="sm" className="mt-4" onClick={() => void loadExtensions()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!catalog) return null;

  const installed = catalog.extensions.filter((e) => e.installed);
  const available = catalog.extensions.filter((e) => !e.installed);

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">
          Extension Hub ({catalog.total} extensions)
        </h2>
        <Button variant="outline" size="sm" onClick={() => void loadExtensions()}>
          <RefreshCw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>

      {/* Installed extensions */}
      <section>
        <h3 className="text-md font-medium mb-3 flex items-center gap-2">
          <Puzzle className="h-4 w-4 text-primary" />
          Installed
        </h3>
        {installed.length === 0 ? (
          <p className="text-sm text-muted-foreground">No extensions installed yet.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {installed.map((ext) => (
              <ExtensionCard
                key={ext.id}
                ext={ext}
                onConnect={() => handleConnect(ext)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Available extensions */}
      <section>
        <h3 className="text-md font-medium mb-3">Available in Marketplace</h3>
        {available.length === 0 ? (
          <p className="text-sm text-muted-foreground">All extensions are installed.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {available.map((ext) => (
              <ExtensionCard
                key={ext.id}
                ext={ext}
                onConnect={() => handleConnect(ext)}
                onInstall={() => void handleInstall(ext)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Connect dialog for API-key extensions */}
      <Dialog open={!!connectDialog} onOpenChange={() => setConnectDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Connect {connectDialog?.name}</DialogTitle>
            <DialogDescription>
              {connectDialog?.connect_type === "api_key"
                ? `Set ${connectDialog.key_env || "the API key env var"} in your environment, or paste it below.`
                : "Press Connect to open the service authorization page."}
            </DialogDescription>
          </DialogHeader>
          {connectDialog && connectDialog.connect_type === "api_key" && (
            <ApiKeyForm onSubmit={(key) => void handleConnectSubmit(connectDialog, key)} />
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConnectDialog(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                if (connectDialog) {
                  void handleConnectSubmit(connectDialog);
                }
              }}
            >
              Connect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface ExtensionCardProps {
  ext: ExtensionManifest;
  onConnect: () => void;
  onInstall?: () => void;
}

function ExtensionCard({ ext, onConnect, onInstall }: ExtensionCardProps) {
  const statusBadge = ext.connected
    ? { text: "Connected", variant: "default" as const }
    : ext.installed
    ? { text: "Installed", variant: "outline" as const }
    : { text: "Available", variant: "secondary" as const };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <span className="text-2xl">{ext.icon}</span>
              <div>
                <CardTitle className="text-base">{ext.name}</CardTitle>
                <CardDescription className="text-xs">
                  {ext.category} · {ext.caps.length} capabilities
                </CardDescription>
              </div>
            </div>
            <Badge variant={statusBadge.variant}>{statusBadge.text}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">{ext.desc}</p>
          <div className="flex gap-2">
            {!ext.installed ? (
              onInstall ? (
                <Button size="sm" onClick={onInstall}>Install</Button>
              ) : (
                <Button size="sm" onClick={onConnect}>Connect</Button>
              )
            ) : ext.connected ? (
              <Button size="sm" variant="outline">Connected</Button>
            ) : (
              <Button size="sm" onClick={onConnect}>Connect</Button>
            )}
            {ext.launch_url && (
              <Button size="sm" variant="ghost" asChild>
                <a href={ext.launch_url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="h-4 w-4" />
                </a>
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

interface ApiKeyFormProps {
  onSubmit: (key: string) => void;
}

function ApiKeyForm({ onSubmit }: ApiKeyFormProps) {
  const [key, setKey] = useState("");

  return (
    <div className="space-y-3">
      <Label htmlFor="api-key-input">API Key (optional — can use env var instead)</Label>
      <Input
        id="api-key-input"
        type="password"
        placeholder="sk-..."
        value={key}
        onChange={(e) => setKey(e.target.value)}
      />
      <Button size="sm" onClick={() => onSubmit(key)} disabled={!key.trim()}>
        Submit & Connect
      </Button>
    </div>
  );
}

function ExtensionsSkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <Card key={i} className="border-border/30">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="w-6 h-6 bg-muted/30 rounded animate-pulse" />
              <div className="space-y-1 flex-1">
                <div className="h-4 bg-muted/30 rounded animate-pulse w-3/4" />
                <div className="h-3 bg-muted/30 rounded animate-pulse w-1/2" />
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="h-3 bg-muted/30 rounded animate-pulse w-full mb-2" />
            <div className="h-3 bg-muted/30 rounded animate-pulse w-full mb-3" />
            <div className="h-8 bg-muted/30 rounded animate-pulse w-24" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
