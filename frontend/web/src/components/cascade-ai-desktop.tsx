'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Progress } from '@/components/ui/progress';
import { 
  AlertTriangle, 
  CheckCircle, 
  Clock, 
  Code, 
  Terminal, 
  Zap, 
  Activity,
  AlertCircle,
  Loader2,
  Eye,
  Play,
  Pause
} from 'lucide-react';

interface ErrorData {
  id: string;
  error: {
    id: string;
    timestamp: string;
    severity: string;
    category: string;
    file_path: string;
    line_number: number;
    error_message: string;
    code_snippet: string;
    stack_trace: string;
    context: any;
    auto_fix_available: boolean;
    implementation_status: string;
  };
  status: string;
  timestamp: string;
  priority: number;
  implementation_result?: any;
}

interface VirtualDesktopData {
  system_status: string;
  cascade_ai_status: string;
  last_update: string;
  total_errors: number;
  pending_implementations: number;
  completed_implementations: number;
  last_event?: {
    type: string;
    data: any;
    timestamp: string;
  };
}

interface CascadeAIDesktopProps {
  className?: string;
}

export function CascadeAIDesktop({ className }: CascadeAIDesktopProps) {
  const [desktopData, setDesktopData] = useState<VirtualDesktopData | null>(null);
  const [errors, setErrors] = useState<ErrorData[]>([]);
  const [selectedError, setSelectedError] = useState<ErrorData | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch data from JARVIS Cascade integration
  const fetchCascadeData = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/cascade-ai/status');
      if (response.ok) {
        const data = await response.json();
        const desktopData = data.desktop_data ?? {};
        setDesktopData(desktopData);

        // Convert errors object to array
        const errorEntries = Object.entries(desktopData)
          .filter(([key]) => key.startsWith('error_'))
          .map(([key, value]) => value as ErrorData);
        
        setErrors(errorEntries.sort((a, b) => b.priority - a.priority));
      }
    } catch (error) {
      console.error('Failed to fetch Cascade AI data:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initialize connection to JARVIS Cascade integration
  const initializeConnection = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/cascade-ai/initialize', {
        method: 'POST'
      });
      
      if (response.ok) {
        setIsConnected(true);
        console.log('Connected to JARVIS Cascade AI integration');
      }
    } catch (error) {
      console.error('Failed to connect to Cascade AI:', error);
    }
  }, []);

  useEffect(() => {
    initializeConnection();
    
    // Set up polling for real-time updates
    const interval = setInterval(fetchCascadeData, 2000); // Update every 2 seconds
    
    return () => clearInterval(interval);
  }, [fetchCascadeData, initializeConnection]);

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'bg-red-500';
      case 'high': return 'bg-orange-500';
      case 'medium': return 'bg-yellow-500';
      case 'low': return 'bg-green-500';
      default: return 'bg-gray-500';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-600';
      case 'implementing': return 'text-blue-600';
      case 'pending': return 'text-yellow-600';
      case 'failed': return 'text-red-600';
      default: return 'text-gray-600';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-4 h-4" />;
      case 'implementing': return <Loader2 className="w-4 h-4 animate-spin" />;
      case 'pending': return <Clock className="w-4 h-4" />;
      case 'failed': return <AlertCircle className="w-4 h-4" />;
      default: return <AlertTriangle className="w-4 h-4" />;
    }
  };

  const handleFixError = async (errorId: string) => {
    try {
      const response = await fetch(`/api/v1/cascade-ai/fix/${errorId}`, {
        method: 'POST'
      });
      
      if (response.ok) {
        console.log(`Fix initiated for error ${errorId}`);
        // Refresh data
        fetchCascadeData();
      }
    } catch (error) {
      console.error('Failed to initiate fix:', error);
    }
  };

  const handleViewError = (error: ErrorData) => {
    setSelectedError(error);
  };

  if (isLoading) {
    return (
      <div className={`p-6 ${className}`}>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin" />
          <span className="ml-2">Initializing Cascade AI Desktop...</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`p-6 space-y-4 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Terminal className="w-6 h-6 text-blue-500" />
          <h2 className="text-2xl font-bold">Cascade AI Desktop</h2>
          <Badge variant={isConnected ? "default" : "destructive"}>
            {isConnected ? "Connected" : "Disconnected"}
          </Badge>
        </div>
        <div className="flex items-center space-x-2">
          <Activity className="w-4 h-4" />
          <span className="text-sm text-gray-500">
            Last Update: {desktopData?.last_update ? new Date(desktopData.last_update).toLocaleTimeString() : 'Never'}
          </span>
        </div>
      </div>

      {/* System Status */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">System Status</p>
                <p className="text-2xl font-bold text-green-600">
                  {desktopData?.system_status || 'Unknown'}
                </p>
              </div>
              <Activity className="w-8 h-8 text-green-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Total Errors</p>
                <p className="text-2xl font-bold text-orange-600">
                  {desktopData?.total_errors || 0}
                </p>
              </div>
              <AlertTriangle className="w-8 h-8 text-orange-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Pending</p>
                <p className="text-2xl font-bold text-yellow-600">
                  {desktopData?.pending_implementations || 0}
                </p>
              </div>
              <Clock className="w-8 h-8 text-yellow-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Completed</p>
                <p className="text-2xl font-bold text-green-600">
                  {desktopData?.completed_implementations || 0}
                </p>
              </div>
              <CheckCircle className="w-8 h-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Error List */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <AlertTriangle className="w-5 h-5" />
                <span>Error Queue</span>
                <Badge variant="secondary">{errors.length}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-96">
                <div className="space-y-2">
                  {errors.map((error) => (
                    <div
                      key={error.error.id}
                      className="p-3 border rounded-lg hover:bg-gray-50 cursor-pointer transition-colors"
                      onClick={() => handleViewError(error)}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center space-x-2 mb-1">
                            <Badge className={getSeverityColor(error.error.severity)}>
                              {error.error.severity}
                            </Badge>
                            <Badge variant="outline">
                              {error.error.category}
                            </Badge>
                            <span className={`text-sm ${getStatusColor(error.error.implementation_status)}`}>
                              {getStatusIcon(error.error.implementation_status)}
                              <span className="ml-1">{error.error.implementation_status}</span>
                            </span>
                          </div>
                          <p className="text-sm font-medium text-gray-900">
                            {error.error.error_message}
                          </p>
                          <p className="text-xs text-gray-500">
                            {error.error.file_path}:{error.error.line_number}
                          </p>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleFixError(error.error.id);
                            }}
                            disabled={error.error.implementation_status === 'implementing'}
                          >
                            {error.error.implementation_status === 'implementing' ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Zap className="w-4 h-4" />
                            )}
                          </Button>
                        </div>
                      </div>
                      
                      {error.error.implementation_status === 'implementing' && (
                        <div className="mt-2">
                          <Progress value={50} className="h-2" />
                        </div>
                      )}
                    </div>
                  ))}
                  
                  {errors.length === 0 && (
                    <div className="text-center py-8">
                      <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-2" />
                      <p className="text-gray-500">No errors detected</p>
                    </div>
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>

        {/* Error Details */}
        <div className="space-y-4">
          {selectedError ? (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Code className="w-5 h-5" />
                  <span>Error Details</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <h4 className="font-medium text-gray-900">Error Message</h4>
                    <p className="text-sm text-gray-600 mt-1">
                      {selectedError.error.error_message}
                    </p>
                  </div>
                  
                  <div>
                    <h4 className="font-medium text-gray-900">Location</h4>
                    <p className="text-sm text-gray-600 mt-1">
                      {selectedError.error.file_path}:{selectedError.error.line_number}
                    </p>
                  </div>
                  
                  <div>
                    <h4 className="font-medium text-gray-900">Code Snippet</h4>
                    <pre className="bg-gray-100 p-2 rounded text-xs mt-1 overflow-x-auto">
                      {selectedError.error.code_snippet}
                    </pre>
                  </div>
                  
                  {selectedError.implementation_result && (
                    <div>
                      <h4 className="font-medium text-gray-900">Implementation Result</h4>
                      <div className="mt-1 space-y-2">
                        <div className="flex items-center space-x-2">
                          <span className="text-sm text-gray-600">Status:</span>
                          <Badge variant={selectedError.implementation_result.status === 'success' ? 'default' : 'destructive'}>
                            {selectedError.implementation_result.status}
                          </Badge>
                        </div>
                        
                        {selectedError.implementation_result.changes_made.length > 0 && (
                          <div>
                            <span className="text-sm text-gray-600">Changes Made:</span>
                            <ul className="text-sm text-gray-600 mt-1 ml-4">
                              {selectedError.implementation_result.changes_made.map((change: string, index: number) => (
                                <li key={index}>{change}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  
                  <div className="flex space-x-2">
                    <Button
                      size="sm"
                      onClick={() => handleFixError(selectedError.error.id)}
                      disabled={selectedError.error.implementation_status === 'implementing'}
                    >
                      {selectedError.error.implementation_status === 'implementing' ? (
                        <Loader2 className="w-4 h-4 animate-spin mr-2" />
                      ) : (
                        <Zap className="w-4 h-4 mr-2" />
                      )}
                      Fix Error
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setSelectedError(null)}
                    >
                      Close
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="p-6 text-center">
                <Eye className="w-12 h-12 text-gray-400 mx-auto mb-2" />
                <p className="text-gray-500">Select an error to view details</p>
              </CardContent>
            </Card>
          )}
          
          {/* System Activity */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Activity className="w-5 h-5" />
                <span>System Activity</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">Cascade AI Status</span>
                  <Badge variant={desktopData?.cascade_ai_status === 'connected' ? 'default' : 'destructive'}>
                    {desktopData?.cascade_ai_status || 'Unknown'}
                  </Badge>
                </div>
                
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">Auto-Fix Available</span>
                  <Badge variant="secondary">
                    {errors.filter(e => e.error.auto_fix_available).length} errors
                  </Badge>
                </div>
                
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">Critical Errors</span>
                  <Badge variant="destructive">
                    {errors.filter(e => e.error.severity === 'critical').length}
                  </Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default CascadeAIDesktop;
