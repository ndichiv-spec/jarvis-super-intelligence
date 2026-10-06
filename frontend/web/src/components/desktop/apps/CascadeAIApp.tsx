'use client';

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Progress } from '@/components/ui/progress';
import { 
  Terminal, 
  AlertTriangle, 
  CheckCircle, 
  Clock, 
  Code, 
  Zap, 
  Activity,
  Loader2,
  Eye,
  Play,
  Pause,
  Settings,
  RefreshCw,
  Monitor,
  Cpu,
  Shield
} from 'lucide-react';
import { CascadeAIDesktop } from '@/components/cascade-ai-desktop';

interface CascadeAIAppProps {
  appId: string;
  onClose: () => void;
  onMinimize: () => void;
  onMaximize: () => void;
}

export function CascadeAIApp({ appId, onClose, onMinimize, onMaximize }: CascadeAIAppProps) {
  const [activeTab, setActiveTab] = useState<'desktop' | 'workflow' | 'settings'>('desktop');
  const [isConnected, setIsConnected] = useState(false);
  const [systemStatus, setSystemStatus] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Check connection status
    checkConnectionStatus();
    
    // Set up periodic status updates
    const interval = setInterval(checkConnectionStatus, 5000);
    
    return () => clearInterval(interval);
  }, []);

  const checkConnectionStatus = async () => {
    try {
      setIsLoading(true);
      const response = await fetch('/api/v1/cascade-ai/health');
      const data = await response.json();
      setIsConnected(data.status === 'healthy');
      setSystemStatus(data);
    } catch (error) {
      setIsConnected(false);
    } finally {
      setIsLoading(false);
    }
  };

  const handleInitialize = async () => {
    try {
      const response = await fetch('/api/v1/cascade-ai/initialize', {
        method: 'POST'
      });
      
      if (response.ok) {
        setIsConnected(true);
        checkConnectionStatus();
      }
    } catch (error) {
      console.error('Failed to initialize Cascade AI:', error);
    }
  };

  const handleCreateTestError = async () => {
    try {
      const response = await fetch('/api/v1/cascade-ai/test-error', {
        method: 'POST'
      });
      
      if (response.ok) {
        console.log('Test error created');
      }
    } catch (error) {
      console.error('Failed to create test error:', error);
    }
  };

  return (
    <div className="h-full flex flex-col bg-gray-900 text-white">
      {/* App Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <div className="flex items-center space-x-3">
          <Terminal className="w-6 h-6 text-blue-400" />
          <div>
            <h2 className="text-lg font-semibold">Cascade AI Integration</h2>
            <p className="text-sm text-gray-400">JARVIS Error Detection & Auto-Fix</p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant={isConnected ? "default" : "destructive"}>
            {isConnected ? "Connected" : "Disconnected"}
          </Badge>
          <Button size="sm" variant="outline" onClick={onMinimize}>
            <Pause className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex space-x-1 p-4 border-b border-gray-700">
        <Button
          variant={activeTab === 'desktop' ? 'default' : 'ghost'}
          size="sm"
          onClick={() => setActiveTab('desktop')}
          className="text-white"
        >
          <Monitor className="w-4 h-4 mr-2" />
          Desktop
        </Button>
        <Button
          variant={activeTab === 'workflow' ? 'default' : 'ghost'}
          size="sm"
          onClick={() => setActiveTab('workflow')}
          className="text-white"
        >
          <Activity className="w-4 h-4 mr-2" />
          Workflow
        </Button>
        <Button
          variant={activeTab === 'settings' ? 'default' : 'ghost'}
          size="sm"
          onClick={() => setActiveTab('settings')}
          className="text-white"
        >
          <Settings className="w-4 h-4 mr-2" />
          Settings
        </Button>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'desktop' && (
          <div className="h-full">
            {isLoading ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <Loader2 className="w-8 h-8 animate-spin mx-auto mb-4" />
                  <p className="text-gray-400">Initializing Cascade AI...</p>
                </div>
              </div>
            ) : (
              <div className="h-full overflow-auto">
                <CascadeAIDesktop className="p-4" />
              </div>
            )}
          </div>
        )}

        {activeTab === 'workflow' && (
          <div className="p-4 space-y-4 overflow-auto">
            {/* Connection Status */}
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-3">
                <CardTitle className="text-white flex items-center space-x-2">
                  <Activity className="w-5 h-5" />
                  <span>Implementation Workflow</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3 bg-gray-700 rounded-lg">
                    <div className="flex items-center space-x-2">
                      <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
                      <span className="font-medium">
                        {isConnected ? 'Cascade AI Connected' : 'Cascade AI Disconnected'}
                      </span>
                    </div>
                    {!isConnected && (
                      <Button size="sm" onClick={handleInitialize}>
                        <Play className="w-4 h-4 mr-2" />
                        Initialize
                      </Button>
                    )}
                  </div>

                  {/* System Status */}
                  {systemStatus && (
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-3 bg-gray-700 rounded-lg">
                        <p className="text-sm text-gray-400">Total Errors</p>
                        <p className="text-xl font-bold text-white">{systemStatus.total_errors || 0}</p>
                      </div>
                      <div className="p-3 bg-gray-700 rounded-lg">
                        <p className="text-sm text-gray-400">System Status</p>
                        <p className="text-xl font-bold text-green-400">{systemStatus.system_status || 'Unknown'}</p>
                      </div>
                    </div>
                  )}

                  {/* Test Controls */}
                  <div className="space-y-2">
                    <h4 className="font-medium text-white">Test Controls</h4>
                    <div className="flex space-x-2">
                      <Button size="sm" onClick={handleCreateTestError}>
                        <AlertTriangle className="w-4 h-4 mr-2" />
                        Create Test Error
                      </Button>
                      <Button size="sm" variant="outline" onClick={checkConnectionStatus}>
                        <RefreshCw className="w-4 h-4 mr-2" />
                        Refresh Status
                      </Button>
                    </div>
                  </div>

                  {/* Workflow Steps */}
                  <div className="space-y-2">
                    <h4 className="font-medium text-white">Implementation Workflow</h4>
                    <div className="space-y-2">
                      <div className="flex items-center space-x-2 p-2 bg-gray-700 rounded">
                        <div className="w-4 h-4 rounded-full bg-green-500" />
                        <span className="text-sm">1. Error Detection</span>
                      </div>
                      <div className="flex items-center space-x-2 p-2 bg-gray-700 rounded">
                        <div className="w-4 h-4 rounded-full bg-blue-500" />
                        <span className="text-sm">2. Error Analysis</span>
                      </div>
                      <div className="flex items-center space-x-2 p-2 bg-gray-700 rounded">
                        <div className="w-4 h-4 rounded-full bg-yellow-500" />
                        <span className="text-sm">3. Solution Planning</span>
                      </div>
                      <div className="flex items-center space-x-2 p-2 bg-gray-700 rounded">
                        <div className="w-4 h-4 rounded-full bg-orange-500" />
                        <span className="text-sm">4. Implementation</span>
                      </div>
                      <div className="flex items-center space-x-2 p-2 bg-gray-700 rounded">
                        <div className="w-4 h-4 rounded-full bg-purple-500" />
                        <span className="text-sm">5. Verification</span>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="p-4 space-y-4 overflow-auto">
            <Card className="bg-gray-800 border-gray-700">
              <CardHeader className="pb-3">
                <CardTitle className="text-white flex items-center space-x-2">
                  <Settings className="w-5 h-5" />
                  <span>Cascade AI Settings</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="space-y-2">
                    <h4 className="font-medium text-white">Monitoring Settings</h4>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between p-2 bg-gray-700 rounded">
                        <span className="text-sm">Auto-fix Enabled</span>
                        <Badge variant="default">Enabled</Badge>
                      </div>
                      <div className="flex items-center justify-between p-2 bg-gray-700 rounded">
                        <span className="text-sm">Real-time Monitoring</span>
                        <Badge variant="default">Active</Badge>
                      </div>
                      <div className="flex items-center justify-between p-2 bg-gray-700 rounded">
                        <span className="text-sm">Error Severity Threshold</span>
                        <Badge variant="outline">Medium</Badge>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <h4 className="font-medium text-white">Integration Settings</h4>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between p-2 bg-gray-700 rounded">
                        <span className="text-sm">JARVIS Core Integration</span>
                        <Badge variant="default">Connected</Badge>
                      </div>
                      <div className="flex items-center justify-between p-2 bg-gray-700 rounded">
                        <span className="text-sm">Virtual Desktop Display</span>
                        <Badge variant="default">Active</Badge>
                      </div>
                      <div className="flex items-center justify-between p-2 bg-gray-700 rounded">
                        <span className="text-sm">API Endpoint</span>
                        <Badge variant="outline">/api/v1/cascade-ai</Badge>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <h4 className="font-medium text-white">Performance Settings</h4>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between p-2 bg-gray-700 rounded">
                        <span className="text-sm">Max Concurrent Fixes</span>
                        <Badge variant="outline">5</Badge>
                      </div>
                      <div className="flex items-center justify-between p-2 bg-gray-700 rounded">
                        <span className="text-sm">Fix Timeout (seconds)</span>
                        <Badge variant="outline">60</Badge>
                      </div>
                      <div className="flex items-center justify-between p-2 bg-gray-700 rounded">
                        <span className="text-sm">Retry Attempts</span>
                        <Badge variant="outline">3</Badge>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

export default CascadeAIApp;
