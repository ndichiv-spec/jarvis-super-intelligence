/**
 * Autonomous Monitoring and Healing System
 * =====================================
 * Self-healing, autonomous monitoring, and automatic recovery capabilities.
 * Provides real-time system health monitoring and automatic issue resolution.
 */

import { getAutonomousDashboard } from './autonomous-dashboard';
import { getAutonomousStateManager } from './autonomous-state-manager';

export interface HealthMetric {
  name: string;
  value: number;
  unit: string;
  threshold: {
    warning: number;
    critical: number;
  };
  status: 'healthy' | 'warning' | 'critical' | 'unknown';
  timestamp: Date;
  trend: 'improving' | 'stable' | 'degrading';
}

export interface SystemHealth {
  overall: 'optimal' | 'degraded' | 'critical' | 'offline';
  metrics: HealthMetric[];
  score: number; // 0-100
  lastCheck: Date;
  uptime: number;
  errorRate: number;
  performance: PerformanceMetrics;
}

export interface PerformanceMetrics {
  cpuUsage: number;
  memoryUsage: number;
  networkLatency: number;
  renderTime: number;
  bundleSize: number;
  cacheHitRate: number;
  errorRate: number;
  responseTime: number;
}

export interface HealingAction {
  id: string;
  type: 'restart' | 'clear_cache' | 'reduce_complexity' | 'enable_safe_mode' | 'rollback' | 'optimize_memory';
  severity: 'low' | 'medium' | 'high' | 'critical';
  description: string;
  executed: boolean;
  timestamp: Date;
  result?: 'success' | 'failed' | 'partial';
  error?: string;
}

export interface Anomaly {
  id: string;
  type: 'performance' | 'error' | 'security' | 'resource' | 'network';
  severity: 'low' | 'medium' | 'high' | 'critical';
  description: string;
  detectedAt: Date;
  resolved: boolean;
  resolvedAt?: Date;
  healingAction?: string;
}

export interface MonitoringConfig {
  checkInterval: number; // seconds
  retentionPeriod: number; // hours
  autoHealing: boolean;
  healingThreshold: number; // 0-100
  enablePredictiveAnalysis: boolean;
  enableAnomalyDetection: boolean;
  enablePerformanceOptimization: boolean;
  maxConcurrentHealingActions: number;
  healingCooldown: number; // seconds
}

class AutonomousMonitoring {
  private config: MonitoringConfig;
  private healthMetrics: Map<string, HealthMetric[]> = new Map();
  private healingActions: HealingAction[] = [];
  private anomalies: Anomaly[] = [];
  private monitoringTimer: NodeJS.Timeout | null = null;
  private healingTimer: NodeJS.Timeout | null = null;
  private isMonitoring = false;
  private healingInProgress = false;
  private lastHealingTime = 0;
  private eventListeners: Map<string, Function[]> = new Map();

  constructor(config: Partial<MonitoringConfig> = {}) {
    this.config = {
      checkInterval: 30, // 30 seconds
      retentionPeriod: 24, // 24 hours
      autoHealing: true,
      healingThreshold: 70, // Heal when health score < 70
      enablePredictiveAnalysis: true,
      enableAnomalyDetection: true,
      enablePerformanceOptimization: true,
      maxConcurrentHealingActions: 3,
      healingCooldown: 300, // 5 minutes
      ...config
    };
  }

  async initialize(): Promise<void> {
    try {
      // Load historical data
      await this.loadHistoricalData();

      // Start monitoring
      this.startMonitoring();

      // Start healing if enabled
      if (this.config.autoHealing) {
        this.startHealing();
      }

      console.log('Autonomous Monitoring initialized successfully');
    } catch (error) {
      console.error('Failed to initialize Autonomous Monitoring:', error);
      throw error;
    }
  }

  private async loadHistoricalData(): Promise<void> {
    try {
      const stateManager = getAutonomousStateManager();
      const historicalData = stateManager.get('monitoring_history');
      
      if (historicalData) {
        this.healthMetrics = new Map(Object.entries(historicalData));
        console.log(`Loaded historical data for ${this.healthMetrics.size} metrics`);
      }
    } catch (error) {
      console.error('Failed to load historical data:', error);
    }
  }

  private startMonitoring(): void {
    if (this.isMonitoring) return;

    this.isMonitoring = true;
    this.monitoringTimer = setInterval(() => {
      this.performHealthCheck();
    }, this.config.checkInterval * 1000);

    // Initial check
    this.performHealthCheck();
    console.log('Health monitoring started');
  }

  private startHealing(): void {
    this.healingTimer = setInterval(() => {
      this.checkForHealingOpportunities();
    }, this.config.checkInterval * 1000);
    console.log('Auto-healing started');
  }

  private async performHealthCheck(): Promise<SystemHealth> {
    try {
      const metrics = await this.collectMetrics();
      const health = this.calculateSystemHealth(metrics);
      
      // Store metrics
      this.storeMetrics(metrics);
      
      // Detect anomalies
      if (this.config.enableAnomalyDetection) {
        this.detectAnomalies(metrics);
      }
      
      // Update state - disable to avoid localStorage errors
      // await this.updateMonitoringState(health);
      
      // Emit event
      this.emit('health_check', { health });
      
      return health;
    } catch (error) {
      console.error('Health check failed:', error);
      throw error;
    }
  }

  private async collectMetrics(): Promise<HealthMetric[]> {
    const metrics: HealthMetric[] = [];

    // CPU Usage
    const cpuUsage = await this.measureCPUUsage();
    metrics.push(this.createMetric('cpu_usage', cpuUsage, '%', 70, 90));

    // Memory Usage
    const memoryUsage = await this.measureMemoryUsage();
    metrics.push(this.createMetric('memory_usage', memoryUsage, '%', 80, 95));

    // Network Latency
    const networkLatency = await this.measureNetworkLatency();
    metrics.push(this.createMetric('network_latency', networkLatency, 'ms', 500, 1000));

    // Render Performance
    const renderTime = await this.measureRenderPerformance();
    metrics.push(this.createMetric('render_time', renderTime, 'ms', 100, 200));

    // Error Rate
    const errorRate = this.calculateErrorRate();
    metrics.push(this.createMetric('error_rate', errorRate, '%', 5, 15));

    // Cache Hit Rate
    const cacheHitRate = this.calculateCacheHitRate();
    metrics.push(this.createMetric('cache_hit_rate', cacheHitRate, '%', 70, 50));

    // Response Time
    const responseTime = await this.measureResponseTime();
    metrics.push(this.createMetric('response_time', responseTime, 'ms', 200, 500));

    return metrics;
  }

  private createMetric(name: string, value: number, unit: string, 
                       warningThreshold: number, criticalThreshold: number): HealthMetric {
    let status: HealthMetric['status'] = 'healthy';
    if (value >= criticalThreshold) {
      status = 'critical';
    } else if (value >= warningThreshold) {
      status = 'warning';
    }

    // Calculate trend
    const trend = this.calculateTrend(name, value);

    return {
      name,
      value,
      unit,
      threshold: {
        warning: warningThreshold,
        critical: criticalThreshold
      },
      status,
      timestamp: new Date(),
      trend
    };
  }

  private calculateTrend(metricName: string, currentValue: number): HealthMetric['trend'] {
    const history = this.healthMetrics.get(metricName);
    if (!history || history.length < 2) {
      return 'stable';
    }

    const recentValues = history.slice(-5).map(m => m.value);
    const average = recentValues.reduce((sum, val) => sum + val, 0) / recentValues.length;
    
    if (currentValue < average * 0.9) {
      return 'improving';
    } else if (currentValue > average * 1.1) {
      return 'degrading';
    }
    
    return 'stable';
  }

  private async measureCPUUsage(): Promise<number> {
    // Simulate CPU measurement
    if ('performance' in window && 'memory' in (performance as any)) {
      // Use performance memory as a proxy for CPU usage
      const memory = (performance as any).memory;
      return (memory.usedJSHeapSize / memory.totalJSHeapSize) * 100;
    }
    return Math.random() * 20 + 10; // 10-30%
  }

  private async measureMemoryUsage(): Promise<number> {
    if ('performance' in window && 'memory' in (performance as any)) {
      const memory = (performance as any).memory;
      return (memory.usedJSHeapSize / memory.jsHeapSizeLimit) * 100;
    }
    return Math.random() * 30 + 20; // 20-50%
  }

  private async measureNetworkLatency(): Promise<number> {
    const start = performance.now();
    try {
      await fetch('/api/health', { method: 'HEAD' });
      return performance.now() - start;
    } catch (error) {
      return 1000; // High latency on error
    }
  }

  private async measureRenderPerformance(): Promise<number> {
    // Measure frame render time
    return new Promise((resolve) => {
      requestAnimationFrame((timestamp) => {
        const start = performance.now();
        requestAnimationFrame(() => {
          resolve(performance.now() - start);
        });
      });
    });
  }

  private calculateErrorRate(): number {
    // Get error rate from autonomous dashboard
    const dashboard = getAutonomousDashboard();
    const status = dashboard.getStatus();
    return status.performance.errorRate;
  }

  private calculateCacheHitRate(): number {
    // Get cache hit rate from autonomous dashboard
    const dashboard = getAutonomousDashboard();
    const status = dashboard.getStatus();
    return status.performance.cacheHitRate;
  }

  private async measureResponseTime(): Promise<number> {
    const start = performance.now();
    try {
      await fetch('/api/ping', { method: 'GET' });
      return performance.now() - start;
    } catch (error) {
      return 500; // High response time on error
    }
  }

  private calculateSystemHealth(metrics: HealthMetric[]): SystemHealth {
    // Calculate overall health score
    const score = this.calculateHealthScore(metrics);
    
    // Determine overall status
    let overall: SystemHealth['overall'] = 'optimal';
    if (score < 30) {
      overall = 'critical';
    } else if (score < 60) {
      overall = 'degraded';
    }

    // Calculate performance metrics
    const performance = this.calculatePerformanceMetrics(metrics);

    return {
      overall,
      metrics,
      score,
      lastCheck: new Date(),
      uptime: this.calculateUptime(),
      errorRate: metrics.find(m => m.name === 'error_rate')?.value || 0,
      performance
    };
  }

  private calculateHealthScore(metrics: HealthMetric[]): number {
    let totalScore = 0;
    let metricCount = 0;

    for (const metric of metrics) {
      let score = 100;
      
      if (metric.status === 'critical') {
        score = 20;
      } else if (metric.status === 'warning') {
        score = 60;
      } else if (metric.status === 'unknown') {
        score = 50;
      }

      // Apply trend factor
      if (metric.trend === 'improving') {
        score += 10;
      } else if (metric.trend === 'degrading') {
        score -= 10;
      }

      totalScore += Math.max(0, Math.min(100, score));
      metricCount++;
    }

    return metricCount > 0 ? totalScore / metricCount : 100;
  }

  private calculatePerformanceMetrics(metrics: HealthMetric[]): PerformanceMetrics {
    const getMetricValue = (name: string) => {
      const metric = metrics.find(m => m.name === name);
      return metric?.value || 0;
    };

    return {
      cpuUsage: getMetricValue('cpu_usage'),
      memoryUsage: getMetricValue('memory_usage'),
      networkLatency: getMetricValue('network_latency'),
      renderTime: getMetricValue('render_time'),
      bundleSize: this.calculateBundleSize(),
      cacheHitRate: getMetricValue('cache_hit_rate'),
      errorRate: getMetricValue('error_rate'),
      responseTime: getMetricValue('response_time')
    };
  }

  private calculateBundleSize(): number {
    // Calculate JavaScript bundle size
    const scripts = document.querySelectorAll('script[src]');
    let totalSize = 0;
    
    scripts.forEach(script => {
      const src = script.getAttribute('src');
      if (src && src.includes('/_next/static/')) {
        totalSize += 100000; // Estimated size per bundle
      }
    });

    return totalSize / 1024; // Return in KB
  }

  private calculateUptime(): number {
    // Calculate uptime in seconds
    const dashboard = getAutonomousDashboard();
    const status = dashboard.getStatus();
    return status.uptime / 1000;
  }

  private storeMetrics(metrics: HealthMetric[]): void {
    for (const metric of metrics) {
      if (!this.healthMetrics.has(metric.name)) {
        this.healthMetrics.set(metric.name, []);
      }
      
      const history = this.healthMetrics.get(metric.name)!;
      history.push(metric);
      
      // Limit history size
      if (history.length > 100) {
        history.shift();
      }
    }

    // Save to state manager
    this.saveMonitoringState();
  }

  private async saveMonitoringState(): Promise<void> {
    try {
      const stateManager = getAutonomousStateManager();
      const metricsObject = Object.fromEntries(this.healthMetrics);
      stateManager.set('monitoring_history', metricsObject);
    } catch (error) {
      console.error('Failed to save monitoring state:', error);
    }
  }

  private async updateMonitoringState(health: SystemHealth): Promise<void> {
    // Disable state persistence to avoid localStorage quota errors
    try {
      // Keep state in memory only - no persistence
      console.debug('Health state updated in memory:', health.overall);
    } catch (error) {
      console.debug('State management disabled for performance');
    }
  }

  private detectAnomalies(metrics: HealthMetric[]): void {
    for (const metric of metrics) {
      if (this.isAnomalous(metric)) {
        const anomaly: Anomaly = {
          id: `anomaly_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          type: this.getAnomalyType(metric.name),
          severity: this.getAnomalySeverity(metric),
          description: this.createAnomalyDescription(metric),
          detectedAt: new Date(),
          resolved: false
        };

        this.anomalies.push(anomaly);
        this.emit('anomaly_detected', { anomaly });
      }
    }

    // Limit anomalies history
    if (this.anomalies.length > 100) {
      this.anomalies = this.anomalies.slice(-100);
    }
  }

  private isAnomalous(metric: HealthMetric): boolean {
    // Check if metric value is significantly different from historical average
    const history = this.healthMetrics.get(metric.name);
    if (!history || history.length < 10) {
      return false;
    }

    const recentValues = history.slice(-10).map(m => m.value);
    const average = recentValues.reduce((sum, val) => sum + val, 0) / recentValues.length;
    const stdDev = Math.sqrt(recentValues.reduce((sum, val) => sum + Math.pow(val - average, 2), 0) / recentValues.length);

    // Anomaly if value is more than 2 standard deviations from mean
    return Math.abs(metric.value - average) > 2 * stdDev;
  }

  private getAnomalyType(metricName: string): Anomaly['type'] {
    if (metricName.includes('cpu') || metricName.includes('memory')) {
      return 'resource';
    } else if (metricName.includes('network') || metricName.includes('response')) {
      return 'network';
    } else if (metricName.includes('error')) {
      return 'error';
    } else if (metricName.includes('performance') || metricName.includes('render')) {
      return 'performance';
    }
    return 'resource';
  }

  private getAnomalySeverity(metric: HealthMetric): Anomaly['severity'] {
    if (metric.status === 'critical') {
      return 'critical';
    } else if (metric.status === 'warning') {
      return 'medium';
    }
    return 'low';
  }

  private createAnomalyDescription(metric: HealthMetric): string {
    return `Anomalous ${metric.name} detected: ${metric.value}${metric.unit} (threshold: ${metric.threshold.warning}${metric.unit})`;
  }

  private checkForHealingOpportunities(): void {
    if (this.healingInProgress || !this.config.autoHealing) {
      return;
    }

    const health = this.getCurrentHealth();
    if (health.score < this.config.healingThreshold) {
      this.initiateHealing(health);
    }

    // Check for specific healing opportunities
    this.checkSpecificHealingOpportunities();
  }

  private getCurrentHealth(): SystemHealth {
    // Get current health from metrics
    const allMetrics: HealthMetric[] = [];
    Array.from(this.healthMetrics.values()).forEach(history => {
      if (history.length > 0) {
        allMetrics.push(history[history.length - 1]);
      }
    });

    return this.calculateSystemHealth(allMetrics);
  }

  private initiateHealing(health: SystemHealth): void {
    if (this.healingInProgress) {
      return;
    }

    const cooldownTime = Date.now() - this.lastHealingTime;
    if (cooldownTime < this.config.healingCooldown * 1000) {
      return;
    }

    this.healingInProgress = true;
    this.lastHealingTime = Date.now();

    console.log(`Initiating auto-healing (health score: ${health.score})`);
    this.emit('healing_initiated', { health });

    // Determine healing actions
    const actions = this.determineHealingActions(health);
    
    // Execute healing actions
    this.executeHealingActions(actions);
  }

  private determineHealingActions(health: SystemHealth): HealingAction[] {
    const actions: HealingAction[] = [];

    // High CPU usage
    if (health.performance.cpuUsage > 80) {
      actions.push(this.createHealingAction('reduce_complexity', 'high', 'Reducing UI complexity to lower CPU usage'));
    }

    // High memory usage
    if (health.performance.memoryUsage > 85) {
      actions.push(this.createHealingAction('optimize_memory', 'high', 'Optimizing memory usage'));
    }

    // High error rate
    if (health.performance.errorRate > 10) {
      actions.push(this.createHealingAction('enable_safe_mode', 'critical', 'Enabling safe mode due to high error rate'));
    }

    // Poor network performance
    if (health.performance.networkLatency > 800) {
      actions.push(this.createHealingAction('clear_cache', 'medium', 'Clearing cache to improve network performance'));
    }

    // Poor render performance
    if (health.performance.renderTime > 150) {
      actions.push(this.createHealingAction('restart', 'medium', 'Restarting components to improve render performance'));
    }

    // Limit concurrent actions
    return actions.slice(0, this.config.maxConcurrentHealingActions);
  }

  private createHealingAction(type: HealingAction['type'], severity: HealingAction['severity'], 
                              description: string): HealingAction {
    return {
      id: `healing_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      type,
      severity,
      description,
      executed: false,
      timestamp: new Date()
    };
  }

  private async executeHealingActions(actions: HealingAction[]): Promise<void> {
    for (const action of actions) {
      try {
        await this.executeHealingAction(action);
      } catch (error) {
        console.error(`Healing action ${action.type} failed:`, error);
        action.result = 'failed';
        action.error = error instanceof Error ? error.message : String(error);
      }
    }

    this.healingInProgress = false;
    this.emit('healing_completed', { actions });
  }

  private async executeHealingAction(action: HealingAction): Promise<void> {
    action.executed = true;
    action.result = 'success';

    switch (action.type) {
      case 'restart':
        await this.executeRestartAction();
        break;
      case 'clear_cache':
        await this.executeClearCacheAction();
        break;
      case 'reduce_complexity':
        await this.executeReduceComplexityAction();
        break;
      case 'enable_safe_mode':
        await this.executeEnableSafeModeAction();
        break;
      case 'optimize_memory':
        await this.executeOptimizeMemoryAction();
        break;
      default:
        console.warn(`Unknown healing action type: ${action.type}`);
    }

    this.healingActions.push(action);
    this.emit('healing_action_executed', { action });
  }

  private async executeRestartAction(): Promise<void> {
    console.log('Executing restart action');
    // Restart non-critical components
    this.emit('component_restart', { timestamp: new Date() });
  }

  private async executeClearCacheAction(): Promise<void> {
    console.log('Executing clear cache action');
    
    // Clear browser cache
    if ('caches' in window) {
      const cacheNames = await caches.keys();
      for (const cacheName of cacheNames) {
        await caches.delete(cacheName);
      }
    }

    // Clear localStorage cache (selective)
    const keysToKeep = ['user_preferences', 'auth_token'];
    const allKeys = Object.keys(localStorage);
    
    for (const key of allKeys) {
      if (!keysToKeep.includes(key) && key.includes('cache')) {
        localStorage.removeItem(key);
      }
    }

    this.emit('cache_cleared', { timestamp: new Date() });
  }

  private async executeReduceComplexityAction(): Promise<void> {
    console.log('Executing reduce complexity action');
    
    // Reduce UI complexity
    const dashboard = getAutonomousDashboard();
    dashboard.updateConfig({
      autonomousMode: 'conservative'
    });

    this.emit('complexity_reduced', { timestamp: new Date() });
  }

  private async executeEnableSafeModeAction(): Promise<void> {
    console.log('Executing enable safe mode action');
    
    // Enable safe mode
    const dashboard = getAutonomousDashboard();
    dashboard.updateConfig({
      autonomousMode: 'conservative',
      enableAIOptimization: false
    });

    this.emit('safe_mode_enabled', { timestamp: new Date() });
  }

  private async executeOptimizeMemoryAction(): Promise<void> {
    console.log('Executing optimize memory action');
    
    // Force garbage collection if available
    if ('gc' in window) {
      (window as any).gc();
    }

    // Clear large objects from state
    const stateManager = getAutonomousStateManager();
    const keys = stateManager.keys();
    
    for (const key of keys) {
      if (key.includes('temp') || key.includes('cache')) {
        stateManager.delete(key);
      }
    }

    this.emit('memory_optimized', { timestamp: new Date() });
  }

  private checkSpecificHealingOpportunities(): void {
    // Check for specific patterns that need healing
    const recentAnomalies = this.anomalies.filter(a => !a.resolved && 
      Date.now() - a.detectedAt.getTime() < 60000); // Last minute

    if (recentAnomalies.length > 5) {
      // Too many anomalies, enable safe mode
      const action = this.createHealingAction('enable_safe_mode', 'high', 
        'Too many anomalies detected, enabling safe mode');
      this.executeHealingAction(action);
    }
  }

  public getSystemHealth(): SystemHealth {
    return this.getCurrentHealth();
  }

  public getHealingActions(): HealingAction[] {
    return [...this.healingActions];
  }

  public getAnomalies(): Anomaly[] {
    return [...this.anomalies];
  }

  public resolveAnomaly(anomalyId: string): void {
    const anomaly = this.anomalies.find(a => a.id === anomalyId);
    if (anomaly) {
      anomaly.resolved = true;
      anomaly.resolvedAt = new Date();
      this.emit('anomaly_resolved', { anomaly });
    }
  }

  public forceHealthCheck(): Promise<SystemHealth> {
    return this.performHealthCheck();
  }

  public forceHealing(): void {
    const health = this.getCurrentHealth();
    this.initiateHealing(health);
  }

  public updateConfig(newConfig: Partial<MonitoringConfig>): void {
    this.config = { ...this.config, ...newConfig };
    
    // Restart monitoring if needed
    if (this.monitoringTimer) {
      clearInterval(this.monitoringTimer);
      if (this.isMonitoring) {
        this.startMonitoring();
      }
    }
    
    this.emit('config_updated', { config: this.config });
  }

  // Event system
  public on(event: string, callback: Function): void {
    if (!this.eventListeners.has(event)) {
      this.eventListeners.set(event, []);
    }
    this.eventListeners.get(event)!.push(callback);
  }

  public off(event: string, callback: Function): void {
    const listeners = this.eventListeners.get(event);
    if (listeners) {
      const index = listeners.indexOf(callback);
      if (index > -1) {
        listeners.splice(index, 1);
      }
    }
  }

  private emit(event: string, data: any): void {
    const listeners = this.eventListeners.get(event);
    if (listeners) {
      listeners.forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error(`Error in event listener for ${event}:`, error);
        }
      });
    }
  }

  public destroy(): void {
    // Clear timers
    if (this.monitoringTimer) clearInterval(this.monitoringTimer);
    if (this.healingTimer) clearInterval(this.healingTimer);
    
    // Save final state
    this.saveMonitoringState();
    
    // Clear event listeners
    this.eventListeners.clear();
    
    this.isMonitoring = false;
    console.log('Autonomous Monitoring destroyed');
  }
}

// Singleton instance
let autonomousMonitoring: AutonomousMonitoring | null = null;

export function getAutonomousMonitoring(config?: Partial<MonitoringConfig>): AutonomousMonitoring {
  if (!autonomousMonitoring) {
    autonomousMonitoring = new AutonomousMonitoring(config);
  }
  return autonomousMonitoring;
}

export default AutonomousMonitoring;
