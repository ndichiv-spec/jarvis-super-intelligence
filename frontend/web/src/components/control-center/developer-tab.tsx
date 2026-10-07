"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Terminal,
  Save,
  RefreshCw,
  AlertCircle,
  Cpu,
  MemoryStick,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";

interface ProviderSettings {
  ollama_base_url: string;
  ollama_model: string;
  aws_region: string;
}

interface LocalSettings {
  watchdogInterval: number;
  autoRecovery: boolean;
  optimizationStrategy: string;
  maxMemoryPercent: number;
  schedulerInterval: number;
  streamingResponses: boolean;
  autoSaveChat: boolean;
  defaultModel: string;
}

const DEFAULT_LOCAL_SETTINGS: LocalSettings = {
  watchdogInterval: 60,
  autoRecovery: true,
  optimizationStrategy: "adaptive",
  maxMemoryPercent: 80,
  schedulerInterval: 10,
  streamingResponses: true,
  autoSaveChat: true,
  defaultModel: "local",
};

const DEFAULT_PROVIDER_SETTINGS: ProviderSettings = {
  ollama_base_url: "http://localhost:11434",
  ollama_model: "llama3",
  aws_region: "us-east-1",
};

export function DeveloperTab() {
  const [settings, setSettings] = useState<ProviderSettings>(DEFAULT_PROVIDER_SETTINGS);
  const [localSettings, setLocalSettings] = useState<LocalSettings>(DEFAULT_LOCAL_SETTINGS);
  const [envPath, setEnvPath] = useState("");
  const [configuredCount, setConfiguredCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      // Load local settings from localStorage
      const saved = localStorage.getItem("jarvis-settings");
      if (saved) {
        const parsed = JSON.parse(saved) as Partial<LocalSettings>;
        setLocalSettings({ ...DEFAULT_LOCAL_SETTINGS, ...parsed });
      }

      // Load backend provider settings
      const response = await apiClient.get<{
        settings?: Partial<ProviderSettings>;
        env_path?: string;
        providers?: Record<string, { configured?: boolean }>;
      }>(
        "/api/v1/system/provider-settings"
      );
      const raw = response?.settings ?? {};
      setSettings({
        ollama_base_url: typeof raw.ollama_base_url === "string"
          ? raw.ollama_base_url
          : DEFAULT_PROVIDER_SETTINGS.ollama_base_url,
        ollama_model: typeof raw.ollama_model === "string"
          ? raw.ollama_model
          : DEFAULT_PROVIDER_SETTINGS.ollama_model,
        aws_region: typeof raw.aws_region === "string"
          ? raw.aws_region
          : DEFAULT_PROVIDER_SETTINGS.aws_region,
      });
      setConfiguredCount(
        Object.values(response?.providers ?? {}).filter((provider) => provider.configured).length
      );
      setEnvPath((response && response.env_path) || "");
    } catch (err: any) {
      setError(err.message || "Failed to load developer settings");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Save local settings to localStorage
      localStorage.setItem("jarvis-settings", JSON.stringify(localSettings));

      // Save backend provider settings
      const response = await apiClient.put<{
        providers?: Record<string, { configured?: boolean }>;
      }>("/api/v1/system/provider-settings", {
        ollama_base_url: settings.ollama_base_url,
        ollama_model: settings.ollama_model,
        aws_region: settings.aws_region,
      });
      setConfiguredCount(
        Object.values(response?.providers ?? {}).filter((provider) => provider.configured).length
      );
      toast.success("Developer settings saved");
    } catch (err: any) {
      toast.error(`Save failed: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    void loadSettings();
  }, []);

  if (loading) {
    return <DeveloperSkeleton />;
  }

  if (error) {
    return (
      <Card className="border-destructive/50">
        <CardContent className="pt-6">
          <div className="flex items-center gap-3 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{error}</span>
          </div>
          <Button variant="outline" size="sm" className="mt-4" onClick={() => void loadSettings()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  const updateProviderField = (field: keyof ProviderSettings, value: string) => {
    setSettings((current) => ({ ...current, [field]: value }));
  };

  const updateLocalField = (field: keyof LocalSettings, value: any) => {
    setLocalSettings((current) => ({ ...current, [field]: value }));
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">Developer Settings</h2>
        <Button variant="outline" size="sm" onClick={() => void loadSettings()}>
          <RefreshCw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
          Save Settings
        </Button>
      </div>

      {/* Local runtime config */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Cpu className="h-5 w-5 text-primary" />
              Local Runtime
            </CardTitle>
            <CardDescription>Client-side preferences stored in localStorage.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Default Model</Label>
              <Select
                value={localSettings.defaultModel}
                onValueChange={(v) => updateLocalField("defaultModel", v)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="local">Local (Ollama/Silverwing)</SelectItem>
                  <SelectItem value="openai">OpenAI</SelectItem>
                  <SelectItem value="google">Google Gemini</SelectItem>
                  <SelectItem value="auto">Auto Select</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center justify-between">
              <Label htmlFor="streaming">Streaming Responses</Label>
              <Switch
                id="streaming"
                checked={localSettings.streamingResponses}
                onCheckedChange={(c) => updateLocalField("streamingResponses", c)}
              />
            </div>

            <div className="flex items-center justify-between">
              <Label htmlFor="autosave">Auto-Save Chat History</Label>
              <Switch
                id="autosave"
                checked={localSettings.autoSaveChat}
                onCheckedChange={(c) => updateLocalField("autoSaveChat", c)}
              />
            </div>

            <div className="flex items-center justify-between">
              <Label htmlFor="recovery">Auto-Recovery</Label>
              <Switch
                id="recovery"
                checked={localSettings.autoRecovery}
                onCheckedChange={(c) => updateLocalField("autoRecovery", c)}
              />
            </div>

            <div className="space-y-2">
              <Label>Optimization Strategy</Label>
              <Select
                value={localSettings.optimizationStrategy}
                onValueChange={(v) => updateLocalField("optimizationStrategy", v)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="adaptive">Adaptive</SelectItem>
                  <SelectItem value="speed">Speed</SelectItem>
                  <SelectItem value="quality">Quality</SelectItem>
                  <SelectItem value="cost">Cost</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between">
                <Label>Max Memory Usage ({localSettings.maxMemoryPercent}%)</Label>
              </div>
              <Slider
                value={[localSettings.maxMemoryPercent]}
                onValueChange={(v) => updateLocalField("maxMemoryPercent", v[0])}
                max={95}
                min={50}
                step={5}
              />
            </div>

            <div className="space-y-2">
              <Label>Watchdog Interval (seconds)</Label>
              <Input
                type="number"
                value={localSettings.watchdogInterval}
                onChange={(e) => updateLocalField("watchdogInterval", parseInt(e.target.value, 10) || 60)}
              />
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Backend provider config */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Terminal className="h-5 w-5 text-primary" />
              Backend Provider Settings
            </CardTitle>
            <CardDescription>
              {envPath ? `Environment-managed configuration · ${configuredCount} providers configured` : `${configuredCount} providers configured`}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Provider credentials are configured by the server operator and are never returned to or editable in this browser.
            </p>

            <Separator />

            <div className="space-y-2">
              <Label>Ollama Base URL</Label>
              <Input
                value={settings.ollama_base_url || ""}
                onChange={(e) => updateProviderField("ollama_base_url", e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label>Ollama Model</Label>
              <Input
                value={settings.ollama_model || ""}
                onChange={(e) => updateProviderField("ollama_model", e.target.value)}
              />
            </div>

            <Separator />

            <div className="space-y-2">
              <Label>AWS Region</Label>
              <Input
                value={settings.aws_region || ""}
                onChange={(e) => updateProviderField("aws_region", e.target.value)}
              />
            </div>

          </CardContent>
        </Card>
      </motion.div>

      {/* Resource monitoring */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MemoryStick className="h-5 w-5 text-primary" />
              Resource Monitoring
            </CardTitle>
            <CardDescription>Local-only scheduler intervals for autonomous systems.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Scheduler Interval (seconds)</Label>
              <Input
                type="number"
                value={localSettings.schedulerInterval}
                onChange={(e) => updateLocalField("schedulerInterval", parseInt(e.target.value, 10) || 10)}
              />
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}

function DeveloperSkeleton() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="h-5 bg-muted/30 rounded animate-pulse w-48" />
          <div className="h-4 bg-muted/30 rounded animate-pulse w-32 mt-1" />
        </CardHeader>
        <CardContent className="space-y-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-10 bg-muted/30 rounded animate-pulse" />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
