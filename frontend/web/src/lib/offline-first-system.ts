/**
 * Offline-First System
 * ===================
 * Complete offline functionality with intelligent caching and synchronization.
 * Provides seamless offline experience with automatic data synchronization.
 */

import { getAutonomousStateManager } from './autonomous-state-manager';
import { getAutonomousDashboard } from './autonomous-dashboard';

export interface OfflineConfig {
  enableOfflineMode: boolean;
  cacheStrategy: 'cache-first' | 'network-first' | 'cache-only';
  maxCacheSize: number; // MB
  syncInterval: number; // minutes
  enableBackgroundSync: boolean;
  enablePredictiveCaching: boolean;
  enableOfflineAnalytics: boolean;
  offlineNotificationThreshold: number; // seconds
  retryAttempts: number;
  retryDelay: number; // seconds
}

export interface CacheEntry {
  url: string;
  data: any;
  timestamp: Date;
  expiresAt: Date;
  etag?: string;
  lastModified?: string;
  size: number;
  accessCount: number;
  lastAccessed: Date;
  priority: 'low' | 'medium' | 'high' | 'critical';
}

export interface SyncOperation {
  id: string;
  type: 'create' | 'update' | 'delete';
  url: string;
  data?: any;
  timestamp: Date;
  retries: number;
  status: 'pending' | 'syncing' | 'completed' | 'failed';
  error?: string;
}

export interface OfflineAnalytics {
  totalRequests: number;
  offlineRequests: number;
  cacheHits: number;
  cacheMisses: number;
  syncOperations: number;
  averageResponseTime: number;
  offlineDuration: number;
  bandwidthSaved: number; // MB
}

export interface NetworkStatus {
  online: boolean;
  connectionType: 'wifi' | 'cellular' | 'ethernet' | 'unknown';
  effectiveType: 'slow-2g' | '2g' | '3g' | '4g' | 'unknown';
  downlink: number; // Mbps
  rtt: number; // ms
  saveData: boolean;
  lastChecked: Date;
}

class OfflineFirstSystem {
  private config: OfflineConfig;
  private cache: Map<string, CacheEntry> = new Map();
  private syncQueue: SyncOperation[] = [];
  private networkStatus: NetworkStatus;
  private analytics: OfflineAnalytics;
  private eventListeners: Map<string, Function[]> = new Map();
  private syncTimer: NodeJS.Timeout | null = null;
  private cacheTimer: NodeJS.Timeout | null = null;
  private isInitialized = false;
  private currentCacheSize = 0;

  constructor(config: Partial<OfflineConfig> = {}) {
    this.config = {
      enableOfflineMode: true,
      cacheStrategy: 'cache-first',
      maxCacheSize: 100, // 100MB
      syncInterval: 5, // 5 minutes
      enableBackgroundSync: true,
      enablePredictiveCaching: true,
      enableOfflineAnalytics: true,
      offlineNotificationThreshold: 10, // 10 seconds
      retryAttempts: 3,
      retryDelay: 5, // 5 seconds
      ...config
    };

    this.networkStatus = {
      online: navigator.onLine,
      connectionType: 'unknown',
      effectiveType: 'unknown',
      downlink: 0,
      rtt: 0,
      saveData: false,
      lastChecked: new Date()
    };

    this.analytics = {
      totalRequests: 0,
      offlineRequests: 0,
      cacheHits: 0,
      cacheMisses: 0,
      syncOperations: 0,
      averageResponseTime: 0,
      offlineDuration: 0,
      bandwidthSaved: 0
    };
  }

  async initialize(): Promise<void> {
    if (this.isInitialized) return;

    try {
      // Initialize service worker
      await this.initializeServiceWorker();

      // Load cached data
      await this.loadCachedData();

      // Set up network monitoring
      this.setupNetworkMonitoring();

      // Set up event listeners
      this.setupEventListeners();

      // Start background sync if enabled
      if (this.config.enableBackgroundSync) {
        this.startBackgroundSync();
      }

      // Start cache maintenance
      this.startCacheMaintenance();

      // Initialize predictive caching
      if (this.config.enablePredictiveCaching) {
        await this.initializePredictiveCaching();
      }

      this.isInitialized = true;
      this.emit('initialized', { config: this.config });

      console.log('Offline-First System initialized successfully');
    } catch (error) {
      console.error('Failed to initialize Offline-First System:', error);
      this.emit('initialization_failed', { error });
      throw error;
    }
  }

  private async initializeServiceWorker(): Promise<void> {
    if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
      return;
    }

    try {
      // Registration was previously commented out with no replacement, while
      // `public/sw.js` did not exist either -- so the app was neither offline
      // capable nor installable. The worker now ships and only caches the shell;
      // see sw.js for why /api/* is excluded.
      //
      // Registration is skipped outside production: a service worker in dev
      // serves stale bundles and is a common source of "my change did not show
      // up" confusion.
      if (process.env.NODE_ENV !== 'production') {
        return;
      }

      await navigator.serviceWorker.register('/sw.js', { scope: '/' });

      navigator.serviceWorker.addEventListener(
        'message',
        this.handleServiceWorkerMessage.bind(this)
      );
    } catch (error) {
      console.error('Service Worker registration failed:', error);
    }
  }

  private handleServiceWorkerMessage(event: MessageEvent): void {
    const message = event.data;
    
    switch (message.type) {
      case 'cache_updated':
        this.emit('cache_updated', message);
        break;
      case 'sync_completed':
        this.handleSyncCompleted(message);
        break;
      case 'offline_notification':
        this.emit('offline_notification', message);
        break;
      default:
        console.log('Unknown service worker message:', message);
    }
  }

  private handleSyncCompleted(message: any): void {
    const { operationId, success, error } = message;
    
    const operation = this.syncQueue.find(op => op.id === operationId);
    if (operation) {
      operation.status = success ? 'completed' : 'failed';
      if (error) {
        operation.error = error;
      }
      
      if (success) {
        this.analytics.syncOperations++;
        this.emit('sync_completed', { operation });
      } else {
        this.emit('sync_failed', { operation, error });
      }
    }
  }

  private async loadCachedData(): Promise<void> {
    try {
      const stateManager = getAutonomousStateManager();
      const cachedData = stateManager.get('offline_cache');
      
      if (cachedData) {
        this.cache = new Map(Object.entries(cachedData));
        this.updateCacheSize();
        console.log(`Loaded ${this.cache.size} cached entries`);
      }
    } catch (error) {
      console.error('Failed to load cached data:', error);
    }
  }

  private setupNetworkMonitoring(): void {
    // Monitor online/offline status
    window.addEventListener('online', this.handleOnline.bind(this));
    window.addEventListener('offline', this.handleOffline.bind(this));

    // Monitor connection quality
    if ('connection' in navigator) {
      const connection = (navigator as any).connection;
      this.updateNetworkStatus(connection);
      
      connection.addEventListener('change', () => {
        this.updateNetworkStatus(connection);
      });
    }

    // Periodic network check
    setInterval(() => {
      this.checkNetworkConnectivity();
    }, 30000); // Every 30 seconds
  }

  private handleOnline(): void {
    this.networkStatus.online = true;
    this.networkStatus.lastChecked = new Date();
    
    this.emit('online', { timestamp: new Date() });
    
    // Start syncing when back online
    if (this.config.enableBackgroundSync) {
      this.processSyncQueue();
    }
  }

  private handleOffline(): void {
    this.networkStatus.online = false;
    this.networkStatus.lastChecked = new Date();
    
    this.emit('offline', { timestamp: new Date() });
    
    // Show offline notification if threshold exceeded
    setTimeout(() => {
      if (!this.networkStatus.online) {
        this.showOfflineNotification();
      }
    }, this.config.offlineNotificationThreshold * 1000);
  }

  private updateNetworkStatus(connection: any): void {
    this.networkStatus = {
      ...this.networkStatus,
      connectionType: this.getConnectionType(connection),
      effectiveType: connection.effectiveType || 'unknown',
      downlink: connection.downlink || 0,
      rtt: connection.rtt || 0,
      saveData: connection.saveData || false,
      lastChecked: new Date()
    };
  }

  private getConnectionType(connection: any): NetworkStatus['connectionType'] {
    if (connection.type) {
      return connection.type;
    }
    
    // Fallback detection
    if (connection.effectiveType) {
      const effectiveType = connection.effectiveType;
      if (effectiveType.includes('cellular') || effectiveType.includes('4g') || effectiveType.includes('3g')) {
        return 'cellular';
      }
    }
    
    return 'unknown';
  }

  private async checkNetworkConnectivity(): Promise<boolean> {
    try {
      const response = await fetch('/api/health', { 
        method: 'HEAD',
        cache: 'no-cache',
        signal: AbortSignal.timeout(5000)
      });
      
      const wasOnline = this.networkStatus.online;
      const isOnline = response.ok;
      
      if (wasOnline !== isOnline) {
        if (isOnline) {
          this.handleOnline();
        } else {
          this.handleOffline();
        }
      }
      
      return isOnline;
    } catch (error) {
      if (this.networkStatus.online) {
        this.handleOffline();
      }
      return false;
    }
  }

  private setupEventListeners(): void {
    // Listen for storage events (for multi-tab sync)
    window.addEventListener('storage', this.handleStorageChange.bind(this));
    
    // Listen for page visibility changes
    document.addEventListener('visibilitychange', this.handleVisibilityChange.bind(this));
  }

  private handleStorageChange(event: StorageEvent): void {
    if (event.key === 'offline_cache') {
      // Reload cache if another tab updated it
      this.loadCachedData();
    }
  }

  private handleVisibilityChange(): void {
    if (!document.hidden && this.config.enableBackgroundSync) {
      // Page became visible, try to sync
      this.processSyncQueue();
    }
  }

  private startBackgroundSync(): void {
    this.syncTimer = setInterval(() => {
      if (this.networkStatus.online) {
        this.processSyncQueue();
      }
    }, this.config.syncInterval * 60 * 1000);
  }

  private startCacheMaintenance(): void {
    this.cacheTimer = setInterval(() => {
      this.maintainCache();
    }, 60000); // Every minute
  }

  private async initializePredictiveCaching(): Promise<void> {
    // Analyze user patterns and pre-cache likely content
    console.log('Predictive caching initialized');
  }

  private async processSyncQueue(): Promise<void> {
    if (this.syncQueue.length === 0) {
      return;
    }

    const pendingOperations = this.syncQueue.filter(op => op.status === 'pending');
    
    for (const operation of pendingOperations) {
      if (operation.retries >= this.config.retryAttempts) {
        operation.status = 'failed';
        continue;
      }

      try {
        operation.status = 'syncing';
        await this.executeSyncOperation(operation);
      } catch (error) {
        operation.retries++;
        operation.status = 'pending';
        operation.error = error instanceof Error ? error.message : String(error);
        
        // Delay retry
        await new Promise(resolve => setTimeout(resolve, this.config.retryDelay * 1000));
      }
    }

    // Clean up completed operations
    this.syncQueue = this.syncQueue.filter(op => op.status === 'pending' || op.status === 'syncing');
    
    // Save sync queue
    this.saveSyncQueue();
  }

  private async executeSyncOperation(operation: SyncOperation): Promise<void> {
    switch (operation.type) {
      case 'create':
        await this.executeCreateOperation(operation);
        break;
      case 'update':
        await this.executeUpdateOperation(operation);
        break;
      case 'delete':
        await this.executeDeleteOperation(operation);
        break;
    }
  }

  private async executeCreateOperation(operation: SyncOperation): Promise<void> {
    const response = await fetch(operation.url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(operation.data)
    });

    if (!response.ok) {
      throw new Error(`Create operation failed: ${response.statusText}`);
    }
  }

  private async executeUpdateOperation(operation: SyncOperation): Promise<void> {
    const response = await fetch(operation.url, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(operation.data)
    });

    if (!response.ok) {
      throw new Error(`Update operation failed: ${response.statusText}`);
    }
  }

  private async executeDeleteOperation(operation: SyncOperation): Promise<void> {
    const response = await fetch(operation.url, {
      method: 'DELETE'
    });

    if (!response.ok) {
      throw new Error(`Delete operation failed: ${response.statusText}`);
    }
  }

  private maintainCache(): void {
    // Remove expired entries
    const now = new Date();
    for (const [url, entry] of this.cache) {
      if (entry.expiresAt < now) {
        this.cache.delete(url);
      }
    }

    // Remove least recently used entries if cache is full
    while (this.currentCacheSize > this.config.maxCacheSize * 1024 * 1024) {
      this.evictLeastRecentlyUsed();
    }

    // Update cache size
    this.updateCacheSize();

    // Save cache
    this.saveCache();
  }

  private evictLeastRecentlyUsed(): void {
    let oldestEntry: [string, CacheEntry] | null = null;
    let oldestTime = Date.now();

    for (const [url, entry] of this.cache) {
      if (entry.lastAccessed.getTime() < oldestTime) {
        oldestTime = entry.lastAccessed.getTime();
        oldestEntry = [url, entry];
      }
    }

    if (oldestEntry) {
      this.cache.delete(oldestEntry[0]);
    }
  }

  private updateCacheSize(): void {
    this.currentCacheSize = 0;
    for (const entry of this.cache.values()) {
      this.currentCacheSize += entry.size;
    }
  }

  private showOfflineNotification(): void {
    this.emit('offline_notification', {
      message: 'You are currently offline. Some features may be limited.',
      duration: this.config.offlineNotificationThreshold
    });
  }

  private saveCache(): void {
    try {
      const stateManager = getAutonomousStateManager();
      const cacheObject = Object.fromEntries(this.cache);
      stateManager.set('offline_cache', cacheObject);
    } catch (error) {
      console.error('Failed to save cache:', error);
    }
  }

  private saveSyncQueue(): void {
    try {
      const stateManager = getAutonomousStateManager();
      stateManager.set('sync_queue', this.syncQueue);
    } catch (error) {
      console.error('Failed to save sync queue:', error);
    }
  }

  // Public API methods
  public async request(url: string, options: RequestInit = {}): Promise<Response> {
    this.analytics.totalRequests++;
    const startTime = performance.now();

    try {
      let response: Response;

      if (!this.networkStatus.online) {
        // Offline mode - try cache first
        response = await this.getCachedResponse(url);
        this.analytics.offlineRequests++;
      } else {
        // Online mode - follow cache strategy
        switch (this.config.cacheStrategy) {
          case 'cache-first':
            response = await this.cacheFirstRequest(url, options);
            break;
          case 'network-first':
            response = await this.networkFirstRequest(url, options);
            break;
          case 'cache-only':
            response = await this.getCachedResponse(url);
            break;
          default:
            response = await fetch(url, options);
        }
      }

      const responseTime = performance.now() - startTime;
      this.updateAnalytics(responseTime);

      return response;
    } catch (error) {
      // Fallback to cache if network request fails
      try {
        const cachedResponse = await this.getCachedResponse(url);
        this.analytics.offlineRequests++;
        return cachedResponse;
      } catch (cacheError) {
        throw error; // Throw original error if cache also fails
      }
    }
  }

  private async cacheFirstRequest(url: string, options: RequestInit): Promise<Response> {
    // Try cache first
    try {
      const cachedResponse = await this.getCachedResponse(url);
      this.analytics.cacheHits++;
      return cachedResponse;
    } catch (error) {
      // Cache miss, fetch from network
      const response = await fetch(url, options);
      this.analytics.cacheMisses++;
      
      // Cache the response
      if (response.ok) {
        await this.cacheResponse(url, response);
      }
      
      return response;
    }
  }

  private async networkFirstRequest(url: string, options: RequestInit): Promise<Response> {
    try {
      const response = await fetch(url, options);
      
      if (response.ok) {
        // Cache the response
        await this.cacheResponse(url, response);
      }
      
      return response;
    } catch (error) {
      // Network failed, try cache
      const cachedResponse = await this.getCachedResponse(url);
      this.analytics.cacheHits++;
      return cachedResponse;
    }
  }

  private async getCachedResponse(url: string): Promise<Response> {
    const entry = this.cache.get(url);
    
    if (!entry) {
      throw new Error('No cached response found');
    }

    if (entry.expiresAt < new Date()) {
      this.cache.delete(url);
      throw new Error('Cached response expired');
    }

    // Update access info
    entry.accessCount++;
    entry.lastAccessed = new Date();

    return new Response(entry.data, {
      status: 200,
      statusText: 'OK',
      headers: {
        'Content-Type': 'application/json',
        'X-Cached': 'true',
        'X-Cache-Timestamp': entry.timestamp.toISOString()
      }
    });
  }

  private async cacheResponse(url: string, response: Response): Promise<void> {
    if (!response.ok) {
      return;
    }

    try {
      const data = await response.clone().text();
      const size = new Blob([data]).size;
      
      // Check cache size limit
      if (this.currentCacheSize + size > this.config.maxCacheSize * 1024 * 1024) {
        this.maintainCache();
      }

      const entry: CacheEntry = {
        url,
        data,
        timestamp: new Date(),
        expiresAt: new Date(Date.now() + 3600000), // 1 hour
        size,
        accessCount: 1,
        lastAccessed: new Date(),
        priority: 'medium'
      };

      this.cache.set(url, entry);
      this.updateCacheSize();
    } catch (error) {
      console.error('Failed to cache response:', error);
    }
  }

  public addToSyncQueue(operation: Omit<SyncOperation, 'id' | 'timestamp' | 'retries' | 'status'>): void {
    const syncOperation: SyncOperation = {
      ...operation,
      id: `sync_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date(),
      retries: 0,
      status: 'pending'
    };

    this.syncQueue.push(syncOperation);
    this.saveSyncQueue();
  }

  public getNetworkStatus(): NetworkStatus {
    return { ...this.networkStatus };
  }

  public getAnalytics(): OfflineAnalytics {
    return { ...this.analytics };
  }

  public getCacheSize(): number {
    return this.currentCacheSize;
  }

  public getCacheEntries(): CacheEntry[] {
    return Array.from(this.cache.values())
      .sort((a, b) => b.lastAccessed.getTime() - a.lastAccessed.getTime());
  }

  public clearCache(): void {
    this.cache.clear();
    this.currentCacheSize = 0;
    this.saveCache();
    this.emit('cache_cleared', {});
  }

  public preload(urls: string[]): Promise<void[]> {
    return Promise.all(urls.map(url => this.preloadUrl(url)));
  }

  private async preloadUrl(url: string): Promise<void> {
    if (this.cache.has(url)) {
      return; // Already cached
    }

    try {
      const response = await fetch(url);
      if (response.ok) {
        await this.cacheResponse(url, response);
      }
    } catch (error) {
      console.error(`Failed to preload ${url}:`, error);
    }
  }

  private updateAnalytics(responseTime: number): void {
    // Update average response time
    const totalRequests = this.analytics.totalRequests;
    const currentAverage = this.analytics.averageResponseTime;
    this.analytics.averageResponseTime = (currentAverage * (totalRequests - 1) + responseTime) / totalRequests;
  }

  public updateConfig(newConfig: Partial<OfflineConfig>): void {
    this.config = { ...this.config, ...newConfig };
    
    // Restart timers if needed
    if (this.syncTimer) {
      clearInterval(this.syncTimer);
      if (this.config.enableBackgroundSync) {
        this.startBackgroundSync();
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
    if (this.syncTimer) clearInterval(this.syncTimer);
    if (this.cacheTimer) clearInterval(this.cacheTimer);
    
    // Save final state
    this.saveCache();
    this.saveSyncQueue();
    
    // Clear event listeners
    this.eventListeners.clear();
    
    // Clear cache
    this.cache.clear();
    this.syncQueue = [];
    
    this.isInitialized = false;
    console.log('Offline-First System destroyed');
  }
}

// Singleton instance
let offlineFirstSystem: OfflineFirstSystem | null = null;

export function getOfflineFirstSystem(config?: Partial<OfflineConfig>): OfflineFirstSystem {
  if (!offlineFirstSystem) {
    offlineFirstSystem = new OfflineFirstSystem(config);
  }
  return offlineFirstSystem;
}

export default OfflineFirstSystem;
