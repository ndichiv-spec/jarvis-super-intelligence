"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, CheckCircle2, CircleHelp, Loader2, RefreshCw, Wrench } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { API_ENDPOINTS } from "@/config/api";
import { apiClient } from "@/lib/api-client";

interface ReadinessItem {
  id: string;
  name: string;
  status: "available" | "needs_setup" | "needs_consent" | "unavailable" | "partial";
  detail: string;
  action: string;
  href: string;
}

const STATUS_LABELS: Record<ReadinessItem["status"], string> = {
  available: "Available",
  needs_setup: "Needs setup",
  needs_consent: "Needs consent",
  unavailable: "Unavailable",
  partial: "Partial",
};

export default function CapabilitiesPage() {
  const [items, setItems] = useState<ReadinessItem[]>([]);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.get<{ items: ReadinessItem[]; checked_at: string }>(
        API_ENDPOINTS.system.readiness,
      );
      setItems(result.items);
      setCheckedAt(result.checked_at);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not load capability readiness.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  const readyCount = items.filter((item) => item.status === "available").length;

  return (
    <main className="space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Capability Readiness</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            What JARVIS can use now, what needs provider setup, and where to configure it.
          </p>
        </div>
        <Button variant="outline" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </header>

      {error ? (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 pt-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{error}</span>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-6">
              <div>
                <p className="text-lg font-semibold">
                  {loading ? "Checking system…" : `${readyCount} of ${items.length} capabilities available`}
                </p>
                <p className="text-sm text-muted-foreground">
                  Recommendations are informational; JARVIS will not install software or authorize services without your action.
                </p>
              </div>
              {checkedAt && <p className="text-xs text-muted-foreground">Checked {new Date(checkedAt).toLocaleString()}</p>}
            </CardContent>
          </Card>

          {loading && items.length === 0 ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Checking configured services…
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {items.map((item) => (
                <Card key={item.id}>
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-3">
                      <CardTitle className="text-base">{item.name}</CardTitle>
                      <Badge variant={item.status === "available" ? "default" : "secondary"}>
                        {item.status === "available" ? (
                          <CheckCircle2 className="mr-1 h-3 w-3" />
                        ) : item.status === "unavailable" ? (
                          <CircleHelp className="mr-1 h-3 w-3" />
                        ) : (
                          <Wrench className="mr-1 h-3 w-3" />
                        )}
                        {STATUS_LABELS[item.status]}
                      </Badge>
                    </div>
                    <CardDescription>{item.detail}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Button asChild size="sm" variant="outline">
                      <Link href={item.href}>{item.action}</Link>
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}
