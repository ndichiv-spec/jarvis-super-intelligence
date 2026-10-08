/**
 * Autonomous Security System
 * ==========================
 * Self-healing security and autonomous authentication system.
 * Provides automatic threat detection, prevention, and response capabilities.
 */

import { getAutonomousDashboard } from './autonomous-dashboard';
import { getAutonomousStateManager } from './autonomous-state-manager';

export interface SecurityConfig {
  enableAutonomousSecurity: boolean;
  threatDetection: boolean;
  autoResponse: boolean;
  encryptionEnabled: boolean;
  authenticationRequired: boolean;
  sessionTimeout: number; // minutes
  maxLoginAttempts: number;
  lockoutDuration: number; // minutes
  passwordPolicy: PasswordPolicy;
  twoFactorAuth: boolean;
  biometricAuth: boolean;
  rateLimiting: RateLimitConfig;
  auditLogging: boolean;
  securityScanning: boolean;
}

export interface PasswordPolicy {
  minLength: number;
  requireUppercase: boolean;
  requireLowercase: boolean;
  requireNumbers: boolean;
  requireSpecialChars: boolean;
  maxAge: number; // days
  preventReuse: number; // previous passwords
}

export interface RateLimitConfig {
  enabled: boolean;
  requestsPerMinute: number;
  requestsPerHour: number;
  requestsPerDay: number;
  burstLimit: number;
  penaltyDuration: number; // seconds
}

export interface SecurityThreat {
  id: string;
  type: 'brute_force' | 'injection' | 'xss' | 'csrf' | 'ddos' | 'malware' | 'phishing' | 'unauthorized_access';
  severity: 'low' | 'medium' | 'high' | 'critical';
  source: string;
  description: string;
  detectedAt: Date;
  resolved: boolean;
  resolvedAt?: Date;
  responseAction?: SecurityAction;
}

export interface SecurityAction {
  type: 'block_ip' | 'lock_account' | 'force_logout' | 'escalate_privileges' | 'notify_admin' | 'quarantine';
  description: string;
  executed: boolean;
  timestamp: Date;
  result?: 'success' | 'failed' | 'partial';
  details?: any;
}

export interface AuthenticationSession {
  id: string;
  userId: string;
  username: string;
  role: string;
  permissions: string[];
  createdAt: Date;
  lastActivity: Date;
  expiresAt: Date;
  ipAddress: string;
  userAgent: string;
  twoFactorVerified: boolean;
  securityLevel: 'low' | 'medium' | 'high' | 'maximum';
}

export interface SecurityMetrics {
  totalThreats: number;
  blockedThreats: number;
  activeSessions: number;
  failedLogins: number;
  successfulLogins: number;
  securityScore: number; // 0-100
  averageResponseTime: number;
  encryptionOverhead: number;
}

class AutonomousSecurity {
  private config: SecurityConfig;
  private threats: SecurityThreat[] = [];
  private sessions: Map<string, AuthenticationSession> = new Map();
  private blockedIPs: Set<string> = new Set();
  private rateLimitTracker: Map<string, RateLimitEntry[]> = new Map();
  private securityMetrics: SecurityMetrics;
  private eventListeners: Map<string, Function[]> = new Map();
  private securityTimer: NodeJS.Timeout | null = null;
  private encryptionKey: string | null = null;
  private isInitialized = false;

  constructor(config: Partial<SecurityConfig> = {}) {
    this.config = {
      enableAutonomousSecurity: true,
      threatDetection: true,
      autoResponse: true,
      encryptionEnabled: true,
      authenticationRequired: true,
      sessionTimeout: 60, // 1 hour
      maxLoginAttempts: 5,
      lockoutDuration: 30, // 30 minutes
      passwordPolicy: {
        minLength: 8,
        requireUppercase: true,
        requireLowercase: true,
        requireNumbers: true,
        requireSpecialChars: true,
        maxAge: 90, // 90 days
        preventReuse: 5
      },
      twoFactorAuth: true,
      biometricAuth: false,
      rateLimiting: {
        enabled: true,
        requestsPerMinute: 60,
        requestsPerHour: 1000,
        requestsPerDay: 10000,
        burstLimit: 10,
        penaltyDuration: 300 // 5 minutes
      },
      auditLogging: true,
      securityScanning: true,
      ...config
    };

    this.securityMetrics = {
      totalThreats: 0,
      blockedThreats: 0,
      activeSessions: 0,
      failedLogins: 0,
      successfulLogins: 0,
      securityScore: 100,
      averageResponseTime: 0,
      encryptionOverhead: 0
    };
  }

  async initialize(): Promise<void> {
    if (this.isInitialized) return;

    try {
      // Initialize encryption
      if (this.config.encryptionEnabled) {
        await this.initializeEncryption();
      }

      // Load security data
      await this.loadSecurityData();

      // Start security monitoring
      if (this.config.enableAutonomousSecurity) {
        this.startSecurityMonitoring();
      }

      // Initialize threat detection
      if (this.config.threatDetection) {
        this.initializeThreatDetection();
      }

      // Clean up expired sessions
      this.cleanupExpiredSessions();

      this.isInitialized = true;
      this.emit('initialized', { config: this.config });

      console.log('Autonomous Security initialized successfully');
    } catch (error) {
      console.error('Failed to initialize Autonomous Security:', error);
      this.emit('initialization_failed', { error });
      throw error;
    }
  }

  private async initializeEncryption(): Promise<void> {
    // Generate or retrieve encryption key
    const storedKey = localStorage.getItem('security_encryption_key');
    
    if (storedKey) {
      this.encryptionKey = storedKey;
    } else {
      const key = await this.generateEncryptionKey();
      this.encryptionKey = key;
      localStorage.setItem('security_encryption_key', key);
    }
  }

  private async generateEncryptionKey(): Promise<string> {
    const array = new Uint8Array(32);
    crypto.getRandomValues(array);
    return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
  }

  private async loadSecurityData(): Promise<void> {
    try {
      const stateManager = getAutonomousStateManager();
      
      // Load blocked IPs
      const blockedIPs = stateManager.get('blocked_ips');
      if (blockedIPs) {
        this.blockedIPs = new Set(blockedIPs);
      }

      // Load threats
      const threats = stateManager.get('security_threats');
      if (threats) {
        this.threats = threats;
      }

      // Load sessions
      const sessions = stateManager.get('auth_sessions');
      if (sessions) {
        this.sessions = new Map(Object.entries(sessions));
      }

      console.log('Security data loaded successfully');
    } catch (error) {
      console.error('Failed to load security data:', error);
    }
  }

  private startSecurityMonitoring(): void {
    this.securityTimer = setInterval(() => {
      this.performSecurityScan();
    }, 60000); // Every minute
  }

  private initializeThreatDetection(): void {
    // Set up global error handlers for threat detection
    window.addEventListener('error', this.handleSecurityError.bind(this));
    window.addEventListener('unhandledrejection', this.handleSecurityError.bind(this));

    // Monitor network requests for suspicious activity
    this.monitorNetworkRequests();
  }

  private handleSecurityError(event: ErrorEvent | PromiseRejectionEvent): void {
    const error = 'error' in event ? event.error : event.reason;
    
    // Analyze error for security threats
    const threat = this.analyzeErrorForThreats(error);
    
    if (threat) {
      this.handleThreat(threat);
    }
  }

  private analyzeErrorForThreats(error: any): SecurityThreat | null {
    const errorMessage = error?.message || String(error);
    
    // Check for common attack patterns
    if (errorMessage.includes('SQL') || errorMessage.includes('injection')) {
      return this.createThreat('injection', 'high', errorMessage);
    }
    
    if (errorMessage.includes('XSS') || errorMessage.includes('script')) {
      return this.createThreat('xss', 'medium', errorMessage);
    }
    
    if (errorMessage.includes('CSRF') || errorMessage.includes('forged')) {
      return this.createThreat('csrf', 'medium', errorMessage);
    }

    return null;
  }

  private createThreat(type: SecurityThreat['type'], severity: SecurityThreat['severity'], 
                        description: string): SecurityThreat {
    return {
      id: `threat_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      type,
      severity,
      source: this.getCurrentIP(),
      description,
      detectedAt: new Date(),
      resolved: false
    };
  }

  private monitorNetworkRequests(): void {
    // Override fetch to monitor requests
    const originalFetch = window.fetch;
    
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      const ip = this.getCurrentIP();
      
      // Check rate limiting.
      //
      // This limiter is keyed on the browser's own IP, so it counts *all* traffic the
      // app makes, including its own background polling. A single dashboard load
      // issues 80-130 API calls, which is well past requestsPerMinute (60), so the
      // limiter used to trip against first-party polling and then reject the user's
      // own actions (e.g. chat surfaced "Error: Rate limit exceeded" without ever
      // reaching the network).
      //
      // Client-side limiting of the app's own traffic provides no real protection --
      // whoever controls the client controls the limiter -- and the backend already
      // enforces server-side rate limiting. So only genuinely third-party origins are
      // counted here.
      if (this.config.rateLimiting.enabled && !this.isFirstPartyRequest(url) && !this.checkRateLimit(ip)) {
        throw new Error('Rate limit exceeded');
      }
      
      // Check if IP is blocked
      if (this.blockedIPs.has(ip)) {
        throw new Error('Access denied');
      }
      
      // Monitor for suspicious patterns
      const threat = this.analyzeRequestForThreats(url, init);
      if (threat) {
        this.handleThreat(threat);
      }
      
      try {
        const response = await originalFetch(input, init);
        return response;
      } catch (error) {
        this.handleSecurityError({ reason: error } as PromiseRejectionEvent);
        throw error;
      }
    };
  }

  private analyzeRequestForThreats(url: string, init?: RequestInit): SecurityThreat | null {
    // Check for suspicious URLs
    if (url.includes('..') || url.includes('%2e%2e')) {
      return this.createThreat('injection', 'medium', 'Path traversal attempt');
    }
    
    if (url.includes('<script>') || url.includes('javascript:')) {
      return this.createThreat('xss', 'high', 'XSS attempt in URL');
    }
    
    // Check for large payloads (potential DoS)
    if (init?.body && JSON.stringify(init.body).length > 1000000) { // 1MB
      return this.createThreat('ddos', 'medium', 'Large payload detected');
    }
    
    return null;
  }

  /**
   * True when the request targets the app itself (same origin) or a loopback
   * address, i.e. JARVIS's own API server. Such traffic is not third-party
   * and must not be counted against the client-side abuse limiter.
   */
  private isFirstPartyRequest(url: string): boolean {
    try {
      const parsed = new URL(url, window.location.origin);
      if (parsed.origin === window.location.origin) {
        return true;
      }
      const host = parsed.hostname.toLowerCase();
      return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]';
    } catch {
      return false;
    }
  }

  private checkRateLimit(ip: string): boolean {
    if (!this.rateLimitTracker.has(ip)) {
      this.rateLimitTracker.set(ip, []);
    }
    
    const entries = this.rateLimitTracker.get(ip)!;
    const now = Date.now();
    
    // Remove old entries
    const recentEntries = entries.filter(entry => now - entry.timestamp < 60000); // Last minute
    
    if (recentEntries.length >= this.config.rateLimiting.requestsPerMinute) {
      this.applyRateLimitPenalty(ip);
      return false;
    }
    
    // Add new entry
    recentEntries.push({ timestamp: now });
    this.rateLimitTracker.set(ip, recentEntries);
    
    return true;
  }

  private applyRateLimitPenalty(ip: string): void {
    // Block IP temporarily
    this.blockedIPs.add(ip);
    
    // Schedule unblock
    setTimeout(() => {
      this.blockedIPs.delete(ip);
    }, this.config.rateLimiting.penaltyDuration * 1000);
    
    this.emit('rate_limit_exceeded', { ip, timestamp: new Date() });
  }

  private getCurrentIP(): string {
    // In a real implementation, this would get the actual IP
    return 'client_ip';
  }

  private performSecurityScan(): void {
    // Scan for security issues
    this.scanForVulnerabilities();
    this.cleanupExpiredSessions();
    this.updateSecurityMetrics();
    
    this.emit('security_scan_completed', { 
      threats: this.threats.length,
      sessions: this.sessions.size,
      blockedIPs: this.blockedIPs.size
    });
  }

  private scanForVulnerabilities(): void {
    // Check for common vulnerabilities
    this.checkForXSSVulnerabilities();
    this.checkForCSRFVulnerabilities();
    this.checkForAuthenticationIssues();
  }

  private checkForXSSVulnerabilities(): void {
    // Scan DOM for potential XSS
    const scripts = document.querySelectorAll('script');
    scripts.forEach(script => {
      if (script.src && !script.src.startsWith(window.location.origin)) {
        const threat = this.createThreat('xss', 'medium', `External script detected: ${script.src}`);
        this.handleThreat(threat);
      }
    });
  }

  private checkForCSRFVulnerabilities(): void {
    // Check for missing CSRF tokens in forms
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
      const hasCSRFToken = form.querySelector('input[name*="csrf"], input[name*="token"]');
      if (!hasCSRFToken && form.action) {
        const threat = this.createThreat('csrf', 'low', 'Form without CSRF protection');
        this.handleThreat(threat);
      }
    });
  }

  private checkForAuthenticationIssues(): void {
    // Check for expired sessions
    const now = Date.now();
    for (const [sessionId, session] of this.sessions) {
      if (session.expiresAt.getTime() < now) {
        this.terminateSession(sessionId, 'Session expired');
      }
    }
  }

  private cleanupExpiredSessions(): void {
    const now = Date.now();
    const expiredSessions: string[] = [];
    
    for (const [sessionId, session] of this.sessions) {
      if (session.expiresAt.getTime() < now) {
        expiredSessions.push(sessionId);
      }
    }
    
    expiredSessions.forEach(sessionId => {
      this.sessions.delete(sessionId);
    });
    
    if (expiredSessions.length > 0) {
      this.saveSecurityData();
      this.emit('sessions_cleaned', { count: expiredSessions.length });
    }
  }

  private updateSecurityMetrics(): void {
    this.securityMetrics.activeSessions = this.sessions.size;
    this.securityMetrics.securityScore = this.calculateSecurityScore();
    
    // Save metrics
    this.saveSecurityData();
  }

  private calculateSecurityScore(): number {
    let score = 100;
    
    // Deduct points for active threats
    score -= this.threats.filter(t => !t.resolved).length * 5;
    
    // Deduct points for blocked IPs (indicates attacks)
    score -= this.blockedIPs.size * 2;
    
    // Add points for successful security measures
    if (this.config.encryptionEnabled) score += 5;
    if (this.config.twoFactorAuth) score += 5;
    if (this.config.threatDetection) score += 5;
    
    return Math.max(0, Math.min(100, score));
  }

  private handleThreat(threat: SecurityThreat): void {
    this.threats.push(threat);
    this.securityMetrics.totalThreats++;
    
    this.emit('threat_detected', { threat });
    
    if (this.config.autoResponse) {
      this.respondToThreat(threat);
    }
  }

  private respondToThreat(threat: SecurityThreat): void {
    let action: SecurityAction;
    
    switch (threat.type) {
      case 'brute_force':
        action = this.createSecurityAction('block_ip', 'Blocking IP due to brute force attempt');
        break;
      case 'injection':
        action = this.createSecurityAction('block_ip', 'Blocking IP due to injection attempt');
        break;
      case 'ddos':
        action = this.createSecurityAction('block_ip', 'Blocking IP due to DoS attempt');
        break;
      case 'unauthorized_access':
        action = this.createSecurityAction('force_logout', 'Forcing logout due to unauthorized access');
        break;
      default:
        action = this.createSecurityAction('notify_admin', 'Notifying admin of security threat');
    }
    
    this.executeSecurityAction(action, threat);
  }

  private createSecurityAction(type: SecurityAction['type'], description: string): SecurityAction {
    return {
      type,
      description,
      executed: false,
      timestamp: new Date()
    };
  }

  private async executeSecurityAction(action: SecurityAction, threat: SecurityThreat): Promise<void> {
    try {
      action.executed = true;
      
      switch (action.type) {
        case 'block_ip':
          await this.blockIP(threat.source);
          action.result = 'success';
          break;
        case 'force_logout':
          await this.forceLogoutByIP(threat.source);
          action.result = 'success';
          break;
        case 'notify_admin':
          this.notifyAdmin(threat);
          action.result = 'success';
          break;
        default:
          action.result = 'partial';
      }
      
      threat.responseAction = action;
      threat.resolved = true;
      threat.resolvedAt = new Date();
      
      this.securityMetrics.blockedThreats++;
      this.emit('threat_resolved', { threat, action });
    } catch (error) {
      action.result = 'failed';
      action.details = error instanceof Error ? error.message : String(error);
      this.emit('security_action_failed', { action, error });
    }
  }

  private async blockIP(ip: string): Promise<void> {
    this.blockedIPs.add(ip);
    this.saveSecurityData();
    this.emit('ip_blocked', { ip, timestamp: new Date() });
  }

  private async forceLogoutByIP(ip: string): Promise<void> {
    const sessionsToTerminate: string[] = [];
    
    for (const [sessionId, session] of this.sessions) {
      if (session.ipAddress === ip) {
        sessionsToTerminate.push(sessionId);
      }
    }
    
    sessionsToTerminate.forEach(sessionId => {
      this.terminateSession(sessionId, 'Security action: force logout');
    });
  }

  private notifyAdmin(threat: SecurityThreat): void {
    // In a real implementation, this would send notifications to administrators
    console.warn(`Security threat detected: ${threat.description}`, threat);
    this.emit('admin_notified', { threat });
  }

  // Authentication methods
  public async authenticate(username: string, password: string, 
                          twoFactorCode?: string): Promise<AuthenticationSession> {
    const ip = this.getCurrentIP();
    
    // Check if IP is blocked
    if (this.blockedIPs.has(ip)) {
      throw new Error('Access denied: IP blocked');
    }
    
    // Check rate limiting
    if (!this.checkRateLimit(ip)) {
      throw new Error('Too many authentication attempts');
    }
    
    try {
      // Validate credentials (in real implementation, this would check against database)
      const isValid = await this.validateCredentials(username, password);
      
      if (!isValid) {
        this.securityMetrics.failedLogins++;
        throw new Error('Invalid credentials');
      }
      
      // Check two-factor authentication if enabled
      if (this.config.twoFactorAuth && !this.verifyTwoFactorCode(username, twoFactorCode)) {
        throw new Error('Invalid two-factor code');
      }
      
      // Create session
      const session = this.createSession(username, ip);
      this.sessions.set(session.id, session);
      
      this.securityMetrics.successfulLogins++;
      this.saveSecurityData();
      
      this.emit('authentication_success', { session });
      return session;
    } catch (error) {
      this.emit('authentication_failed', { username, ip, error });
      throw error;
    }
  }

  private async validateCredentials(username: string, password: string): Promise<boolean> {
    // In a real implementation, this would check against a secure database
    // For demo purposes, we'll use a simple validation
    const storedPassword = localStorage.getItem(`user_${username}`);
    if (!storedPassword) {
      return false;
    }
    
    return password === storedPassword;
  }

  private verifyTwoFactorCode(username: string, code?: string): boolean {
    if (!code) return false;
    
    // In a real implementation, this would verify against a 2FA service
    const storedCode = localStorage.getItem(`2fa_${username}`);
    return code === storedCode;
  }

  private createSession(username: string, ip: string): AuthenticationSession {
    const sessionId = this.generateSessionId();
    const expiresAt = new Date(Date.now() + this.config.sessionTimeout * 60 * 1000);
    
    return {
      id: sessionId,
      userId: `user_${username}`,
      username,
      role: 'user',
      permissions: ['read', 'write'],
      createdAt: new Date(),
      lastActivity: new Date(),
      expiresAt,
      ipAddress: ip,
      userAgent: navigator.userAgent,
      twoFactorVerified: this.config.twoFactorAuth,
      securityLevel: this.calculateSecurityLevel()
    };
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 16)}`;
  }

  private calculateSecurityLevel(): AuthenticationSession['securityLevel'] {
    let level: AuthenticationSession['securityLevel'] = 'low';
    
    if (this.config.twoFactorAuth) level = 'medium';
    if (this.config.biometricAuth) level = 'high';
    if (this.config.encryptionEnabled && this.config.threatDetection) level = 'maximum';
    
    return level;
  }

  public validateSession(sessionId: string): AuthenticationSession | null {
    const session = this.sessions.get(sessionId);
    
    if (!session) {
      return null;
    }
    
    if (session.expiresAt < new Date()) {
      this.sessions.delete(sessionId);
      return null;
    }
    
    // Update last activity
    session.lastActivity = new Date();
    
    return session;
  }

  public terminateSession(sessionId: string, reason: string): void {
    const session = this.sessions.get(sessionId);
    if (session) {
      this.sessions.delete(sessionId);
      this.saveSecurityData();
      this.emit('session_terminated', { sessionId, reason, session });
    }
  }

  public async logout(sessionId: string): Promise<void> {
    this.terminateSession(sessionId, 'User logout');
  }

  // Encryption methods
  public encrypt(data: string): string {
    if (!this.config.encryptionEnabled || !this.encryptionKey) {
      return data;
    }
    
    // Simple encryption (in production, use proper encryption)
    const encrypted = btoa(data + this.encryptionKey);
    return `encrypted:${encrypted}`;
  }

  public decrypt(encryptedData: string): string {
    if (!this.config.encryptionEnabled || !this.encryptionKey) {
      return encryptedData;
    }
    
    if (typeof encryptedData !== 'string' || !encryptedData.startsWith('encrypted:')) {
      return encryptedData;
    }
    
    try {
      const encrypted = encryptedData.substring(10); // Remove 'encrypted:' prefix
      const decrypted = atob(encrypted);
      return decrypted.replace(this.encryptionKey, '');
    } catch (error) {
      console.error('Decryption failed:', error);
      return encryptedData;
    }
  }

  private saveSecurityData(): void {
    try {
      const stateManager = getAutonomousStateManager();
      
      stateManager.set('blocked_ips', Array.from(this.blockedIPs));
      stateManager.set('security_threats', this.threats);
      stateManager.set('auth_sessions', Object.fromEntries(this.sessions));
      stateManager.set('security_metrics', this.securityMetrics);
    } catch (error) {
      console.error('Failed to save security data:', error);
    }
  }

  // Public API methods
  public getSecurityMetrics(): SecurityMetrics {
    return { ...this.securityMetrics };
  }

  public getActiveThreats(): SecurityThreat[] {
    return this.threats.filter(threat => !threat.resolved);
  }

  public getActiveSessions(): AuthenticationSession[] {
    return Array.from(this.sessions.values())
      .filter(session => session.expiresAt > new Date());
  }

  public isIPBlocked(ip: string): boolean {
    return this.blockedIPs.has(ip);
  }

  public blockIPManually(ip: string, reason: string): void {
    const threat = this.createThreat('unauthorized_access', 'medium', `Manual block: ${reason}`);
    threat.source = ip;
    this.handleThreat(threat);
  }

  public unblockIP(ip: string): void {
    this.blockedIPs.delete(ip);
    this.saveSecurityData();
    this.emit('ip_unblocked', { ip, timestamp: new Date() });
  }

  public updateConfig(newConfig: Partial<SecurityConfig>): void {
    this.config = { ...this.config, ...newConfig };
    
    // Restart security monitoring if needed
    if (this.securityTimer) {
      clearInterval(this.securityTimer);
      if (this.config.enableAutonomousSecurity) {
        this.startSecurityMonitoring();
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
    // Clear timer
    if (this.securityTimer) clearInterval(this.securityTimer);
    
    // Save final state
    this.saveSecurityData();
    
    // Clear event listeners
    this.eventListeners.clear();
    
    // Clear data
    this.threats = [];
    this.sessions.clear();
    this.blockedIPs.clear();
    this.rateLimitTracker.clear();
    
    this.isInitialized = false;
    console.log('Autonomous Security destroyed');
  }
}

// Rate limit entry interface
interface RateLimitEntry {
  timestamp: number;
}

// Singleton instance
let autonomousSecurity: AutonomousSecurity | null = null;

export function getAutonomousSecurity(config?: Partial<SecurityConfig>): AutonomousSecurity {
  if (!autonomousSecurity) {
    autonomousSecurity = new AutonomousSecurity(config);
  }
  return autonomousSecurity;
}

export default AutonomousSecurity;
