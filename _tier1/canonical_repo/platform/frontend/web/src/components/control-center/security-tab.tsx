"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Shield,
  Lock,
  Key,
  RefreshCw,
  AlertCircle,
  Clock,
  CheckCircle,
  XCircle,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";

interface AuditEntry {
  timestamp: string | number;
  user: string;
  provider: string;
  operation: string;
  resource: string;
  permission: string;
  decision: string;
  result: string;
}

interface IdentityInfo {
  email: string;
  name: string;
  role: string;
  developer: boolean;
  primary_admin: boolean;
  auth_methods: string[];
  mfa_enabled: boolean;
  passkey_enabled: boolean;
  is_active: boolean;
  created_at: string | null;
  last_authenticated_at: string | null;
}

interface AuditSummary {
  total_events: number;
  last_event: string | null;
}

export function SecurityTab() {
  const [identity, setIdentity] = useState<IdentityInfo | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [auditSummary, setAuditSummary] = useState<AuditSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [idData, auditData] = await Promise.all([
        apiClient.get<{ owner: IdentityInfo; audit_summary: AuditSummary }>("/api/v1/admin/identity"),
        apiClient.get<{ entries: AuditEntry[] }>("/api/v1/admin/audit"),
      ]);
      setIdentity(idData.owner);
      setAuditSummary(idData.audit_summary);
      setAudit(auditData.entries || []);
    } catch (err: any) {
      setError(err.message || "Failed to load security data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  if (loading) {
    return <SecuritySkeleton />;
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
        <h2 className="text-lg font-semibold">Security</h2>
        <Button variant="outline" size="sm" onClick={() => void loadData()}>
          <RefreshCw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>

      {/* Identity / MFA */}
      {identity && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              Owner Identity
            </CardTitle>
            <CardDescription>{identity.email}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-sm font-medium">Multi-Factor Auth</span>
                <p className="text-xs text-muted-foreground">Additional login verification</p>
              </div>
              <Badge variant={identity.mfa_enabled ? "default" : "secondary"}>
                {identity.mfa_enabled ? "Enabled" : "Disabled"}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <span className="text-sm font-medium">Passkey Authentication</span>
                <p className="text-xs text-muted-foreground">WebAuthn passkey login</p>
              </div>
              <Badge variant={identity.passkey_enabled ? "default" : "secondary"}>
                {identity.passkey_enabled ? "Enabled" : "Disabled"}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <span className="text-sm font-medium">Auth Methods</span>
                <p className="text-xs text-muted-foreground">
                  {identity.auth_methods.join(", ") || "none"}
                </p>
              </div>
              <Badge variant="outline">{identity.role}</Badge>
            </div>
            {identity.last_authenticated_at && (
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium">Last Authentication</span>
                </div>
                <span className="text-xs text-muted-foreground">{identity.last_authenticated_at}</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Audit log */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Audit Log</CardTitle>
          <CardDescription>
            {auditSummary?.total_events || 0} total events · Last: {auditSummary?.last_event || "never"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {audit.slice(0, 10).map((entry, i) => (
              <AuditRow key={`${i}-${entry.timestamp}`} entry={entry} />
            ))}
            {audit.length === 0 && (
              <p className="text-sm text-muted-foreground">No audit events recorded.</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function AuditRow({ entry }: { entry: AuditEntry }) {
  const decisionColor =
    entry.decision === "granted" || entry.decision === "approved"
      ? "text-success"
      : entry.decision === "denied" || entry.decision === "rejected"
      ? "text-destructive"
      : "text-muted-foreground";

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <div className="flex items-center justify-between py-2 border-b border-border/30 last:border-0">
        <div className="flex items-center gap-3">
          <Clock className="h-4 w-4 text-muted-foreground" />
          <div>
            <span className="text-sm font-medium">{entry.operation}</span>
            <p className="text-xs text-muted-foreground">
              {entry.user} · {entry.resource} · {entry.permission}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium ${decisionColor}`}>{entry.decision}</span>
          <Badge variant={entry.result === "success" ? "default" : "destructive"} className="text-xs">
            {entry.result}
          </Badge>
        </div>
      </div>
    </motion.div>
  );
}

function SecuritySkeleton() {
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="h-5 bg-muted/30 rounded animate-pulse w-48" />
          <div className="h-4 bg-muted/30 rounded animate-pulse w-32 mt-1" />
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-12 bg-muted/30 rounded animate-pulse" />
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div className="h-5 bg-muted/30 rounded animate-pulse w-32" />
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-14 bg-muted/30 rounded animate-pulse" />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
