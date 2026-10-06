'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { jarvisAPI } from '@/lib/api';

export default function VerifyEmailPage() {
  const [status, setStatus] = useState<'verifying' | 'verified' | 'failed'>('verifying');

  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get('token');
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
    if (!token) {
      setStatus('failed');
      return;
    }
    jarvisAPI.verifyEmail(token).then(
      () => setStatus('verified'),
      () => setStatus('failed')
    );
  }, []);

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-950 px-4 text-white">
      <section className="w-full max-w-md rounded-2xl border border-gray-700 bg-gray-900 p-8 text-center">
        <h1 className="mb-4 text-3xl font-bold">JARVIS</h1>
        <p role="status" className="mb-6 text-gray-300">
          {status === 'verifying' && 'Verifying your email address…'}
          {status === 'verified' && 'Email verified. You can now sign in.'}
          {status === 'failed' && 'This verification link is invalid or expired.'}
        </p>
        {status === 'verified' && (
          <Link href="/login" className="rounded bg-purple-700 px-5 py-3 text-white">
            Continue to sign in
          </Link>
        )}
        {status === 'failed' && (
          <Link href="/register" className="text-purple-300 hover:text-purple-200">
            Return to registration
          </Link>
        )}
      </section>
    </main>
  );
}
