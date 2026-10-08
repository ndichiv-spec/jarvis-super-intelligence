'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowUpRight, Shield } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export default function EnterpriseSSOPage() {
  const [checking, setChecking] = useState(false);

  const checkAvailability = async () => {
    setChecking(true);
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || ''}/api/v1/enterprise/sso/test`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: 'enterprise-sso' }),
        },
      );
      const result = await response.json();
      if (response.ok && result.success === true) {
        toast.success('Identity provider validation is available.');
      } else if (response.status === 501) {
        toast.error('Enterprise SSO validation is not implemented in this deployment.');
      } else {
        toast.error(result.error?.message ?? `SSO availability check failed (HTTP ${response.status}).`);
      }
    } catch {
      toast.error('Could not reach the enterprise SSO validation API.');
    } finally {
      setChecking(false);
    }
  };

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-4 sm:p-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-cyan-300">JARVIS / Identity</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Enterprise single sign-on</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Identity-provider configuration and federation are not available in this deployment.
        </p>
      </header>

      <Card className="border-amber-400/25 bg-amber-400/[0.04]">
        <CardHeader>
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-1 h-5 w-5 shrink-0 text-amber-300" aria-hidden="true" />
            <div>
              <CardTitle>SSO is unavailable</CardTitle>
              <CardDescription className="mt-2">
                JARVIS does not expose a configured OIDC or SAML identity-provider flow here. Provider settings,
                client secrets, and success states are not stored or simulated by this page.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button onClick={() => void checkAvailability()} disabled={checking}>
            <Shield className="mr-2 h-4 w-4" />
            {checking ? 'Checking…' : 'Check backend support'}
          </Button>
          <Button asChild variant="outline">
            <Link href="/dashboard/connections">
              Service connections <ArrowUpRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Service OAuth connections are separate from signing in to JARVIS. Manage only the provider grants currently
        exposed by the Connections Center; they do not enable enterprise SSO.
      </p>
    </main>
  );
}
