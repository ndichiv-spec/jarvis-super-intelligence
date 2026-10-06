"""
JARVIS User Interface and Control Panel
====================================
Advanced user interface and control panel for the JARVIS drive engine
with comprehensive system control, monitoring, and management capabilities.

Features:
- Web-based control panel
- Real-time system dashboard
- Component management interface
- Performance monitoring dashboard
- AI capabilities control
- Testing interface
- Deployment management
- Configuration management
- Alert management
- User authentication
- Responsive design
- Interactive controls
- Real-time updates via WebSocket
- System status visualization
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid
from pathlib import Path
import weakref
from collections import defaultdict

# FastAPI for web interface
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import uvicorn

logger = logging.getLogger(__name__)


class PanelSection(Enum):
    """Panel section enumeration"""
    DASHBOARD = "dashboard"
    COMPONENTS = "components"
    AI_CAPABILITIES = "ai_capabilities"
    MONITORING = "monitoring"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    CONFIGURATION = "configuration"
    ALERTS = "alerts"
    LOGS = "logs"
    PERFORMANCE = "performance"


class ControlActionType(Enum):
    """Control action type enumeration"""
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    SCALE = "scale"
    DEPLOY = "deploy"
    TEST = "test"
    CONFIGURE = "configure"
    MONITOR = "monitor"
    OPTIMIZE = "optimize"


@dataclass
class PanelUser:
    """Panel user data structure"""
    id: str
    username: str
    email: str
    role: str = "user"
    permissions: List[str] = field(default_factory=list)
    last_login: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)


class ControlPanelAPI:
    """Control panel API endpoints"""
    
    def __init__(self, drive_engine):
        self.drive_engine = drive_engine
        self.app = FastAPI(title="JARVIS Control Panel", version="1.0.0")
        self.security = HTTPBearer()
        self.connected_websockets = set()
        
        # Setup routes
        self._setup_routes()
        
        # Setup static files and templates
        self._setup_static_files()
        
        # Mock users for demo
        self.users = {
            "admin": PanelUser(
                id="admin",
                username="admin",
                email="admin@jarvis.ai",
                role="admin",
                permissions=["*"]
            ),
            "user": PanelUser(
                id="user",
                username="user",
                email="user@jarvis.ai",
                role="user",
                permissions=["read", "monitor"]
            )
        }
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.app.get("/")
        async def dashboard(request: Request):
            """Main dashboard - Enhanced JARVIS Interface"""
            try:
                return self.templates.TemplateResponse("dashboard.html", {"request": request})
            except Exception as e:
                # Fallback to serving static HTML directly
                dashboard_path = Path("drive_engine/templates/dashboard.html")
                if dashboard_path.exists():
                    with open(dashboard_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    return HTMLResponse(content=content)
                # Fallback to basic dashboard
                basic_path = Path("drive_engine/templates/dashboard.html")
                if basic_path.exists():
                    with open(basic_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    return HTMLResponse(content=content)
                return HTMLResponse("<h1>JARVIS Dashboard</h1><p>Template error occurred</p>")
        
        @self.app.get("/api/status")
        async def get_system_status():
            """Get system status"""
            return self.drive_engine.get_status()
        
        @self.app.get("/api/components")
        async def get_components():
            """Get components"""
            return self.drive_engine.get_components()
        
        @self.app.get("/api/metrics")
        async def get_metrics():
            """Get performance metrics"""
            return self.drive_engine.get_metrics()
        
        @self.app.post("/api/control/{action}")
        async def execute_control(action: str, parameters: Dict[str, Any] = None):
            """Execute control command"""
            return await self.drive_engine.execute_command(action, parameters.get("args", []))
        
        @self.app.get("/api/ai/status")
        async def get_ai_status():
            """Get AI orchestrator status"""
            if hasattr(self.drive_engine, 'ai_orchestrator'):
                return self.drive_engine.ai_orchestrator.get_system_status()
            return {"error": "AI orchestrator not available"}
        
        @self.app.post("/api/ai/submit_task")
        async def submit_ai_task(task_data: Dict[str, Any]):
            """Submit AI task"""
            if hasattr(self.drive_engine, 'ai_orchestrator'):
                from drive_engine.ai_orchestrator import AITask, TaskPriority
                task = AITask(
                    task_type=task_data.get("task_type", "general"),
                    description=task_data.get("description", ""),
                    input_data=task_data.get("input_data", {}),
                    required_capabilities=task_data.get("required_capabilities", []),
                    priority=TaskPriority(task_data.get("priority", 2))
                )
                task_id = await self.drive_engine.ai_orchestrator.submit_task(task)
                return {"task_id": task_id, "status": "submitted"}
            return {"error": "AI orchestrator not available"}
        
        @self.app.get("/api/monitoring/dashboard")
        async def get_monitoring_dashboard():
            """Get monitoring dashboard data"""
            if hasattr(self.drive_engine, 'monitoring_interface'):
                return self.drive_engine.monitoring_interface.get_dashboard_data()
            return {"error": "Monitoring interface not available"}
        
        @self.app.post("/api/monitoring/control")
        async def execute_monitoring_control(action_data: Dict[str, Any]):
            """Execute monitoring control"""
            if hasattr(self.drive_engine, 'monitoring_interface'):
                from drive_engine.monitoring_interface import ControlAction
                action = ControlAction(action_data.get("action"))
                target = action_data.get("target", "")
                parameters = action_data.get("parameters", {})
                
                command_id = await self.drive_engine.monitoring_interface.execute_control_command(
                    action, target, parameters
                )
                return {"command_id": command_id, "status": "executed"}
            return {"error": "Monitoring interface not available"}
        
        @self.app.get("/api/testing/status")
        async def get_testing_status():
            """Get testing status"""
            if hasattr(self.drive_engine, 'testing_system'):
                return self.drive_engine.testing_system.get_test_metrics()
            return {"error": "Testing system not available"}
        
        @self.app.post("/api/testing/run")
        async def run_tests(test_config: Dict[str, Any]):
            """Run tests"""
            if hasattr(self.drive_engine, 'testing_system'):
                suite_id = test_config.get("suite_id")
                environment_id = test_config.get("environment_id")
                
                report = await self.drive_engine.testing_system.run_test_suite(suite_id, environment_id)
                return {"report": report}
            return {"error": "Testing system not available"}
        
        @self.app.get("/api/deployment/status")
        async def get_deployment_status():
            """Get deployment status"""
            if hasattr(self.drive_engine, 'deployment_manager'):
                return self.drive_engine.deployment_manager.get_system_status()
            return {"error": "Deployment manager not available"}
        
        @self.app.post("/api/deployment/deploy")
        async def deploy_service(deployment_config: Dict[str, Any]):
            """Deploy service"""
            if hasattr(self.drive_engine, 'deployment_manager'):
                from drive_engine.deployment_manager import DeploymentEnvironment, DeploymentStrategy
                
                service_id = deployment_config.get("service_id")
                version = deployment_config.get("version")
                environment = DeploymentEnvironment(deployment_config.get("environment", "development"))
                strategy = DeploymentStrategy(deployment_config.get("strategy", "rolling"))
                
                deployment_id = await self.drive_engine.deployment_manager.deploy_service(
                    service_id, version, environment, strategy
                )
                return {"deployment_id": deployment_id, "status": "started"}
            return {"error": "Deployment manager not available"}
        
        @self.app.post("/api/deployment/scale")
        async def scale_service(scale_config: Dict[str, Any]):
            """Scale service"""
            if hasattr(self.drive_engine, 'deployment_manager'):
                service_id = scale_config.get("service_id")
                target_replicas = scale_config.get("target_replicas")
                reason = scale_config.get("reason", "Manual scaling")
                
                scaling_event_id = await self.drive_engine.deployment_manager.scale_service(
                    service_id, target_replicas, reason
                )
                return {"scaling_event_id": scaling_event_id, "status": "scaling"}
            return {"error": "Deployment manager not available"}
        
        @self.app.get("/api/performance/status")
        async def get_performance_status():
            """Get performance optimization status"""
            if hasattr(self.drive_engine, 'performance_optimizer'):
                return self.drive_engine.performance_optimizer.get_performance_metrics()
            return {"error": "Performance optimizer not available"}
        
        @self.app.post("/api/performance/optimize")
        async def optimize_performance(optimization_config: Dict[str, Any]):
            """Perform performance optimization"""
            if hasattr(self.drive_engine, 'performance_optimizer'):
                from drive_engine.performance_optimizer import OptimizationType
                
                optimization_type = OptimizationType(optimization_config.get("type", "memory"))
                action = optimization_config.get("action", "garbage_collect")
                
                result = await self.drive_engine.performance_optimizer.manual_optimization(
                    optimization_type, action
                )
                return {"result": result}
            return {"error": "Performance optimizer not available"}
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates"""
            await websocket.accept()
            self.connected_websockets.add(websocket)
            
            try:
                while True:
                    # Receive client message
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    
                    # Handle different message types
                    if message.get("type") == "subscribe":
                        # Subscribe to updates
                        await self._handle_subscription(websocket, message.get("sections", []))
                    elif message.get("type") == "ping":
                        # Handle ping
                        await websocket.send_text(json.dumps({"type": "pong"}))
                    elif message.get("type") == "get_status":
                        # Send current status
                        status = self.drive_engine.get_status()
                        await websocket.send_text(json.dumps({
                            "type": "status_update",
                            "data": status
                        }))
                    
            except WebSocketDisconnect:
                self.connected_websockets.discard(websocket)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self.connected_websockets.discard(websocket)
    
    def _setup_static_files(self):
        """Setup static files and templates"""
        # Create static directory if it doesn't exist
        static_dir = Path("drive_engine/static")
        static_dir.mkdir(parents=True, exist_ok=True)
        
        # Create templates directory if it doesn't exist
        templates_dir = Path("drive_engine/templates")
        templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Mount static files
        self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        
        # Setup templates
        self.templates = Jinja2Templates(directory=str(templates_dir))
    
    async def _handle_subscription(self, websocket: WebSocket, sections: List[str]):
        """Handle WebSocket subscription"""
        # Send initial data for subscribed sections
        for section in sections:
            if section == "dashboard":
                status = self.drive_engine.get_status()
                await websocket.send_text(json.dumps({
                    "type": "dashboard_update",
                    "section": section,
                    "data": status
                }))
            elif section == "components":
                components = self.drive_engine.get_components()
                await websocket.send_text(json.dumps({
                    "type": "components_update",
                    "section": section,
                    "data": components
                }))
            elif section == "monitoring":
                if hasattr(self.drive_engine, 'monitoring_interface'):
                    monitoring_data = self.drive_engine.monitoring_interface.get_dashboard_data()
                    await websocket.send_text(json.dumps({
                        "type": "monitoring_update",
                        "section": section,
                        "data": monitoring_data
                    }))
    
    async def broadcast_update(self, update_type: str, data: Dict[str, Any]):
        """Broadcast update to all connected WebSockets"""
        if not self.connected_websockets:
            return
        
        message = json.dumps({
            "type": update_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        })
        
        disconnected = set()
        
        for websocket in self.connected_websockets:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Failed to send WebSocket update: {e}")
                disconnected.add(websocket)
        
        # Remove disconnected connections
        self.connected_websockets -= disconnected


class ControlPanelUI:
    """Control Panel UI Generator"""
    
    def __init__(self):
        self.static_dir = Path("drive_engine/static")
        self.templates_dir = Path("drive_engine/templates")
        
        # Ensure directories exist
        self.static_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate UI files
        self._generate_html_templates()
        self._generate_css_styles()
        self._generate_javascript()
    
    def _generate_html_templates(self):
        """Generate HTML templates"""
        
        # Main dashboard template
        dashboard_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JARVIS Control Panel</title>
    <link rel="stylesheet" href="/static/styles.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1><i class="fas fa-robot"></i> JARVIS Control Panel</h1>
            <div class="header-controls">
                <button id="refresh-btn" class="btn btn-primary">
                    <i class="fas fa-sync-alt"></i> Refresh
                </button>
                <span id="status-indicator" class="status-indicator">
                    <i class="fas fa-circle"></i> <span id="status-text">Loading...</span>
                </span>
            </div>
        </header>
        
        <nav class="sidebar">
            <ul class="nav-menu">
                <li><a href="#dashboard" class="nav-link active" data-section="dashboard">
                    <i class="fas fa-tachometer-alt"></i> Dashboard
                </a></li>
                <li><a href="#components" class="nav-link" data-section="components">
                    <i class="fas fa-cogs"></i> Components
                </a></li>
                <li><a href="#ai" class="nav-link" data-section="ai">
                    <i class="fas fa-brain"></i> AI Capabilities
                </a></li>
                <li><a href="#monitoring" class="nav-link" data-section="monitoring">
                    <i class="fas fa-chart-line"></i> Monitoring
                </a></li>
                <li><a href="#testing" class="nav-link" data-section="testing">
                    <i class="fas fa-vial"></i> Testing
                </a></li>
                <li><a href="#deployment" class="nav-link" data-section="deployment">
                    <i class="fas fa-rocket"></i> Deployment
                </a></li>
                <li><a href="#performance" class="nav-link" data-section="performance">
                    <i class="fas fa-tachometer-alt"></i> Performance
                </a></li>
                <li><a href="#alerts" class="nav-link" data-section="alerts">
                    <i class="fas fa-exclamation-triangle"></i> Alerts
                </a></li>
            </ul>
        </nav>
        
        <main class="main-content">
            <section id="dashboard" class="content-section active">
                <h2>System Dashboard</h2>
                <div class="dashboard-grid">
                    <div class="card">
                        <h3>System Status</h3>
                        <div id="system-status" class="status-content">
                            <div class="status-item">
                                <span class="label">Status:</span>
                                <span id="drive-engine-status" class="value">Loading...</span>
                            </div>
                            <div class="status-item">
                                <span class="label">Components:</span>
                                <span id="total-components" class="value">0</span>
                            </div>
                            <div class="status-item">
                                <span class="label">Active:</span>
                                <span id="active-components" class="value">0</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h3>Performance Metrics</h3>
                        <div class="metrics-grid">
                            <div class="metric">
                                <span class="metric-label">CPU Usage</span>
                                <span id="cpu-usage" class="metric-value">0%</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Memory Usage</span>
                                <span id="memory-usage" class="metric-value">0%</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Disk Usage</span>
                                <span id="disk-usage" class="metric-value">0%</span>
                            </div>
                            <div class="metric">
                                <span class="metric-label">Uptime</span>
                                <span id="uptime" class="metric-value">0s</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card full-width">
                        <h3>System Performance Chart</h3>
                        <canvas id="performance-chart" width="400" height="200"></canvas>
                    </div>
                </div>
            </section>
            
            <section id="components" class="content-section">
                <h2>Component Management</h2>
                <div class="component-controls">
                    <button id="load-all-components" class="btn btn-primary">
                        <i class="fas fa-play"></i> Load All
                    </button>
                    <button id="unload-all-components" class="btn btn-secondary">
                        <i class="fas fa-stop"></i> Unload All
                    </button>
                    <button id="refresh-components" class="btn btn-info">
                        <i class="fas fa-sync-alt"></i> Refresh
                    </button>
                </div>
                <div id="components-list" class="components-grid">
                    <!-- Components will be loaded here -->
                </div>
            </section>
            
            <section id="ai" class="content-section">
                <h2>AI Capabilities</h2>
                <div class="ai-controls">
                    <div class="control-group">
                        <label for="ai-task-type">Task Type:</label>
                        <select id="ai-task-type">
                            <option value="text_processing">Text Processing</option>
                            <option value="image_processing">Image Processing</option>
                            <option value="reasoning">Reasoning</option>
                            <option value="learning">Learning</option>
                        </select>
                    </div>
                    <div class="control-group">
                        <label for="ai-task-priority">Priority:</label>
                        <select id="ai-task-priority">
                            <option value="1">Low</option>
                            <option value="2">Normal</option>
                            <option value="3">High</option>
                            <option value="4">Urgent</option>
                        </select>
                    </div>
                    <button id="submit-ai-task" class="btn btn-primary">
                        <i class="fas fa-paper-plane"></i> Submit Task
                    </button>
                </div>
                <div id="ai-status" class="ai-status-panel">
                    <h3>AI System Status</h3>
                    <div id="ai-metrics" class="metrics-grid">
                        <!-- AI metrics will be loaded here -->
                    </div>
                </div>
            </section>
            
            <section id="monitoring" class="content-section">
                <h2>System Monitoring</h2>
                <div class="monitoring-controls">
                    <button id="start-monitoring" class="btn btn-success">
                        <i class="fas fa-play"></i> Start Monitoring
                    </button>
                    <button id="stop-monitoring" class="btn btn-danger">
                        <i class="fas fa-stop"></i> Stop Monitoring
                    </button>
                    <button id="clear-alerts" class="btn btn-warning">
                        <i class="fas fa-trash"></i> Clear Alerts
                    </button>
                </div>
                <div id="monitoring-dashboard" class="monitoring-grid">
                    <div class="card">
                        <h3>Real-time Metrics</h3>
                        <div id="real-time-metrics" class="metrics-list">
                            <!-- Real-time metrics will be loaded here -->
                        </div>
                    </div>
                    <div class="card">
                        <h3>Active Alerts</h3>
                        <div id="active-alerts" class="alerts-list">
                            <!-- Alerts will be loaded here -->
                        </div>
                    </div>
                </div>
            </section>
            
            <section id="testing" class="content-section">
                <h2>Testing & Validation</h2>
                <div class="testing-controls">
                    <div class="control-group">
                        <label for="test-suite">Test Suite:</label>
                        <select id="test-suite">
                            <option value="unit">Unit Tests</option>
                            <option value="integration">Integration Tests</option>
                            <option value="performance">Performance Tests</option>
                            <option value="security">Security Tests</option>
                        </select>
                    </div>
                    <button id="run-tests" class="btn btn-primary">
                        <i class="fas fa-play"></i> Run Tests
                    </button>
                    <button id="stop-tests" class="btn btn-danger">
                        <i class="fas fa-stop"></i> Stop Tests
                    </button>
                </div>
                <div id="test-results" class="test-results-panel">
                    <h3>Test Results</h3>
                    <div id="test-metrics" class="test-metrics">
                        <!-- Test metrics will be loaded here -->
                    </div>
                    <div id="test-details" class="test-details">
                        <!-- Test details will be loaded here -->
                    </div>
                </div>
            </section>
            
            <section id="deployment" class="content-section">
                <h2>Deployment Management</h2>
                <div class="deployment-controls">
                    <div class="control-group">
                        <label for="service-select">Service:</label>
                        <select id="service-select">
                            <option value="jarvis-api">JARVIS API</option>
                            <option value="jarvis-dashboard">JARVIS Dashboard</option>
                            <option value="jarvis-ai">JARVIS AI Orchestrator</option>
                        </select>
                    </div>
                    <div class="control-group">
                        <label for="deployment-version">Version:</label>
                        <input type="text" id="deployment-version" placeholder="1.0.0">
                    </div>
                    <div class="control-group">
                        <label for="deployment-strategy">Strategy:</label>
                        <select id="deployment-strategy">
                            <option value="rolling">Rolling</option>
                            <option value="blue_green">Blue-Green</option>
                            <option value="canary">Canary</option>
                        </select>
                    </div>
                    <button id="deploy-service" class="btn btn-primary">
                        <i class="fas fa-rocket"></i> Deploy
                    </button>
                </div>
                <div id="deployment-status" class="deployment-panel">
                    <h3>Deployment Status</h3>
                    <div id="deployment-info" class="deployment-info">
                        <!-- Deployment info will be loaded here -->
                    </div>
                </div>
            </section>
            
            <section id="performance" class="content-section">
                <h2>Performance Optimization</h2>
                <div class="performance-controls">
                    <button id="run-optimization" class="btn btn-primary">
                        <i class="fas fa-magic"></i> Run Optimization
                    </button>
                    <button id="clear-cache" class="btn btn-secondary">
                        <i class="fas fa-broom"></i> Clear Cache
                    </button>
                    <button id="force-gc" class="btn btn-info">
                        <i class="fas fa-recycle"></i> Force GC
                    </button>
                </div>
                <div id="performance-metrics" class="performance-panel">
                    <h3>Performance Metrics</h3>
                    <div id="performance-charts" class="charts-grid">
                        <!-- Performance charts will be loaded here -->
                    </div>
                </div>
            </section>
            
            <section id="alerts" class="content-section">
                <h2>Alert Management</h2>
                <div class="alerts-controls">
                    <button id="acknowledge-all" class="btn btn-warning">
                        <i class="fas fa-check"></i> Acknowledge All
                    </button>
                    <button id="resolve-all" class="btn btn-success">
                        <i class="fas fa-check-circle"></i> Resolve All
                    </button>
                </div>
                <div id="alerts-list" class="alerts-panel">
                    <h3>Active Alerts</h3>
                    <div id="alerts-content" class="alerts-content">
                        <!-- Alerts will be loaded here -->
                    </div>
                </div>
            </section>
        </main>
    </div>
    
    <script src="/static/control-panel.js"></script>
</body>
</html>
        """
        
        # Write dashboard template
        with open(self.templates_dir / "dashboard.html", "w") as f:
            f.write(dashboard_html)
    
    def _generate_css_styles(self):
        """Generate CSS styles"""
        css_content = """
/* JARVIS Control Panel Styles */
:root {
    --primary-color: #2563eb;
    --secondary-color: #64748b;
    --success-color: #10b981;
    --warning-color: #f59e0b;
    --danger-color: #ef4444;
    --info-color: #3b82f6;
    --dark-color: #1f2937;
    --light-color: #f3f4f6;
    --border-color: #e5e7eb;
    --shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    --shadow-lg: 0 10px 25px rgba(0, 0, 0, 0.1);
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background-color: var(--light-color);
    color: var(--dark-color);
    line-height: 1.6;
}

.container {
    display: flex;
    min-height: 100vh;
}

.header {
    background: linear-gradient(135deg, var(--primary-color), #1e40af);
    color: white;
    padding: 1rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: var(--shadow);
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1000;
}

.header h1 {
    font-size: 1.5rem;
    font-weight: 600;
}

.header-controls {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.status-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 20px;
    font-size: 0.875rem;
}

.sidebar {
    width: 250px;
    background: white;
    border-right: 1px solid var(--border-color);
    padding-top: 80px;
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    overflow-y: auto;
    box-shadow: var(--shadow);
}

.nav-menu {
    list-style: none;
    padding: 1rem 0;
}

.nav-menu li {
    margin-bottom: 0.25rem;
}

.nav-link {
    display: flex;
    align-items: center;
    padding: 0.75rem 1.5rem;
    color: var(--dark-color);
    text-decoration: none;
    transition: all 0.3s ease;
    border-left: 3px solid transparent;
}

.nav-link:hover {
    background: var(--light-color);
    color: var(--primary-color);
}

.nav-link.active {
    background: var(--light-color);
    color: var(--primary-color);
    border-left-color: var(--primary-color);
}

.nav-link i {
    width: 20px;
    margin-right: 0.75rem;
}

.main-content {
    flex: 1;
    margin-left: 250px;
    padding-top: 80px;
    padding: 2rem;
}

.content-section {
    display: none;
}

.content-section.active {
    display: block;
}

.content-section h2 {
    font-size: 1.75rem;
    font-weight: 600;
    margin-bottom: 1.5rem;
    color: var(--dark-color);
}

.card {
    background: white;
    border-radius: 8px;
    padding: 1.5rem;
    box-shadow: var(--shadow);
    margin-bottom: 1.5rem;
}

.card h3 {
    font-size: 1.125rem;
    font-weight: 600;
    margin-bottom: 1rem;
    color: var(--dark-color);
}

.dashboard-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 1.5rem;
}

.full-width {
    grid-column: 1 / -1;
}

.status-content {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.status-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border-color);
}

.status-item:last-child {
    border-bottom: none;
}

.status-item .label {
    font-weight: 500;
    color: var(--secondary-color);
}

.status-item .value {
    font-weight: 600;
    color: var(--dark-color);
}

.metrics-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
}

.metric {
    text-align: center;
    padding: 1rem;
    background: var(--light-color);
    border-radius: 6px;
}

.metric-label {
    display: block;
    font-size: 0.875rem;
    color: var(--secondary-color);
    margin-bottom: 0.25rem;
}

.metric-value {
    display: block;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--primary-color);
}

.btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.3s ease;
    text-decoration: none;
}

.btn-primary {
    background: var(--primary-color);
    color: white;
}

.btn-primary:hover {
    background: #1d4ed8;
}

.btn-secondary {
    background: var(--secondary-color);
    color: white;
}

.btn-secondary:hover {
    background: #475569;
}

.btn-success {
    background: var(--success-color);
    color: white;
}

.btn-success:hover {
    background: #059669;
}

.btn-warning {
    background: var(--warning-color);
    color: white;
}

.btn-warning:hover {
    background: #d97706;
}

.btn-danger {
    background: var(--danger-color);
    color: white;
}

.btn-danger:hover {
    background: #dc2626;
}

.btn-info {
    background: var(--info-color);
    color: white;
}

.btn-info:hover {
    background: #2563eb;
}

.component-controls,
.ai-controls,
.monitoring-controls,
.testing-controls,
.deployment-controls,
.performance-controls,
.alerts-controls {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
}

.control-group {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}

.control-group label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--dark-color);
}

.control-group select,
.control-group input {
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 4px;
    font-size: 0.875rem;
}

.components-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1rem;
}

.component-card {
    background: white;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 1rem;
    transition: all 0.3s ease;
}

.component-card:hover {
    box-shadow: var(--shadow-lg);
    transform: translateY(-2px);
}

.component-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
}

.component-name {
    font-weight: 600;
    color: var(--dark-color);
}

.component-status {
    padding: 0.25rem 0.5rem;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
}

.component-status.active {
    background: var(--success-color);
    color: white;
}

.component-status.inactive {
    background: var(--secondary-color);
    color: white;
}

.component-status.error {
    background: var(--danger-color);
    color: white;
}

.component-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
}

.component-actions .btn {
    font-size: 0.75rem;
    padding: 0.25rem 0.5rem;
}

.alerts-list,
.test-details {
    max-height: 400px;
    overflow-y: auto;
}

.alert-item,
.test-item {
    padding: 1rem;
    border-left: 4px solid var(--warning-color);
    background: var(--light-color);
    margin-bottom: 0.75rem;
    border-radius: 0 4px 4px 0;
}

.alert-item.critical {
    border-left-color: var(--danger-color);
}

.alert-item.info {
    border-left-color: var(--info-color);
}

.alert-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
}

.alert-title {
    font-weight: 600;
    color: var(--dark-color);
}

.alert-time {
    font-size: 0.875rem;
    color: var(--secondary-color);
}

.alert-message {
    font-size: 0.875rem;
    color: var(--dark-color);
}

@media (max-width: 768px) {
    .sidebar {
        width: 200px;
    }
    
    .main-content {
        margin-left: 200px;
    }
    
    .dashboard-grid {
        grid-template-columns: 1fr;
    }
    
    .metrics-grid {
        grid-template-columns: 1fr;
    }
    
    .component-controls,
    .ai-controls,
    .monitoring-controls {
        flex-direction: column;
    }
}

@media (max-width: 640px) {
    .sidebar {
        transform: translateX(-100%);
        transition: transform 0.3s ease;
    }
    
    .sidebar.open {
        transform: translateX(0);
    }
    
    .main-content {
        margin-left: 0;
    }
    
    .header {
        padding: 1rem;
    }
    
    .header h1 {
        font-size: 1.25rem;
    }
    
    .main-content {
        padding: 1rem;
    }
}

/* Loading spinner */
.loading {
    display: inline-block;
    width: 20px;
    height: 20px;
    border: 3px solid rgba(255, 255, 255, 0.3);
    border-radius: 50%;
    border-top-color: white;
    animation: spin 1s ease-in-out infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* Animations */
.fade-in {
    animation: fadeIn 0.5s ease-in;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.slide-in {
    animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
    from { transform: translateX(-100%); }
    to { transform: translateX(0); }
}
        """
        
        # Write CSS file
        with open(self.static_dir / "styles.css", "w") as f:
            f.write(css_content)
    
    def _generate_javascript(self):
        """Generate JavaScript code"""
        js_content = """
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
        """
        
        # Write JavaScript file
        with open(self.static_dir / "control-panel.js", "w") as f:
            f.write(js_content)


# Main Control Panel class
class ControlPanel:
    """Main control panel system"""
    
    def __init__(self, drive_engine):
        self.drive_engine = drive_engine
        self.api = ControlPanelAPI(drive_engine)
        self.ui = ControlPanelUI()
        
        # Configuration
        self.host = "0.0.0.0"
        self.port = 8080
        self.debug = True
    
    async def start(self):
        """Start the control panel"""
        logger.info("Starting JARVIS Control Panel...")
        
        # Start drive engine if not already running
        if self.drive_engine.status.value == "stopped":
            await self.drive_engine.start()
        
        # Start monitoring if available
        if hasattr(self.drive_engine, 'monitoring_interface'):
            await self.drive_engine.monitoring_interface.start_monitoring()
        
        # Start performance optimizer if available
        if hasattr(self.drive_engine, 'performance_optimizer'):
            await self.drive_engine.performance_optimizer.start_optimization()
        
        # Start the web server
        config = uvicorn.Config(
            app=self.api.app,
            host=self.host,
            port=self.port,
            log_level="info" if not self.debug else "debug"
        )
        
        server = uvicorn.Server(config)
        
        logger.info(f"Control Panel started at http://{self.host}:{self.port}")
        logger.info(f"Dashboard available at http://{self.host}:{self.port}/static/dashboard.html")
        
        await server.serve()
    
    async def stop(self):
        """Stop the control panel"""
        logger.info("Stopping JARVIS Control Panel...")
        
        # Stop monitoring
        if hasattr(self.drive_engine, 'monitoring_interface'):
            await self.drive_engine.monitoring_interface.stop_monitoring()
        
        # Stop performance optimizer
        if hasattr(self.drive_engine, 'performance_optimizer'):
            await self.drive_engine.performance_optimizer.stop_optimization()
        
        logger.info("Control Panel stopped")


# Example usage
async def demo_control_panel():
    """Demonstrate control panel"""
    print("=== JARVIS Control Panel Demo ===")
    
    # Import drive engine
    from drive_engine.jarvis_drive_engine import get_drive_engine
    
    # Get drive engine
    drive_engine = get_drive_engine()
    
    # Initialize drive engine
    await drive_engine.initialize()
    
    # Create control panel
    control_panel = ControlPanel(drive_engine)
    
    print("Control Panel created!")
    print("To start the web interface, call: await control_panel.start()")
    print("The panel will be available at: http://localhost:8080")


if __name__ == "__main__":
    asyncio.run(demo_control_panel())
