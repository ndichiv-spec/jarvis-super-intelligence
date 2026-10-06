'use client';

import React, { useState, useEffect } from 'react';
import { getApiUrl } from '@/lib/runtime-url';

export default function TestPage() {
  const [backendStatus, setBackendStatus] = useState<string>('Loading...');
  const [error, setError] = useState<string>('');

  useEffect(() => {
    // Test backend connection
    fetch(getApiUrl('/health'))
      .then(response => response.json())
      .then(data => {
        setBackendStatus(`Connected: Status ${data.status}`);
      })
      .catch(err => {
        setError(`Backend error: ${err.message}`);
      });
  }, []);

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold mb-8 text-blue-400">
          JARVIS System Test Page
        </h1>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-gray-800 p-6 rounded-lg">
            <h2 className="text-xl font-semibold mb-4 text-green-400">
              Backend Connection
            </h2>
            {error ? (
              <p className="text-red-400">{error}</p>
            ) : (
              <p className="text-green-400">{backendStatus}</p>
            )}
          </div>
          
          <div className="bg-gray-800 p-6 rounded-lg">
            <h2 className="text-xl font-semibold mb-4 text-blue-400">
              Frontend Status
            </h2>
            <p className="text-blue-400">
              Next.js Running Successfully
            </p>
            <p className="text-gray-400">
              Port: 3001
            </p>
          </div>
        </div>
        
        <div className="mt-8 bg-gray-800 p-6 rounded-lg">
          <h2 className="text-xl font-semibold mb-4 text-yellow-400">
            System Features
          </h2>
          <ul className="space-y-2 text-gray-300">
            <li>✅ Drive Engine Integration</li>
            <li>✅ Component Management</li>
            <li>✅ AI Capabilities</li>
            <li>✅ Real-time Monitoring</li>
            <li>✅ Performance Optimization</li>
          </ul>
        </div>
        
        <div className="mt-8">
          <a 
            href="/dashboard" 
            className="bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded-lg inline-block text-white font-semibold"
          >
            Go to Dashboard
          </a>
        </div>
      </div>
    </div>
  );
}
