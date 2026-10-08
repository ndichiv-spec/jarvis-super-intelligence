'use client';

import React, { useState, useEffect } from 'react';
import { jarvisAPI, SessionInfo } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';
import { useRouter } from 'next/navigation';

export default function SessionsPage() {
  const router = useRouter();
  const { isAuthenticated, token } = useAuthStore();
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login');
      return;
    }
    fetchSessions();
  }, [isAuthenticated]);

  const fetchSessions = async () => {
    try {
      const data = await jarvisAPI.getSessions();
      setSessions(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch sessions');
    } finally {
      setLoading(false);
    }
  };

  const handleRevokeSession = async (sessionId: string) => {
    try {
      await jarvisAPI.revokeSession(sessionId);
      await fetchSessions();
    } catch (err: any) {
      setError(err.message || 'Failed to revoke session');
    }
  };

  const handleRevokeAll = async () => {
    try {
      await jarvisAPI.revokeAllSessions();
      await fetchSessions();
    } catch (err: any) {
      setError(err.message || 'Failed to revoke all sessions');
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  const getTimeSince = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="text-white text-xl">Loading sessions...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 px-4 py-12">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-cyan-400 via-purple-400 to-pink-400 bg-clip-text text-transparent mb-2">
            Active Sessions
          </h1>
          <p className="text-gray-400">Manage your active login sessions across devices</p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Revoke All Button */}
        {sessions.length > 1 && (
          <div className="mb-6">
            <button
              onClick={handleRevokeAll}
              className="px-4 py-2 bg-red-600/20 hover:bg-red-600/30 border border-red-500/50 text-red-300 rounded-lg transition-all text-sm"
            >
              Revoke All Other Sessions
            </button>
          </div>
        )}

        {/* Sessions List */}
        <div className="space-y-4">
          {sessions.map((session) => (
            <div
              key={session.id}
              className="bg-gray-800/50 backdrop-blur-lg rounded-xl p-6 border border-gray-700/50"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    {/* Device Icon */}
                    <div className="w-10 h-10 bg-purple-500/20 rounded-lg flex items-center justify-center">
                      {session.device.toLowerCase().includes('mobile') ? (
                        <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                        </svg>
                      ) : session.device.toLowerCase().includes('tablet') ? (
                        <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                        </svg>
                      ) : (
                        <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                      )}
                    </div>
                    <div>
                      <h3 className="text-white font-semibold">
                        {session.device}
                        {session.is_current && (
                          <span className="ml-2 px-2 py-0.5 bg-green-500/20 text-green-300 text-xs rounded-full">
                            Current
                          </span>
                        )}
                      </h3>
                      {session.ip_address && (
                        <p className="text-gray-400 text-sm">IP: {session.ip_address}</p>
                      )}
                    </div>
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-gray-500">Created</p>
                      <p className="text-gray-300">{formatDate(session.created_at)}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Last Active</p>
                      <p className="text-gray-300">{getTimeSince(session.last_active_at)}</p>
                    </div>
                  </div>

                  {session.user_agent && (
                    <p className="mt-2 text-xs text-gray-500 truncate">
                      {session.user_agent}
                    </p>
                  )}
                </div>

                {/* Revoke Button */}
                {!session.is_current && (
                  <button
                    onClick={() => handleRevokeSession(session.id)}
                    className="px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 border border-red-500/50 text-red-300 rounded-lg transition-all text-sm"
                  >
                    Revoke
                  </button>
                )}
              </div>
            </div>
          ))}

          {sessions.length === 0 && (
            <div className="bg-gray-800/50 backdrop-blur-lg rounded-xl p-12 border border-gray-700/50 text-center">
              <p className="text-gray-400">No active sessions found</p>
            </div>
          )}
        </div>

        {/* Back to Dashboard */}
        <div className="mt-8 text-center">
          <button
            onClick={() => router.push('/dashboard')}
            className="text-purple-400 hover:text-purple-300 transition-colors"
          >
            ← Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
