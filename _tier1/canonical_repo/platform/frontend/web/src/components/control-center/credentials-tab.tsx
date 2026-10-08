"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Key,
  RefreshCw,
  AlertCircle,
  Shield,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { controlCenterApi } from "@/lib/control-center-api";
import type { CredentialRef } from "@/lib/types/control-center";

export function CredentialsTab() {
  const [credentials, setCredentials] = useState<CredentialRef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rotatingId, setRotatingId] = useState<string | null>(null);

  const loadCredentials = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await controlCenterApi.getCredentials();
      setCredentials(data);
    } catch (err: any) {
      setError(err.message || "Failed to load credentials");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadCredentials();
  }, []);

  const handleRotate = async (providerId: string) => {
    setRotatingId(providerId);
    try {
      const result = await controlCenterApi.connectProvider(providerId);
      if (result.detail) {
        toast.info(result.detail);
      } else {
        toast.success(`Rotation initiated for ${providerId}`);
      }
    } catch (err: any) {
      toast.error(`Rotation failed: ${err.message}`);
    } finally {
      setRotatingId(null);
    }
  };

  const handleDisconnect = (providerId: string) => {
    void controlCenterApi.disconnectProvider(providerId)
      .then(() => {
        toast.success(`${providerId} disconnected`);
        void loadCredentials();
      })
      .catch((err: any) => {
        toast.error(`Disconnect failed: ${err.message}`);
      });
  };

  if (loading) {
    return <CredentialsSkeleton />;
  }

  if (error) {
    return (
      <Card className="border-destructive/50">
        <CardContent className="pt-6">
          <div className="flex items-center gap-3 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{error}</span>
          </div>
          <Button variant="outline" size="sm" className="mt-4" onClick={() => void loadCredentials()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold">Credentials</h2>
        <Button variant="outline" size="sm" onClick={() => void loadCredentials()}>
          <RefreshCw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-primary" />
            Credential Vault
          </CardTitle>
          <CardDescription>
            Credentials are stored in the SecretManager — they are never returned
            to the frontend.  You can rotate or disconnect without exposing values.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {credentials.map((c) => (
              <CredentialRow
                key={c.provider}
                cred={c}
                isRotating={rotatingId === c.provider}
                onRotate={() => void handleRotate(c.provider)}
                onDisconnect={() => handleDisconnect(c.provider)}
              />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function CredentialRow({
  cred,
  isRotating,
  onRotate,
  onDisconnect,
}: {
  cred: CredentialRef;
  isRotating: boolean;
  onRotate: () => void;
  onDisconnect: () => void;
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <div className="flex items-center justify-between py-3 border-b border-border/50 last:border-0">
        <div className="flex items-center gap-3">
          <Key className="h-4 w-4 text-muted-foreground" />
          <div>
            <span className="font-medium text-sm">{cred.label}</span>
            <p className="text-xs text-muted-foreground">
              {cred.key} · source: {cred.source}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={cred.status === "set" ? "default" : "secondary"}>
            {cred.status === "set" ? "Configured" : "Not set"}
          </Badge>
          {cred.status === "set" && !cred.identity_provider && (
            <Button size="sm" variant="outline" disabled={isRotating} onClick={onRotate}>
              {isRotating ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              Rotate
            </Button>
          )}
          {cred.status === "set" && !cred.identity_provider && (
            <Button size="sm" variant="outline" onClick={onDisconnect}>
              Disconnect
            </Button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

function CredentialsSkeleton() {
  return (
    <Card>
      <CardHeader>
        <div className="h-5 bg-muted/30 rounded animate-pulse w-48" />
        <div className="h-4 bg-muted/30 rounded animate-pulse w-64 mt-1" />
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between py-3 border-b border-border/50">
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 bg-muted/30 rounded animate-pulse" />
                <div className="space-y-1">
                  <div className="h-4 bg-muted/30 rounded animate-pulse w-32" />
                  <div className="h-3 bg-muted/30 rounded animate-pulse w-48" />
                </div>
              </div>
              <div className="h-6 bg-muted/30 rounded animate-pulse w-20" />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
