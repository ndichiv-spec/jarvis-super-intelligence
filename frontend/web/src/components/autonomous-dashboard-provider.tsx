'use client';

import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { getAutonomousDashboardIntegration, AutonomousDashboardConfig } from '@/lib/autonomous-dashboard-integration';

interface AutonomousDashboardContextType {
  isInitialized: boolean;
  isInitializing: boolean;
  status: any;
  capabilities: any;
  error: string | null;
  enableAutonomousMode: () => Promise<void>;
  disableAutonomousMode: () => Promise<void>;
  performSystemCheck: () => Promise<void>;
  getSystemMetrics: () => any;
}

const AutonomousDashboardContext = createContext<AutonomousDashboardContextType | undefined>(undefined);

interface AutonomousDashboardProviderProps {
  children: ReactNode;
  config?: Partial<AutonomousDashboardConfig>;
}

export function AutonomousDashboardProvider({ children, config }: AutonomousDashboardProviderProps) {
  const [isInitialized, setIsInitialized] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [status, setStatus] = useState<any>(null);
  const [capabilities, setCapabilities] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    initializeAutonomousDashboard();
  }, []);

  const initializeAutonomousDashboard = async () => {
    if (isInitializing || isInitialized) return;

    setIsInitializing(true);
    setError(null);

    try {
      console.log('Initializing Autonomous Dashboard Provider...');
      
      const integration = getAutonomousDashboardIntegration(config);
      
      // Set up event listeners
      integration.on('initialized', (data: any) => {
        console.log('Autonomous Dashboard initialized:', data);
        setIsInitialized(true);
        setIsInitializing(false);
        setStatus(data.status);
        setCapabilities(integration.getAutonomousCapabilities());
      });

      integration.on('status_updated', (data: any) => {
        setStatus(data.status);
      });

      integration.on('error', (data: any) => {
        console.error('Autonomous Dashboard error:', data);
        setError(data.error?.message || 'Unknown error occurred');
      });

      integration.on('autonomous_mode_enabled', () => {
        console.log('Autonomous mode enabled');
        setCapabilities(integration.getAutonomousCapabilities());
      });

      integration.on('autonomous_mode_disabled', () => {
        console.log('Autonomous mode disabled');
        setCapabilities(integration.getAutonomousCapabilities());
      });

      // Initialize the integration
      await integration.initialize();
      
    } catch (err) {
      console.error('Failed to initialize Autonomous Dashboard:', err);
      setError(err instanceof Error ? err.message : 'Failed to initialize');
      setIsInitializing(false);
    }
  };

  const enableAutonomousMode = async () => {
    try {
      const integration = getAutonomousDashboardIntegration();
      await integration.enableAutonomousMode();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to enable autonomous mode');
    }
  };

  const disableAutonomousMode = async () => {
    try {
      const integration = getAutonomousDashboardIntegration();
      await integration.disableAutonomousMode();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to disable autonomous mode');
    }
  };

  const performSystemCheck = async () => {
    try {
      const integration = getAutonomousDashboardIntegration();
      await integration.performSystemCheck();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'System check failed');
    }
  };

  const getSystemMetrics = () => {
    try {
      const integration = getAutonomousDashboardIntegration();
      return integration.getSystemMetrics();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to get system metrics');
      return null;
    }
  };

  const value: AutonomousDashboardContextType = {
    isInitialized,
    isInitializing,
    status,
    capabilities,
    error,
    enableAutonomousMode,
    disableAutonomousMode,
    performSystemCheck,
    getSystemMetrics,
  };

  return (
    <AutonomousDashboardContext.Provider value={value}>
      {children}
    </AutonomousDashboardContext.Provider>
  );
}

export function useAutonomousDashboard() {
  const context = useContext(AutonomousDashboardContext);
  if (context === undefined) {
    throw new Error('useAutonomousDashboard must be used within an AutonomousDashboardProvider');
  }
  return context;
}

export default AutonomousDashboardProvider;
