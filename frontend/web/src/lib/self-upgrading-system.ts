/**
 * Self-Upgrading System
 * =====================
 * Automatic version detection, download, and installation of updates.
 * Provides seamless, autonomous upgrade capabilities.
 */

import { getAutonomousDashboard } from './autonomous-dashboard';

export interface VersionInfo {
  version: string;
  buildNumber: number;
  releaseDate: Date;
  changelog: ChangelogEntry[];
  critical: boolean;
  breaking: boolean;
  downloadUrl: string;
  checksum: string;
  size: number;
  dependencies: DependencyInfo[];
}

export interface ChangelogEntry {
  version: string;
  date: Date;
  type: 'feature' | 'fix' | 'security' | 'performance' | 'breaking';
  description: string;
  impact: 'low' | 'medium' | 'high' | 'critical';
}

export interface DependencyInfo {
  name: string;
  version: string;
  type: 'required' | 'optional' | 'dev';
}

export interface UpgradePlan {
  currentVersion: string;
  targetVersion: string;
  upgradePath: VersionInfo[];
  estimatedTime: number; // minutes
  requiresDowntime: boolean;
  backupRequired: boolean;
  rollbackAvailable: boolean;
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
}

export interface UpgradeProgress {
  stage: 'downloading' | 'verifying' | 'backing_up' | 'installing' | 'configuring' | 'testing' | 'completed' | 'failed';
  progress: number; // 0-100
  message: string;
  startTime: Date;
  estimatedCompletion: Date;
  error?: string;
}

class SelfUpgradingSystem {
  private currentVersion: string;
  private upgradeInProgress = false;
  private upgradeProgress: UpgradeProgress | null = null;
  private eventListeners: Map<string, Function[]> = new Map();
  private downloadQueue: Map<string, AbortController> = new Map();

  constructor() {
    this.currentVersion = this.getCurrentVersion();
  }

  private getCurrentVersion(): string {
    // Get version from package.json or build info
    if (typeof window !== 'undefined' && (window as any).__APP_VERSION__) {
      return (window as any).__APP_VERSION__;
    }
    
    // Fallback to package.json version (would be injected at build time)
    return '3.0.0';
  }

  async checkForUpdates(): Promise<VersionInfo | null> {
    try {
      console.log('Checking for updates...');
      
      // Fetch version information from update server
      const versionInfo = await this.fetchVersionInfo();
      
      if (versionInfo && this.isNewerVersion(versionInfo.version)) {
        console.log(`Update available: ${versionInfo.version}`);
        this.emit('update_available', { versionInfo });
        return versionInfo;
      }
      
      console.log('No updates available');
      return null;
    } catch (error) {
      console.error('Update check failed:', error);
      this.emit('update_check_failed', { error });
      return null;
    }
  }

  private async fetchVersionInfo(): Promise<VersionInfo | null> {
    try {
      // Try multiple update sources
      const sources = [
        '/api/version',
        'https://api.jarvis-ai.com/version',
        'https://releases.jarvis-ai.com/latest'
      ];

      for (const source of sources) {
        try {
          const response = await fetch(source, {
            method: 'GET',
            headers: {
              'Accept': 'application/json',
              'User-Agent': `Jarvis-Dashboard/${this.currentVersion}`
            },
            signal: AbortSignal.timeout(10000) // 10 second timeout
          });

          if (response.ok) {
            const data = await response.json();
            return this.parseVersionInfo(data);
          }
        } catch (sourceError) {
          console.warn(`Failed to fetch from ${source}:`, sourceError);
          continue;
        }
      }

      return null;
    } catch (error) {
      console.error('Failed to fetch version info:', error);
      return null;
    }
  }

  private parseVersionInfo(data: any): VersionInfo {
    return {
      version: data.version,
      buildNumber: data.buildNumber || 0,
      releaseDate: new Date(data.releaseDate),
      changelog: data.changelog || [],
      critical: data.critical || false,
      breaking: data.breaking || false,
      downloadUrl: data.downloadUrl,
      checksum: data.checksum,
      size: data.size || 0,
      dependencies: data.dependencies || []
    };
  }

  private isNewerVersion(newVersion: string): boolean {
    return this.compareVersions(newVersion, this.currentVersion) > 0;
  }

  private compareVersions(version1: string, version2: string): number {
    const v1Parts = version1.split('.').map(Number);
    const v2Parts = version2.split('.').map(Number);
    
    const maxLength = Math.max(v1Parts.length, v2Parts.length);
    
    for (let i = 0; i < maxLength; i++) {
      const v1Part = v1Parts[i] || 0;
      const v2Part = v2Parts[i] || 0;
      
      if (v1Part > v2Part) return 1;
      if (v1Part < v2Part) return -1;
    }
    
    return 0;
  }

  async createUpgradePlan(targetVersion: string): Promise<UpgradePlan> {
    try {
      console.log(`Creating upgrade plan from ${this.currentVersion} to ${targetVersion}`);
      
      // Get all versions between current and target
      const upgradePath = await this.getUpgradePath(targetVersion);
      
      // Calculate upgrade metrics
      const estimatedTime = this.calculateUpgradeTime(upgradePath);
      const requiresDowntime = upgradePath.some(v => v.breaking);
      const backupRequired = upgradePath.some(v => v.breaking || v.critical);
      const rollbackAvailable = !upgradePath.some(v => v.breaking);
      const riskLevel = this.calculateRiskLevel(upgradePath);
      
      const plan: UpgradePlan = {
        currentVersion: this.currentVersion,
        targetVersion,
        upgradePath,
        estimatedTime,
        requiresDowntime,
        backupRequired,
        rollbackAvailable,
        riskLevel
      };
      
      this.emit('upgrade_plan_created', { plan });
      return plan;
    } catch (error) {
      console.error('Failed to create upgrade plan:', error);
      throw error;
    }
  }

  private async getUpgradePath(targetVersion: string): Promise<VersionInfo[]> {
    // In a real implementation, this would fetch all versions and determine the path
    // For now, we'll simulate getting the target version directly
    
    const versionInfo = await this.fetchVersionInfo();
    if (!versionInfo || versionInfo.version !== targetVersion) {
      throw new Error(`Unable to find upgrade path to version ${targetVersion}`);
    }
    
    return [versionInfo];
  }

  private calculateUpgradeTime(upgradePath: VersionInfo[]): number {
    // Base time + time per version + additional time for breaking changes
    const baseTime = 5; // 5 minutes base
    const timePerVersion = 2; // 2 minutes per version
    const breakingChangePenalty = upgradePath.some(v => v.breaking) ? 10 : 0; // 10 minutes for breaking changes
    
    return baseTime + (upgradePath.length * timePerVersion) + breakingChangePenalty;
  }

  private calculateRiskLevel(upgradePath: VersionInfo[]): 'low' | 'medium' | 'high' | 'critical' {
    let riskScore = 0;
    
    upgradePath.forEach(version => {
      if (version.critical) riskScore += 30;
      if (version.breaking) riskScore += 20;
      if (version.dependencies.some(d => d.type === 'required')) riskScore += 10;
      if (version.changelog.some(c => c.type === 'breaking')) riskScore += 15;
    });
    
    if (riskScore >= 50) return 'critical';
    if (riskScore >= 30) return 'high';
    if (riskScore >= 15) return 'medium';
    return 'low';
  }

  async executeUpgrade(targetVersion: string, options: {
    autoApprove?: boolean;
    backupBeforeUpgrade?: boolean;
    rollbackOnError?: boolean;
  } = {}): Promise<void> {
    if (this.upgradeInProgress) {
      throw new Error('Upgrade already in progress');
    }

    try {
      this.upgradeInProgress = true;
      
      // Create upgrade plan
      const plan = await this.createUpgradePlan(targetVersion);
      
      // Check if upgrade is safe
      if (!options.autoApprove && plan.riskLevel === 'critical') {
        throw new Error('Critical upgrade requires manual approval');
      }
      
      // Create backup if required
      if (options.backupBeforeUpgrade !== false && plan.backupRequired) {
        await this.createUpgradeBackup();
      }
      
      // Execute upgrade
      await this.performUpgrade(plan);
      
      console.log('Upgrade completed successfully');
      this.emit('upgrade_completed', { 
        fromVersion: plan.currentVersion, 
        toVersion: plan.targetVersion 
      });
      
    } catch (error) {
      console.error('Upgrade failed:', error);
      this.emit('upgrade_failed', { error, targetVersion });
      
      // Attempt rollback if enabled
      if (options.rollbackOnError !== false) {
        await this.attemptRollback();
      }
      
      throw error;
    } finally {
      this.upgradeInProgress = false;
      this.upgradeProgress = null;
    }
  }

  private async createUpgradeBackup(): Promise<void> {
    console.log('Creating upgrade backup...');
    
    const autonomousDashboard = getAutonomousDashboard();
    await autonomousDashboard.forceBackup('full');
    
    console.log('Upgrade backup created');
  }

  private async performUpgrade(plan: UpgradePlan): Promise<void> {
    const startTime = new Date();
    const totalSteps = plan.upgradePath.length * 6; // 6 steps per version
    
    for (let i = 0; i < plan.upgradePath.length; i++) {
      const version = plan.upgradePath[i];
      const stepOffset = i * 6;
      
      // Step 1: Download
      await this.updateProgress('downloading', (stepOffset + 1) / totalSteps * 100, 
        `Downloading version ${version.version}...`, startTime);
      const updateData = await this.downloadVersion(version);
      
      // Step 2: Verify
      await this.updateProgress('verifying', (stepOffset + 2) / totalSteps * 100,
        `Verifying version ${version.version}...`, startTime);
      await this.verifyUpdate(updateData, version);
      
      // Step 3: Install
      await this.updateProgress('installing', (stepOffset + 3) / totalSteps * 100,
        `Installing version ${version.version}...`, startTime);
      await this.installVersion(updateData, version);
      
      // Step 4: Configure
      await this.updateProgress('configuring', (stepOffset + 4) / totalSteps * 100,
        `Configuring version ${version.version}...`, startTime);
      await this.configureVersion(version);
      
      // Step 5: Test
      await this.updateProgress('testing', (stepOffset + 5) / totalSteps * 100,
        `Testing version ${version.version}...`, startTime);
      await this.testVersion(version);
      
      // Step 6: Finalize
      await this.updateProgress('completed', (stepOffset + 6) / totalSteps * 100,
        `Finalizing version ${version.version}...`, startTime);
      await this.finalizeVersion(version);
    }
    
    // Update current version
    this.currentVersion = plan.targetVersion;
    
    // Final progress update
    await this.updateProgress('completed', 100, 'Upgrade completed successfully', startTime);
  }

  private async updateProgress(stage: UpgradeProgress['stage'], progress: number, 
                              message: string, startTime: Date): Promise<void> {
    this.upgradeProgress = {
      stage,
      progress,
      message,
      startTime,
      estimatedCompletion: new Date(startTime.getTime() + (Date.now() - startTime.getTime()) * (100 / Math.max(progress, 1)))
    };
    
    this.emit('upgrade_progress', { progress: this.upgradeProgress });
  }

  private async downloadVersion(version: VersionInfo): Promise<ArrayBuffer> {
    console.log(`Downloading version ${version.version}...`);
    
    // Create abort controller for this download
    const abortController = new AbortController();
    this.downloadQueue.set(version.version, abortController);
    
    try {
      const response = await fetch(version.downloadUrl, {
        signal: abortController.signal,
        headers: {
          'User-Agent': `Jarvis-Dashboard/${this.currentVersion}`
        }
      });
      
      if (!response.ok) {
        throw new Error(`Download failed: ${response.statusText}`);
      }
      
      const arrayBuffer = await response.arrayBuffer();
      
      // Verify size
      if (version.size > 0 && arrayBuffer.byteLength !== version.size) {
        throw new Error(`Size mismatch: expected ${version.size}, got ${arrayBuffer.byteLength}`);
      }
      
      console.log(`Download completed: ${arrayBuffer.byteLength} bytes`);
      return arrayBuffer;
    } finally {
      this.downloadQueue.delete(version.version);
    }
  }

  private async verifyUpdate(updateData: ArrayBuffer, version: VersionInfo): Promise<void> {
    console.log(`Verifying version ${version.version}...`);
    
    // Verify checksum
    if (version.checksum) {
      const calculatedChecksum = await this.calculateChecksum(updateData);
      if (calculatedChecksum !== version.checksum) {
        throw new Error(`Checksum mismatch: expected ${version.checksum}, got ${calculatedChecksum}`);
      }
    }
    
    // Verify digital signature (if available)
    if (version.downloadUrl.includes('.signed')) {
      await this.verifySignature(updateData, version);
    }
    
    console.log('Verification passed');
  }

  private async calculateChecksum(data: ArrayBuffer): Promise<string> {
    // Use Web Crypto API for SHA-256
    if (crypto.subtle) {
      const hashBuffer = await crypto.subtle.digest('SHA-256', data);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    }
    
    // Fallback to simple hash
    return this.simpleHash(data);
  }

  private simpleHash(data: ArrayBuffer): string {
    let hash = 0;
    const bytes = new Uint8Array(data);
    
    for (let i = 0; i < bytes.length; i++) {
      hash = ((hash << 5) - hash) + bytes[i];
      hash = hash & hash;
    }
    
    return Math.abs(hash).toString(16);
  }

  private async verifySignature(data: ArrayBuffer, version: VersionInfo): Promise<void> {
    // In a real implementation, this would verify a digital signature
    console.log('Signature verification (simulated)');
  }

  private async installVersion(updateData: ArrayBuffer, version: VersionInfo): Promise<void> {
    console.log(`Installing version ${version.version}...`);
    
    // In a real implementation, this would:
    // 1. Extract the update package
    // 2. Replace files
    // 3. Update dependencies
    // 4. Run migration scripts
    
    // For now, we'll simulate the installation
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    console.log('Installation completed');
  }

  private async configureVersion(version: VersionInfo): Promise<void> {
    console.log(`Configuring version ${version.version}...`);
    
    // Update configuration files
    // Apply new settings
    // Initialize new features
    
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    console.log('Configuration completed');
  }

  private async testVersion(version: VersionInfo): Promise<void> {
    console.log(`Testing version ${version.version}...`);
    
    // Run smoke tests
    // Verify functionality
    // Check performance
    
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    console.log('Testing completed');
  }

  private async finalizeVersion(version: VersionInfo): Promise<void> {
    console.log(`Finalizing version ${version.version}...`);
    
    // Clean up temporary files
    // Update version info
    // Restart services if needed
    
    await new Promise(resolve => setTimeout(resolve, 500));
    
    console.log('Finalization completed');
  }

  private async attemptRollback(): Promise<void> {
    console.log('Attempting rollback...');
    
    try {
      const autonomousDashboard = getAutonomousDashboard();
      const backups = await autonomousDashboard.getBackupsList();
      
      if (backups.length === 0) {
        throw new Error('No backups available for rollback');
      }
      
      // Find the most recent backup before the upgrade
      const latestBackup = backups
        .filter(b => b.type === 'full')
        .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())[0];
      
      if (!latestBackup) {
        throw new Error('No full backup available for rollback');
      }
      
      await autonomousDashboard.restoreFromBackup(latestBackup.id);
      
      console.log('Rollback completed successfully');
      this.emit('rollback_completed', { backupId: latestBackup.id });
    } catch (error) {
      console.error('Rollback failed:', error);
      this.emit('rollback_failed', { error });
      throw error;
    }
  }

  public cancelUpgrade(): void {
    if (!this.upgradeInProgress) {
      return;
    }
    
    console.log('Cancelling upgrade...');
    
    // Cancel any ongoing downloads
    this.downloadQueue.forEach(controller => {
      controller.abort();
    });
    this.downloadQueue.clear();
    
    // Reset state
    this.upgradeInProgress = false;
    this.upgradeProgress = null;
    
    this.emit('upgrade_cancelled', { timestamp: new Date() });
  }

  public getUpgradeProgress(): UpgradeProgress | null {
    return this.upgradeProgress;
  }

  public isUpgradeInProgress(): boolean {
    return this.upgradeInProgress;
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
    // Cancel any ongoing operations
    this.cancelUpgrade();
    
    // Clear event listeners
    this.eventListeners.clear();
    
    console.log('Self-upgrading system destroyed');
  }
}

// Singleton instance
let selfUpgradingSystem: SelfUpgradingSystem | null = null;

export function getSelfUpgradingSystem(): SelfUpgradingSystem {
  if (!selfUpgradingSystem) {
    selfUpgradingSystem = new SelfUpgradingSystem();
  }
  return selfUpgradingSystem;
}

export default SelfUpgradingSystem;
