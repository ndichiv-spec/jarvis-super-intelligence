'use client';

import { useEffect, useState, useSyncExternalStore } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { ArrowRight, Eye, EyeOff, KeyRound, MessageSquareText, UserRound } from 'lucide-react';
import { jarvisAPI } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';

const subscribeToHydration = () => () => {};
const getHydratedSnapshot = () => true;
const getServerHydrationSnapshot = () => false;

export default function LoginPage() {
  const router = useRouter();
  const authLogin = useAuthStore((state) => state.login);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isReady = useSyncExternalStore(
    subscribeToHydration,
    getHydratedSnapshot,
    getServerHydrationSnapshot,
  );
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (isAuthenticated) router.replace('/');
  }, [isAuthenticated, router]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isReady || loading) return;
    setError('');
    setLoading(true);

    try {
      const response = await jarvisAPI.login(identifier, password);
      authLogin(response.access_token ?? null, null, response.user);
      router.replace('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-[#090e16] px-4 py-10 text-slate-100">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_22%_12%,rgba(59,130,246,0.13),transparent_34%),radial-gradient(ellipse_at_85%_88%,rgba(37,99,235,0.08),transparent_32%)]"
      />
      <div className="relative w-full max-w-[620px] py-2">
        <header className="mb-10 sm:mb-12">
          <div className="mb-9 flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-blue-300/20 bg-blue-400/[0.08] text-blue-200">
              <MessageSquareText aria-hidden="true" className="h-5 w-5" />
            </span>
            <span className="text-sm font-semibold tracking-[0.2em] text-slate-100">JARVIS</span>
            <span aria-hidden="true" className="h-4 w-px bg-white/15" />
            <span className="text-[10px] font-medium uppercase tracking-[0.16em] text-slate-400">
              Conversation workspace
            </span>
          </div>

          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-200">
            Your work, in conversation
          </p>
          <h1 className="text-4xl font-semibold leading-tight tracking-[-0.04em] text-white sm:text-5xl">
            Pick up
            <br />
            <span className="text-blue-200">the thread.</span>
          </h1>
          <p className="mt-4 max-w-md text-sm leading-7 text-slate-400">
            Sign in to return to your conversations and the tools connected to your workspace.
          </p>
        </header>

        <section aria-labelledby="signin-title" className="max-w-[500px]">
          <div className="mb-6 flex items-end justify-between gap-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-400">Welcome back</p>
              <h2 id="signin-title" className="mt-1.5 text-2xl font-semibold tracking-tight text-white">
                Sign in
              </h2>
            </div>
            <span className="mb-1 font-mono text-[10px] tracking-[0.12em] text-slate-500">J / ACCESS</span>
          </div>

          {error && (
            <div
              role="alert"
              className="mb-5 rounded-lg border border-rose-300/20 bg-rose-400/[0.07] px-3.5 py-3 text-sm leading-5 text-rose-200"
            >
              {error}
            </div>
          )}

          <form method="post" onSubmit={handleSubmit} className="space-y-5 border-l border-blue-300/20 pl-8">
            <div className="relative">
              <span
                aria-hidden="true"
                className="absolute -left-[42px] top-[23px] flex h-5 w-5 items-center justify-center rounded-full border border-blue-300/30 bg-[#0b111b] text-blue-200"
              >
                <UserRound className="h-3 w-3" />
              </span>
              <label htmlFor="identifier" className="mb-2 block text-sm font-medium text-slate-300">
                Email or username
              </label>
              <input
                id="identifier"
                name="identifier"
                type="text"
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
                className="h-11 w-full rounded-lg border border-white/[0.1] bg-[#080d15] px-3.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-blue-300/60 focus:outline-none focus:ring-2 focus:ring-blue-300/15 disabled:opacity-60"
                placeholder="you@example.com"
                required
                autoComplete="username"
                disabled={!isReady || loading}
              />
            </div>

            <div className="relative">
              <span
                aria-hidden="true"
                className="absolute -left-[42px] top-[23px] flex h-5 w-5 items-center justify-center rounded-full border border-blue-300/30 bg-[#0b111b] text-blue-200"
              >
                <KeyRound className="h-3 w-3" />
              </span>
              <div className="mb-2 flex items-center justify-between gap-3">
                <label htmlFor="password" className="text-sm font-medium text-slate-300">
                  Password
                </label>
                <Link
                  href="/forgot-password"
                  className="text-xs font-medium text-blue-300 transition hover:text-blue-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-300"
                >
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="h-11 w-full rounded-lg border border-white/[0.1] bg-[#080d15] px-3.5 pr-11 text-sm text-slate-100 placeholder:text-slate-500 focus:border-blue-300/60 focus:outline-none focus:ring-2 focus:ring-blue-300/15 disabled:opacity-60"
                  placeholder="Enter your password"
                  required
                  autoComplete="current-password"
                  disabled={!isReady || loading}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((visible) => !visible)}
                  className="absolute right-2 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-slate-400 transition hover:bg-white/[0.05] hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-300 disabled:opacity-50"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                  disabled={!isReady || loading}
                >
                  {showPassword
                    ? <EyeOff aria-hidden="true" className="h-4 w-4" />
                    : <Eye aria-hidden="true" className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div className="relative pt-1">
              <span
                aria-hidden="true"
                className="absolute -left-[42px] top-[11px] flex h-5 w-5 items-center justify-center rounded-full border border-blue-300/50 bg-blue-500/15 text-blue-200 shadow-[0_0_18px_rgba(59,130,246,0.18)]"
              >
                <MessageSquareText className="h-3 w-3" />
              </span>
              <button
                type="submit"
                disabled={!isReady || loading}
                className="flex h-11 w-full items-center justify-center gap-2 rounded-lg border border-blue-300/25 bg-blue-600/90 px-4 text-sm font-semibold text-white transition hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-300 disabled:cursor-not-allowed disabled:opacity-55"
              >
                {loading ? 'Signing in…' : 'Continue'}
                {!loading && <ArrowRight aria-hidden="true" className="h-4 w-4" />}
              </button>
            </div>
          </form>

          <p className="mt-7 pl-8 text-sm text-slate-400">
            New to JARVIS?{' '}
            <Link
              href="/register"
              className="font-medium text-blue-300 transition hover:text-blue-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-300"
            >
              Create an account
            </Link>
          </p>

          <p className="mt-8 border-t border-white/[0.07] pt-5 text-xs leading-5 text-slate-400">
            Need help? Contact your system administrator.
          </p>
        </section>
      </div>
    </main>
  );
}
