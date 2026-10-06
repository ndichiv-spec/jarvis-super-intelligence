'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { jarvisAPI } from '@/lib/api';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [resetMode, setResetMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get('token');
    if (token) {
      setResetToken(token);
      setResetMode(true);
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
    }
  }, []);

  const handleRequest = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const result = await jarvisAPI.forgotPassword(email);
      setSuccess(result.message);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to process the recovery request.');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setSuccess('');
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    try {
      await jarvisAPI.resetPassword(resetToken, newPassword);
      setSuccess('Password reset. Sign in with your new password.');
      setResetToken('');
      setNewPassword('');
      setConfirmPassword('');
      setResetMode(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to reset your password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-950 px-4 text-white">
      <section className="w-full max-w-md rounded-2xl border border-gray-700 bg-gray-900 p-8">
        <h1 className="mb-2 text-3xl font-bold">JARVIS</h1>
        <h2 className="mb-6 text-xl font-semibold">
          {resetMode ? 'Choose a new password' : 'Recover your account'}
        </h2>

        {error && <p className="mb-4 rounded bg-red-950 p-3 text-red-200" role="alert">{error}</p>}
        {success && <p className="mb-4 rounded bg-green-950 p-3 text-green-200" role="status">{success}</p>}

        {resetMode ? (
          <form onSubmit={handleReset} className="space-y-4">
            <label className="block text-sm">
              New password
              <input
                type="password"
                autoComplete="new-password"
                minLength={12}
                required
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                className="mt-1 w-full rounded border border-gray-600 bg-gray-800 p-3"
              />
            </label>
            <label className="block text-sm">
              Confirm new password
              <input
                type="password"
                autoComplete="new-password"
                minLength={12}
                required
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                className="mt-1 w-full rounded border border-gray-600 bg-gray-800 p-3"
              />
            </label>
            <button disabled={loading} className="w-full rounded bg-purple-700 p-3 disabled:opacity-50">
              {loading ? 'Resetting…' : 'Reset password'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleRequest} className="space-y-4">
            <label className="block text-sm">
              Email address
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-1 w-full rounded border border-gray-600 bg-gray-800 p-3"
              />
            </label>
            <p className="text-sm text-gray-400">
              If the account exists, recovery instructions will be sent to its email address.
            </p>
            <button disabled={loading} className="w-full rounded bg-purple-700 p-3 disabled:opacity-50">
              {loading ? 'Sending…' : 'Send recovery link'}
            </button>
          </form>
        )}

        <p className="mt-6 text-sm text-gray-400">
          <Link href="/login" className="text-purple-300 hover:text-purple-200">Return to sign in</Link>
        </p>
      </section>
    </main>
  );
}
