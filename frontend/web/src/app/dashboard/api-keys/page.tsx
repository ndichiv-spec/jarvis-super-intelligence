'use client';

import React, { useState, useEffect } from 'react';
import { jarvisAPI, APIKeyInfo, APIKeyCreate } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';
import { useRouter } from 'next/navigation';

export default function ApiKeysPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const [apiKeys, setApiKeys] = useState<APIKeyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newKey, setNewKey] = useState<{ key: string } | null>(null);
  const [creating, setCreating] = useState(false);

  // Create form state
  const [keyName, setKeyName] = useState('');
  const [keyDescription, setKeyDescription] = useState('');
  const [keyScopes, setKeyScopes] = useState<string[]>(['read', 'write']);
  const [keyExpiresInDays, setKeyExpiresInDays] = useState<number | undefined>(undefined);

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/login');
      return;
    }
    fetchApiKeys();
  }, [isAuthenticated]);

  const fetchApiKeys = async () => {
    try {
      const data = await jarvisAPI.getApiKeys();
      setApiKeys(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch API keys');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setCreating(true);

    try {
      const data: APIKeyCreate = {
        name: keyName,
        description: keyDescription || undefined,
        scopes: keyScopes,
        expires_in_days: keyExpiresInDays,
      };

      const response = await jarvisAPI.createApiKey(data);
      setNewKey({ key: response.key });
      await fetchApiKeys();
      setShowCreateModal(false);
      setKeyName('');
      setKeyDescription('');
    } catch (err: any) {
      setError(err.message || 'Failed to create API key');
    } finally {
      setCreating(false);
    }
  };

  const handleRevokeKey = async (keyId: string) => {
    if (!confirm('Are you sure you want to revoke this API key? This action cannot be undone.')) {
      return;
    }

    try {
      await jarvisAPI.revokeApiKey(keyId);
      await fetchApiKeys();
    } catch (err: any) {
      setError(err.message || 'Failed to revoke API key');
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString();
  };

  const toggleScope = (scope: string) => {
    setKeyScopes(prev =>
      prev.includes(scope)
        ? prev.filter(s => s !== scope)
        : [...prev, scope]
    );
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="text-white text-xl">Loading API keys...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 px-4 py-12">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold bg-gradient-to-r from-cyan-400 via-purple-400 to-pink-400 bg-clip-text text-transparent mb-2">
              API Keys
            </h1>
            <p className="text-gray-400">Manage your API keys for programmatic access</p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-gradient-to-r from-purple-600 to-cyan-600 hover:from-purple-700 hover:to-cyan-700 text-white font-semibold rounded-lg transition-all"
          >
            Create New Key
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* API Keys List */}
        <div className="space-y-4">
          {apiKeys.map((apiKey) => (
            <div
              key={apiKey.id}
              className="bg-gray-800/50 backdrop-blur-lg rounded-xl p-6 border border-gray-700/50"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="w-10 h-10 bg-cyan-500/20 rounded-lg flex items-center justify-center">
                      <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="text-white font-semibold">{apiKey.name}</h3>
                      <p className="text-gray-400 text-sm font-mono">{apiKey.prefix}••••••••••••••••••</p>
                    </div>
                  </div>

                  {apiKey.description && (
                    <p className="text-gray-400 text-sm mb-2">{apiKey.description}</p>
                  )}

                  <div className="mt-3 flex gap-2">
                    {apiKey.scopes.map((scope) => (
                      <span
                        key={scope}
                        className="px-2 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded-full"
                      >
                        {scope}
                      </span>
                    ))}
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-gray-500">Created</p>
                      <p className="text-gray-300">{formatDate(apiKey.created_at)}</p>
                    </div>
                    {apiKey.expires_at && (
                      <div>
                        <p className="text-gray-500">Expires</p>
                        <p className="text-gray-300">{formatDate(apiKey.expires_at)}</p>
                      </div>
                    )}
                    {apiKey.last_used_at && (
                      <div>
                        <p className="text-gray-500">Last Used</p>
                        <p className="text-gray-300">{formatDate(apiKey.last_used_at)}</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Revoke Button */}
                <button
                  onClick={() => handleRevokeKey(apiKey.id)}
                  className="px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 border border-red-500/50 text-red-300 rounded-lg transition-all text-sm"
                >
                  Revoke
                </button>
              </div>
            </div>
          ))}

          {apiKeys.length === 0 && (
            <div className="bg-gray-800/50 backdrop-blur-lg rounded-xl p-12 border border-gray-700/50 text-center">
              <svg className="w-16 h-16 mx-auto text-gray-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
              </svg>
              <p className="text-gray-400 mb-2">No API keys found</p>
              <p className="text-gray-500 text-sm">Create your first API key to get started</p>
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

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 px-4">
          <div className="bg-gray-800 rounded-2xl p-8 border border-gray-700/50 shadow-2xl max-w-md w-full">
            <h2 className="text-2xl font-semibold text-white mb-6">Create API Key</h2>

            {newKey ? (
              <div>
                <div className="mb-4 p-3 bg-yellow-500/20 border border-yellow-500/50 rounded-lg text-yellow-300 text-sm">
                  ⚠️ Save this key now! It will not be shown again.
                </div>
                <div className="bg-gray-900 p-4 rounded-lg font-mono text-sm text-green-400 break-all mb-4">
                  {newKey.key}
                </div>
                <button
                  onClick={() => {
                    setNewKey(null);
                    setShowCreateModal(false);
                  }}
                  className="w-full py-3 bg-gradient-to-r from-purple-600 to-cyan-600 text-white font-semibold rounded-lg transition-all"
                >
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={handleCreateKey} className="space-y-5">
                {/* Name */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Key Name <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="text"
                    value={keyName}
                    onChange={(e) => setKeyName(e.target.value)}
                    className="w-full px-4 py-3 bg-gray-700/50 border border-gray-600/50 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                    placeholder="e.g., Production API Key"
                    required
                    disabled={creating}
                  />
                </div>

                {/* Description */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Description <span className="text-gray-500">(optional)</span>
                  </label>
                  <input
                    type="text"
                    value={keyDescription}
                    onChange={(e) => setKeyDescription(e.target.value)}
                    className="w-full px-4 py-3 bg-gray-700/50 border border-gray-600/50 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                    placeholder="What will this key be used for?"
                    disabled={creating}
                  />
                </div>

                {/* Scopes */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Permissions
                  </label>
                  <div className="space-y-2">
                    {['read', 'write', 'delete', 'admin'].map((scope) => (
                      <label key={scope} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={keyScopes.includes(scope)}
                          onChange={() => toggleScope(scope)}
                          className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-purple-600 focus:ring-purple-500"
                          disabled={creating}
                        />
                        <span className="text-gray-300 capitalize">{scope}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Expiration */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Expiration <span className="text-gray-500">(optional)</span>
                  </label>
                  <select
                    value={keyExpiresInDays || ''}
                    onChange={(e) => setKeyExpiresInDays(e.target.value ? parseInt(e.target.value) : undefined)}
                    className="w-full px-4 py-3 bg-gray-700/50 border border-gray-600/50 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                    disabled={creating}
                  >
                    <option value="">Never expire</option>
                    <option value="30">30 days</option>
                    <option value="90">90 days</option>
                    <option value="180">180 days</option>
                    <option value="365">1 year</option>
                  </select>
                </div>

                {/* Buttons */}
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="flex-1 py-3 bg-gray-700 hover:bg-gray-600 text-white font-semibold rounded-lg transition-all"
                    disabled={creating}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={creating}
                    className="flex-1 py-3 bg-gradient-to-r from-purple-600 to-cyan-600 hover:from-purple-700 hover:to-cyan-700 text-white font-semibold rounded-lg transition-all disabled:opacity-50"
                  >
                    {creating ? 'Creating...' : 'Create Key'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
