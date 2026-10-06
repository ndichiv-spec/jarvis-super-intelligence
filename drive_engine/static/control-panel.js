
// JARVIS Control Panel JavaScript
class JarvisControlPanel {
    constructor() {
        this.ws = null;
        this.currentSection = 'dashboard';
        this.updateInterval = null;
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.connectWebSocket();
        this.showSection('dashboard');
        this.startAutoUpdate();
    }
    
    setupEventListeners() {
        // Navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const section = link.dataset.section;
                this.showSection(section);
            });
        });
        
        // Control buttons
        document.getElementById('refresh-btn')?.addEventListener('click', () => {
            this.refreshData();
        });
        
        // Component controls
        document.getElementById('load-all-components')?.addEventListener('click', () => {
            this.executeCommand('start');
        });
        
        document.getElementById('unload-all-components')?.addEventListener('click', () => {
            this.executeCommand('stop');
        });
        
        document.getElementById('refresh-components')?.addEventListener('click', () => {
            this.refreshComponents();
        });
        
        // AI controls
        document.getElementById('submit-ai-task')?.addEventListener('click', () => {
            this.submitAITask();
        });
        
        // Monitoring controls
        document.getElementById('start-monitoring')?.addEventListener('click', () => {
            this.executeMonitoringCommand('start');
        });
        
        document.getElementById('stop-monitoring')?.addEventListener('click', () => {
            this.executeMonitoringCommand('stop');
        });
        
        document.getElementById('clear-alerts')?.addEventListener('click', () => {
            this.clearAlerts();
        });
        
        // Testing controls
        document.getElementById('run-tests')?.addEventListener('click', () => {
            this.runTests();
        });
        
        // Deployment controls
        document.getElementById('deploy-service')?.addEventListener('click', () => {
            this.deployService();
        });
        
        // Performance controls
        document.getElementById('run-optimization')?.addEventListener('click', () => {
            this.runOptimization();
        });
        
        document.getElementById('clear-cache')?.addEventListener('click', () => {
            this.executePerformanceCommand('clear_cache');
        });
        
        document.getElementById('force-gc')?.addEventListener('click', () => {
            this.executePerformanceCommand('force_gc');
        });
        
        // Alert controls
        document.getElementById('acknowledge-all')?.addEventListener('click', () => {
            this.acknowledgeAllAlerts();
        });
        
        document.getElementById('resolve-all')?.addEventListener('click', () => {
            this.resolveAllAlerts();
        });
    }
    
    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.subscribeToUpdates();
        };
        
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleWebSocketMessage(data);
        };
        
        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            // Attempt to reconnect after 5 seconds
            setTimeout(() => this.connectWebSocket(), 5000);
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }
    
    subscribeToUpdates() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                type: 'subscribe',
                sections: ['dashboard', 'components', 'monitoring']
            }));
        }
    }
    
    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'dashboard_update':
                this.updateDashboard(data.data);
                break;
            case 'components_update':
                this.updateComponents(data.data);
                break;
            case 'monitoring_update':
                this.updateMonitoring(data.data);
                break;
            case 'alert':
                this.showAlert(data.alert);
                break;
            case 'pong':
                // Handle ping response
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }
    
    showSection(sectionName) {
        // Hide all sections
        document.querySelectorAll('.content-section').forEach(section => {
            section.classList.remove('active');
        });
        
        // Show selected section
        const targetSection = document.getElementById(sectionName);
        if (targetSection) {
            targetSection.classList.add('active');
        }
        
        // Update navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
            if (link.dataset.section === sectionName) {
                link.classList.add('active');
            }
        });
        
        this.currentSection = sectionName;
    }
    
    async refreshData() {
        try {
            const status = await this.fetchAPI('/api/status');
            this.updateDashboard(status);
            
            const components = await this.fetchAPI('/api/components');
            this.updateComponents(components);
            
            const metrics = await this.fetchAPI('/api/metrics');
            this.updateMetrics(metrics);
            
        } catch (error) {
            console.error('Error refreshing data:', error);
            this.showNotification('Error refreshing data', 'error');
        }
    }
    
    async fetchAPI(endpoint) {
        const response = await fetch(endpoint);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    }
    
    updateDashboard(data) {
        // Update system status
        const statusElement = document.getElementById('drive-engine-status');
        if (statusElement) {
            statusElement.textContent = data.status || 'Unknown';
            statusElement.className = `value status-${data.status}`;
        }
        
        // Update component counts
        const totalElement = document.getElementById('total-components');
        if (totalElement && data.components) {
            totalElement.textContent = data.components.total || 0;
        }
        
        const activeElement = document.getElementById('active-components');
        if (activeElement && data.components) {
            activeElement.textContent = data.components.active || 0;
        }
        
        // Update status indicator
        const statusText = document.getElementById('status-text');
        const statusIndicator = document.getElementById('status-indicator');
        if (statusText && statusIndicator) {
            statusText.textContent = data.status || 'Unknown';
            statusIndicator.className = `status-indicator status-${data.status}`;
        }
    }
    
    updateComponents(data) {
        const componentsList = document.getElementById('components-list');
        if (!componentsList) return;
        
        componentsList.innerHTML = '';
        
        Object.entries(data).forEach(([id, component]) => {
            const card = this.createComponentCard(id, component);
            componentsList.appendChild(card);
        });
    }
    
    createComponentCard(id, component) {
        const card = document.createElement('div');
        card.className = 'component-card fade-in';
        
        const statusClass = component.active ? 'active' : 'inactive';
        
        card.innerHTML = `
            <div class="component-header">
                <span class="component-name">${component.name}</span>
                <span class="component-status ${statusClass}">${component.active ? 'Active' : 'Inactive'}</span>
            </div>
            <div class="component-details">
                <p><strong>Type:</strong> ${component.component_type}</p>
                <p><strong>State:</strong> ${component.state}</p>
                <p><strong>Load Time:</strong> ${component.load_time?.toFixed(3) || 0}s</p>
            </div>
            <div class="component-actions">
                <button class="btn btn-primary btn-sm" onclick="controlPanel.startComponent('${id}')">
                    <i class="fas fa-play"></i> Start
                </button>
                <button class="btn btn-secondary btn-sm" onclick="controlPanel.stopComponent('${id}')">
                    <i class="fas fa-stop"></i> Stop
                </button>
                <button class="btn btn-info btn-sm" onclick="controlPanel.restartComponent('${id}')">
                    <i class="fas fa-redo"></i> Restart
                </button>
            </div>
        `;
        
        return card;
    }
    
    updateMetrics(data) {
        // Update performance metrics
        const cpuElement = document.getElementById('cpu-usage');
        if (cpuElement && data.cpu_usage) {
            cpuElement.textContent = `${data.cpu_usage.toFixed(1)}%`;
        }
        
        const memoryElement = document.getElementById('memory-usage');
        if (memoryElement && data.memory_usage) {
            memoryElement.textContent = `${data.memory_usage.toFixed(1)}%`;
        }
        
        const diskElement = document.getElementById('disk-usage');
        if (diskElement && data.disk_usage) {
            diskElement.textContent = `${data.disk_usage.toFixed(1)}%`;
        }
        
        const uptimeElement = document.getElementById('uptime');
        if (uptimeElement && data.uptime) {
            uptimeElement.textContent = this.formatDuration(data.uptime);
        }
        
        // Update performance chart
        this.updatePerformanceChart(data);
    }
    
    updatePerformanceChart(data) {
        const canvas = document.getElementById('performance-chart');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        // This would integrate with Chart.js
        // For now, just log the data
        console.log('Performance data for chart:', data);
    }
    
    updateMonitoring(data) {
        // Update real-time metrics
        const metricsElement = document.getElementById('real-time-metrics');
        if (metricsElement && data.system_metrics) {
            metricsElement.innerHTML = '';
            Object.entries(data.system_metrics).forEach(([name, value]) => {
                const metricItem = document.createElement('div');
                metricItem.className = 'metric-item';
                metricItem.innerHTML = `
                    <span class="metric-name">${name}</span>
                    <span class="metric-value">${value}</span>
                `;
                metricsElement.appendChild(metricItem);
            });
        }
        
        // Update alerts
        const alertsElement = document.getElementById('active-alerts');
        if (alertsElement && data.alerts) {
            alertsElement.innerHTML = '';
            data.alerts.forEach(alert => {
                const alertItem = this.createAlertItem(alert);
                alertsElement.appendChild(alertItem);
            });
        }
    }
    
    createAlertItem(alert) {
        const item = document.createElement('div');
        item.className = `alert-item ${alert.severity}`;
        
        item.innerHTML = `
            <div class="alert-header">
                <span class="alert-title">${alert.name}</span>
                <span class="alert-time">${new Date(alert.created_at).toLocaleTimeString()}</span>
            </div>
            <div class="alert-message">${alert.message}</div>
        `;
        
        return item;
    }
    
    async executeCommand(command, args = []) {
        try {
            const response = await this.fetchAPI('/api/control/' + command, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ args })
            });
            
            this.showNotification(response, 'success');
            this.refreshData();
            
        } catch (error) {
            console.error('Error executing command:', error);
            this.showNotification('Error executing command', 'error');
        }
    }
    
    async executeMonitoringCommand(action) {
        try {
            const response = await this.fetchAPI('/api/monitoring/control', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    action: action,
                    target: 'system',
                    parameters: {}
                })
            });
            
            this.showNotification(response.message || 'Command executed', 'success');
            
        } catch (error) {
            console.error('Error executing monitoring command:', error);
            this.showNotification('Error executing command', 'error');
        }
    }
    
    async executePerformanceCommand(action) {
        try {
            const response = await this.fetchAPI('/api/performance/optimize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    type: 'memory',
                    action: action
                })
            });
            
            this.showNotification(response.result?.message || 'Command executed', 'success');
            
        } catch (error) {
            console.error('Error executing performance command:', error);
            this.showNotification('Error executing command', 'error');
        }
    }
    
    async submitAITask() {
        const taskType = document.getElementById('ai-task-type')?.value;
        const priority = document.getElementById('ai-task-priority')?.value;
        
        if (!taskType) {
            this.showNotification('Please select a task type', 'warning');
            return;
        }
        
        try {
            const response = await this.fetchAPI('/api/ai/submit_task', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    task_type: taskType,
                    description: `AI task: ${taskType}`,
                    input_data: {},
                    required_capabilities: [taskType],
                    priority: parseInt(priority)
                })
            });
            
            this.showNotification(`Task submitted: ${response.task_id}`, 'success');
            
        } catch (error) {
            console.error('Error submitting AI task:', error);
            this.showNotification('Error submitting AI task', 'error');
        }
    }
    
    async runTests() {
        const testSuite = document.getElementById('test-suite')?.value;
        
        if (!testSuite) {
            this.showNotification('Please select a test suite', 'warning');
            return;
        }
        
        try {
            const response = await this.fetchAPI('/api/testing/run', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    suite_id: testSuite,
                    environment_id: 'development'
                })
            });
            
            this.showNotification('Tests started', 'success');
            this.updateTestResults(response.report);
            
        } catch (error) {
            console.error('Error running tests:', error);
            this.showNotification('Error running tests', 'error');
        }
    }
    
    updateTestResults(report) {
        const metricsElement = document.getElementById('test-metrics');
        if (metricsElement && report.summary) {
            metricsElement.innerHTML = `
                <div class="test-summary">
                    <p><strong>Total Tests:</strong> ${report.summary.total_tests}</p>
                    <p><strong>Passed:</strong> ${report.summary.passed_tests}</p>
                    <p><strong>Failed:</strong> ${report.summary.failed_tests}</p>
                    <p><strong>Pass Rate:</strong> ${report.summary.pass_rate.toFixed(1)}%</p>
                </div>
            `;
        }
    }
    
    async deployService() {
        const service = document.getElementById('service-select')?.value;
        const version = document.getElementById('deployment-version')?.value;
        const strategy = document.getElementById('deployment-strategy')?.value;
        
        if (!service || !version) {
            this.showNotification('Please fill in all deployment fields', 'warning');
            return;
        }
        
        try {
            const response = await this.fetchAPI('/api/deployment/deploy', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    service_id: service,
                    version: version,
                    environment: 'development',
                    strategy: strategy
                })
            });
            
            this.showNotification(`Deployment started: ${response.deployment_id}`, 'success');
            
        } catch (error) {
            console.error('Error deploying service:', error);
            this.showNotification('Error deploying service', 'error');
        }
    }
    
    async runOptimization() {
        try {
            const response = await this.fetchAPI('/api/performance/optimize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    type: 'memory',
                    action: 'garbage_collect'
                })
            });
            
            this.showNotification('Optimization completed', 'success');
            
        } catch (error) {
            console.error('Error running optimization:', error);
            this.showNotification('Error running optimization', 'error');
        }
    }
    
    startComponent(componentId) {
        this.executeCommand('start', [componentId]);
    }
    
    stopComponent(componentId) {
        this.executeCommand('stop', [componentId]);
    }
    
    restartComponent(componentId) {
        this.executeCommand('restart', [componentId]);
    }
    
    refreshComponents() {
        this.fetchAPI('/api/components')
            .then(data => this.updateComponents(data))
            .catch(error => {
                console.error('Error refreshing components:', error);
                this.showNotification('Error refreshing components', 'error');
            });
    }
    
    clearAlerts() {
        const alertsElement = document.getElementById('active-alerts');
        if (alertsElement) {
            alertsElement.innerHTML = '<p>No active alerts</p>';
        }
        this.showNotification('Alerts cleared', 'info');
    }
    
    acknowledgeAllAlerts() {
        this.showNotification('All alerts acknowledged', 'info');
    }
    
    resolveAllAlerts() {
        this.showNotification('All alerts resolved', 'success');
    }
    
    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <span class="notification-message">${message}</span>
            <button class="notification-close" onclick="this.parentElement.remove()">×</button>
        `;
        
        // Add to page
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }
    
    formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        if (hours > 0) {
            return `${hours}h ${minutes}m ${secs}s`;
        } else if (minutes > 0) {
            return `${minutes}m ${secs}s`;
        } else {
            return `${secs}s`;
        }
    }
    
    startAutoUpdate() {
        // Update data every 30 seconds
        this.updateInterval = setInterval(() => {
            this.refreshData();
        }, 30000);
    }
    
    stopAutoUpdate() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }
}

// Initialize control panel when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.controlPanel = new JarvisControlPanel();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.controlPanel) {
        window.controlPanel.stopAutoUpdate();
        if (window.controlPanel.ws) {
            window.controlPanel.ws.close();
        }
    }
});
        