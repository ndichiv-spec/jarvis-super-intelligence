"""
JARVIS Web Dashboard for Codebase Presentation
==============================================
Interactive web dashboard for displaying JARVIS codebase architecture,
components, scripts, and real-time metrics.

Features:
- Interactive architecture visualization
- Real-time code metrics
- Component dependency mapping
- Searchable codebase index
- Script automation tracking
- Performance monitoring
- Responsive design
- Real-time updates
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn

from dashboard.codebase_documentation import get_codebase_documentation_system

logger = logging.getLogger(__name__)


class DashboardTheme(Enum):
    """Dashboard theme enumeration"""
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class ViewMode(Enum):
    """View mode enumeration"""
    ARCHITECTURE = "architecture"
    COMPONENTS = "components"
    SCRIPTS = "scripts"
    METRICS = "metrics"
    SEARCH = "search"


@dataclass
class DashboardConfig:
    """Dashboard configuration"""
    theme: DashboardTheme = DashboardTheme.AUTO
    view_mode: ViewMode = ViewMode.ARCHITECTURE
    auto_refresh: bool = True
    refresh_interval: int = 30  # seconds
    show_metrics: bool = True
    show_dependencies: bool = True
    show_performance: bool = True


class JARVISWebDashboard:
    """JARVIS web dashboard for codebase presentation"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8090):
        self.host = host
        self.port = port
        self.app = FastAPI(title="JARVIS Codebase Dashboard", version="1.0.0")
        
        # Setup templates
        self.templates_dir = Path(__file__).parent / "templates"
        self.templates_dir.mkdir(exist_ok=True)
        self.templates = Jinja2Templates(directory=str(self.templates_dir))
        
        # Setup static files
        self.static_dir = Path(__file__).parent / "static"
        self.static_dir.mkdir(exist_ok=True)
        self.app.mount("/static", StaticFiles(directory=str(self.static_dir)), name="static")
        
        # Initialize documentation system
        self.doc_system = get_codebase_documentation_system()
        
        # Dashboard state
        self.config = DashboardConfig()
        self.connected_clients: List[WebSocket] = []
        self.last_update = None
        
        # Setup routes
        self._setup_routes()
        self._create_templates()
        self._create_static_files()
    
    def _setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard_home():
            """Main dashboard page"""
            return self.templates.TemplateResponse("dashboard.html", {
                "request": {"url": "/"},
                "title": "JARVIS Codebase Dashboard",
                "config": self.config
            })
        
        @self.app.get("/api/dashboard")
        async def get_dashboard_data():
            """Get dashboard data"""
            try:
                # Scan codebase if needed
                scan_result = await self.doc_system.scan_codebase()
                
                # Get dashboard data
                dashboard_data = self.doc_system.get_dashboard_data()
                
                # Add scan result
                dashboard_data['scan_result'] = scan_result
                
                return dashboard_data
                
            except Exception as e:
                logger.error(f"Failed to get dashboard data: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/components")
        async def get_components():
            """Get all components"""
            try:
                components = {}
                for component_id, component in self.doc_system.components.items():
                    components[component_id] = {
                        'id': component.id,
                        'name': component.name,
                        'type': component.type.value,
                        'file_path': component.file_path,
                        'description': component.description,
                        'functions': component.functions,
                        'classes': component.classes,
                        'imports': component.imports,
                        'lines_of_code': component.lines_of_code,
                        'complexity_score': component.complexity_score,
                        'last_modified': component.last_modified.isoformat(),
                        'tags': component.tags,
                        'metrics': component.metrics
                    }
                
                return {"components": components, "total": len(components)}
                
            except Exception as e:
                logger.error(f"Failed to get components: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/components/{component_id}")
        async def get_component(component_id: str):
            """Get specific component"""
            try:
                component = self.doc_system.get_component(component_id)
                if not component:
                    raise HTTPException(status_code=404, detail="Component not found")
                
                return {
                    'id': component.id,
                    'name': component.name,
                    'type': component.type.value,
                    'file_path': component.file_path,
                    'description': component.description,
                    'functions': component.functions,
                    'classes': component.classes,
                    'imports': component.imports,
                    'lines_of_code': component.lines_of_code,
                    'complexity_score': component.complexity_score,
                    'last_modified': component.last_modified.isoformat(),
                    'tags': component.tags,
                    'metrics': component.metrics
                }
                
            except Exception as e:
                logger.error(f"Failed to get component {component_id}: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/scripts")
        async def get_scripts():
            """Get all scripts"""
            try:
                scripts = {}
                for script_id, script in self.doc_system.scripts.items():
                    scripts[script_id] = {
                        'id': script.id,
                        'name': script.name,
                        'type': script.type.value,
                        'file_path': script.file_path,
                        'description': script.description,
                        'purpose': script.purpose,
                        'dependencies': script.dependencies,
                        'usage_count': script.usage_count,
                        'success_rate': script.success_rate,
                        'execution_time': script.execution_time,
                        'created_at': script.created_at.isoformat(),
                        'tags': script.tags
                    }
                
                return {"scripts": scripts, "total": len(scripts)}
                
            except Exception as e:
                logger.error(f"Failed to get scripts: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/scripts/{script_id}")
        async def get_script(script_id: str):
            """Get specific script"""
            try:
                script = self.doc_system.get_script(script_id)
                if not script:
                    raise HTTPException(status_code=404, detail="Script not found")
                
                return {
                    'id': script.id,
                    'name': script.name,
                    'type': script.type.value,
                    'file_path': script.file_path,
                    'description': script.description,
                    'purpose': script.purpose,
                    'dependencies': script.dependencies,
                    'usage_count': script.usage_count,
                    'success_rate': script.success_rate,
                    'execution_time': script.execution_time,
                    'created_at': script.created_at.isoformat(),
                    'tags': script.tags
                }
                
            except Exception as e:
                logger.error(f"Failed to get script {script_id}: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/architecture")
        async def get_architecture():
            """Get architecture data"""
            try:
                return self.doc_system.get_architecture_overview()
                
            except Exception as e:
                logger.error(f"Failed to get architecture: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/search")
        async def search_codebase(query: str, limit: int = 20):
            """Search codebase"""
            try:
                return self.doc_system.search_codebase(query, limit)
                
            except Exception as e:
                logger.error(f"Failed to search codebase: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/metrics")
        async def get_metrics():
            """Get detailed metrics"""
            try:
                # Get dashboard data
                dashboard_data = self.doc_system.get_dashboard_data()
                
                # Calculate additional metrics
                components = self.doc_system.components
                scripts = self.doc_system.scripts
                
                metrics = {
                    'overview': dashboard_data['overview'],
                    'components': {
                        'total': len(components),
                        'by_type': dashboard_data['components']['by_type'],
                        'by_complexity': dashboard_data['components']['by_complexity'],
                        'average_complexity': sum(c.complexity_score for c in components.values()) / len(components) if components else 0,
                        'total_functions': sum(len(c.functions) for c in components.values()),
                        'total_classes': sum(len(c.classes) for c in components.values()),
                        'total_lines': dashboard_data['components']['total_lines']
                    },
                    'scripts': {
                        'total': len(scripts),
                        'by_type': dashboard_data['scripts']['by_type'],
                        'total_usage': dashboard_data['scripts']['total_usage'],
                        'average_success_rate': dashboard_data['scripts']['average_success_rate'],
                        'average_execution_time': sum(s.execution_time for s in scripts.values()) / len(scripts) if scripts else 0
                    },
                    'architecture': dashboard_data['architecture'],
                    'health': {
                        'last_scan': dashboard_data['overview']['last_scan'],
                        'scan_status': 'healthy',
                        'components_scanned': dashboard_data['overview']['total_components'],
                        'scripts_scanned': dashboard_data['overview']['total_scripts']
                    }
                }
                
                return metrics
                
            except Exception as e:
                logger.error(f"Failed to get metrics: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/scan")
        async def scan_codebase(force: bool = False):
            """Trigger codebase scan"""
            try:
                result = await self.doc_system.scan_codebase(force=force)
                
                # Notify connected clients
                await self._notify_clients({
                    'type': 'scan_completed',
                    'data': result
                })
                
                return result
                
            except Exception as e:
                logger.error(f"Failed to scan codebase: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates"""
            await websocket.accept()
            self.connected_clients.append(websocket)
            
            try:
                # Send initial data
                await websocket.send_json({
                    'type': 'connected',
                    'data': await self.doc_system.get_dashboard_data()
                })
                
                # Keep connection alive
                while True:
                    try:
                        message = await websocket.receive_text()
                        # Handle client messages if needed
                        await asyncio.sleep(1)
                    except WebSocketDisconnect:
                        break
                    except Exception as e:
                        logger.error(f"WebSocket error: {e}")
                        break
            
            finally:
                self.connected_clients.remove(websocket)
        
        @self.app.post("/api/config")
        async def update_config(config: Dict[str, Any]):
            """Update dashboard configuration"""
            try:
                # Update configuration
                if 'theme' in config:
                    self.config.theme = DashboardTheme(config['theme'])
                if 'view_mode' in config:
                    self.config.view_mode = ViewMode(config['view_mode'])
                if 'auto_refresh' in config:
                    self.config.auto_refresh = config['auto_refresh']
                if 'refresh_interval' in config:
                    self.config.refresh_interval = config['refresh_interval']
                
                return {"status": "success", "config": self.config.__dict__}
                
            except Exception as e:
                logger.error(f"Failed to update config: {e}")
                raise HTTPException(status_code=500, detail=str(e))
    
    async def _notify_clients(self, message: Dict[str, Any]):
        """Notify all connected WebSocket clients"""
        if self.connected_clients:
            for client in self.connected_clients:
                try:
                    await client.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to notify client: {e}")
    
    def _create_templates(self):
        """Create HTML templates"""
        # Main dashboard template
        dashboard_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <script src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <style>
        .dark { background-color: #1a202a; color: #e2e8f0; }
        .dark .bg-white { background-color: #374151; }
        .dark .text-gray-900 { color: #f3f4f6; }
        .dark .text-gray-600 { color: #d1d5db; }
        .dark .border-gray-200 { border-color: #4b5563; }
        .dark .bg-gray-50 { background-color: #374151; }
        .architecture-container { height: 600px; border: 1px solid #e5e7eb; }
        .dark .architecture-container { border-color: #4b5563; }
    </style>
</head>
<body class="bg-gray-50" x-data="{ theme: 'auto' }" :class="{ 'dark' : theme === 'dark' }">
    <div class="min-h-screen">
        <!-- Header -->
        <header class="bg-white shadow-sm border-b border-gray-200">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="flex justify-between items-center h-16">
                    <div class="flex items-center">
                        <h1 class="text-2xl font-bold text-gray-900">{{ title }}</h1>
                    </div>
                    <div class="flex items-center space-x-4">
                        <button @click="scanCodebase()" class="bg-blue-500 text-white px-4 py-2 rounded-md hover:bg-blue-600">
                            Scan Codebase
                        </button>
                        <select x-model="theme" class="border border-gray-300 rounded-md px-3 py-2">
                            <option value="auto">Auto</option>
                            <option value="light">Light</option>
                            <option value="dark">Dark</option>
                        </select>
                    </div>
                </div>
            </div>
        </header>

        <!-- Main Content -->
        <main class="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
            <!-- Overview Cards -->
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                <div class="bg-white p-6 rounded-lg shadow">
                    <h3 class="text-lg font-medium text-gray-900">Components</h3>
                    <p class="text-3xl font-bold text-blue-600" id="components-count">0</p>
                    <p class="text-sm text-gray-600">Total components</p>
                </div>
                <div class="bg-white p-6 rounded-lg shadow">
                    <h3 class="text-lg font-medium text-gray-900">Scripts</h3>
                    <p class="text-3xl font-bold text-green-600" id="scripts-count">0</p>
                    <p class="text-sm text-gray-600">Total scripts</p>
                </div>
                <div class="bg-white p-6 rounded-lg shadow">
                    <h3 class="text-lg font-medium text-gray-900">Lines of Code</h3>
                    <p class="text-3xl font-bold text-purple-600" id="lines-count">0</p>
                    <p class="text-sm text-gray-600">Total lines</p>
                </div>
                <div class="bg-white p-6 rounded-lg shadow">
                    <h3 class="text-lg font-medium text-gray-900">Last Scan</h3>
                    <p class="text-lg font-bold text-indigo-600" id="last-scan">Never</p>
                    <p class="text-sm text-gray-600">Last scan time</p>
                </div>
            </div>

            <!-- Navigation Tabs -->
            <div class="border-b border-gray-200 mb-8">
                <nav class="-mb-px flex space-x-8">
                    <button @click="setView('architecture')" class="py-2 px-1 border-b-2 font-medium text-sm border-blue-500 text-blue-600">
                        Architecture
                    </button>
                    <button @click="setView('components')" class="py-2 px-1 border-b-2 font-medium text-sm border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300">
                        Components
                    </button>
                    <button @click="setView('scripts')" class="py-2 px-1 border-b-2 font-medium text-sm border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300">
                        Scripts
                    </button>
                    <button @click="setView('metrics')" class="py-2 px-1 border-b-2 font-medium text-sm border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300">
                        Metrics
                    </button>
                    <button @click="setView('search')" class="py-2 px-1 border-b-2 font-medium text-sm border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300">
                        Search
                    </button>
                </nav>
            </div>

            <!-- Content Area -->
            <div id="content-area">
                <!-- Architecture View -->
                <div x-show="view === 'architecture'" class="space-y-6">
                    <div class="bg-white p-6 rounded-lg shadow">
                        <h2 class="text-xl font-bold text-gray-900 mb-4">Architecture Visualization</h2>
                        <div id="architecture-network" class="architecture-container"></div>
                    </div>
                    
                    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div class="bg-white p-6 rounded-lg shadow">
                            <h3 class="text-lg font-medium text-gray-900 mb-4">Components by Type</h3>
                            <div id="components-by-type"></div>
                        </div>
                        <div class="bg-white p-6 rounded-lg shadow">
                            <h3 class="text-lg font-medium text-gray-900 mb-4">Architecture Stats</h3>
                            <div id="architecture-stats"></div>
                        </div>
                    </div>
                </div>

                <!-- Components View -->
                <div x-show="view === 'components'" class="space-y-6">
                    <div class="bg-white p-6 rounded-lg shadow">
                        <div class="flex justify-between items-center mb-4">
                            <h2 class="text-xl font-bold text-gray-900">Components</h2>
                            <input type="text" x-model="searchQuery" placeholder="Search components..." 
                                   class="border border-gray-300 rounded-md px-3 py-2">
                        </div>
                        <div id="components-list" class="space-y-4"></div>
                    </div>
                </div>

                <!-- Scripts View -->
                <div x-show="view === 'scripts'" class="space-y-6">
                    <div class="bg-white p-6 rounded-lg shadow">
                        <h2 class="text-xl font-bold text-gray-900 mb-4">Scripts</h2>
                        <div id="scripts-list" class="space-y-4"></div>
                    </div>
                </div>

                <!-- Metrics View -->
                <div x-show="view === 'metrics'" class="space-y-6">
                    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div class="bg-white p-6 rounded-lg shadow">
                            <h3 class="text-lg font-medium text-gray-900 mb-4">Component Metrics</h3>
                            <canvas id="component-chart"></canvas>
                        </div>
                        <div class="bg-white p-6 rounded-lg shadow">
                            <h3 class="text-lg font-medium text-gray-900 mb-4">Script Metrics</h3>
                            <canvas id="script-chart"></canvas>
                        </div>
                    </div>
                    <div class="bg-white p-6 rounded-lg shadow">
                        <h3 class="text-lg font-medium text-gray-900 mb-4">Performance Metrics</h3>
                        <canvas id="performance-chart"></canvas>
                    </div>
                </div>

                <!-- Search View -->
                <div x-show="view === 'search'" class="space-y-6">
                    <div class="bg-white p-6 rounded-lg shadow">
                        <div class="flex justify-between items-center mb-4">
                            <h2 class="text-xl font-bold text-gray-900">Search Codebase</h2>
                            <input type="text" x-model="searchQuery" placeholder="Search..." 
                                   class="border border-gray-300 rounded-md px-3 py-2">
                        </div>
                        <div id="search-results" class="space-y-4"></div>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <script>
        // Global state
        let view = 'architecture';
        let searchQuery = '';
        let dashboardData = null;

        // Initialize
        document.addEventListener('DOMContentLoaded', async () => {
            await loadDashboardData();
            updateOverviewCards();
            setView('architecture');
            
            // Auto-refresh
            setInterval(async () => {
                await loadDashboardData();
                updateOverviewCards();
                updateCurrentView();
            }, 30000);
        });

        // Load dashboard data
        async function loadDashboardData() {
            try {
                const response = await fetch('/api/dashboard');
                dashboardData = await response.json();
            } catch (error) {
                console.error('Failed to load dashboard data:', error);
            }
        }

        // Update overview cards
        function updateOverviewCards() {
            if (!dashboardData) return;

            document.getElementById('components-count').textContent = dashboardData.overview.total_components;
            document.getElementById('scripts-count').textContent = dashboardData.overview.total_scripts;
            document.getElementById('lines-count').textContent = dashboardData.components.total_lines.toLocaleString();
            document.getElementById('last-scan').textContent = dashboardData.overview.last_scan ? 
                new Date(dashboardData.overview.last_scan).toLocaleString() : 'Never';
        }

        // Set view
        function setView(newView) {
            view = newView;
            updateCurrentView();
        }

        // Update current view
        async function updateCurrentView() {
            if (!dashboardData) return;

            switch (view) {
                case 'architecture':
                    await updateArchitectureView();
                    break;
                case 'components':
                    await updateComponentsView();
                    break;
                case 'scripts':
                    await updateScriptsView();
                    break;
                case 'metrics':
                    await updateMetricsView();
                    break;
                case 'search':
                    updateSearchView();
                    break;
            }
        }

        // Update architecture view
        async function updateArchitectureView() {
            const architectureData = await fetch('/api/architecture').then(r => r.json());
            
            // Create network visualization
            const container = document.getElementById('architecture-network');
            const nodes = new vis.DataSet();
            const edges = new vis.DataSet();
            
            // Add nodes
            Object.keys(architectureData.components_by_type).forEach(type => {
                architectureData.components_by_type[type].forEach((node, index) => {
                    nodes.add({
                        id: node.id,
                        label: node.name,
                        color: getNodeColor(type),
                        level: node.level || 3
                    });
                });
            });
            
            // Add edges
            architectureData.edges.forEach(edge => {
                edges.add({
                    from: edge.source,
                    to: edge.target
                });
            });
            
            const data = { nodes, edges };
            const options = {
                nodes: {
                    shape: 'dot',
                    size: 20,
                    font: {
                        size: 14
                    }
                },
                edges: {
                    smooth: {
                        type: 'cubicBezier'
                    }
                },
                layout: {
                    hierarchical: {
                        direction: 'UD',
                        sortMethod: 'directed'
                    }
                }
            };
            
            new vis.Network(container, data, options);
            
            // Update stats
            updateArchitectureStats(architectureData);
        }

        // Update components view
        async function updateComponentsView() {
            const response = await fetch('/api/components');
            const data = await response.json();
            
            const container = document.getElementById('components-list');
            container.innerHTML = '';
            
            Object.values(data.components).forEach(component => {
                if (!searchQuery || component.name.toLowerCase().includes(searchQuery.toLowerCase()) {
                    const componentEl = createComponentElement(component);
                    container.appendChild(componentEl);
                }
            });
        }

        // Update scripts view
        async function updateScriptsView() {
            const response = await fetch('/api/scripts');
            const data = await response.json();
            
            const container = document.getElementById('scripts-list');
            container.innerHTML = '';
            
            Object.values(data.scripts).forEach(script => {
                if (!searchQuery || script.name.toLowerCase().includes(searchQuery.toLowerCase())) {
                    const scriptEl = createScriptElement(script);
                    container.appendChild(scriptEl);
                }
            });
        }

        // Update metrics view
        async function updateMetricsView() {
            const response = await fetch('/api/metrics');
            const data = await response.json();
            
            // Update component chart
            updateComponentChart(data.components);
            
            // Update script chart
            updateScriptChart(data.scripts);
            
            // Update performance chart
            updatePerformanceChart(data);
        }

        // Update search view
        function updateSearchView() {
            if (!searchQuery) {
                document.getElementById('search-results').innerHTML = '<p class="text-gray-500">Enter a search query to find components and scripts.</p>';
                return;
            }
            
            performSearch(searchQuery);
        }

        // Perform search
        async function performSearch(query) {
            try {
                const response = await fetch(`/api/search?query=${encodeURIComponent(query)}&limit=20`);
                const data = await response.json();
                
                const container = document.getElementById('search-results');
                container.innerHTML = '';
                
                if (data.results.length === 0) {
                    container.innerHTML = '<p class="text-gray-500">No results found.</p>';
                    return;
                }
                
                data.results.forEach(result => {
                    const resultEl = createSearchResultElement(result);
                    container.appendChild(resultEl);
                });
                
            } catch (error) {
                console.error('Search failed:', error);
            }
        }

        // Helper functions
        function getNodeColor(type) {
            const colors = {
                'core': '#e74c3c',
                'api': '#3498db',
                'web': '#2ecc71',
                'mobile': '#f39c12',
                'analytics': '#9b59b6',
                'security': '#e67e22',
                'performance': '#1abc9c',
                'monitoring': '#34495e',
                'ai': '#8e44ad',
                'ml': '#e74c3c',
                'neuromorphic': '#f39c12',
                'quantum': '#9b59b6'
            };
            return colors[type] || '#95a5a6';
        }

        function createComponentElement(component) {
            const div = document.createElement('div');
            div.className = 'border border-gray-200 rounded-lg p-4 hover:bg-gray-50';
            div.innerHTML = `
                <div class="flex justify-between items-start">
                    <div>
                        <h3 class="text-lg font-medium text-gray-900">${component.name}</h3>
                        <p class="text-sm text-gray-600">${component.description}</p>
                        <div class="mt-2 flex flex-wrap gap-2">
                            <span class="px-2 py-1 text-xs font-medium rounded bg-blue-100 text-blue-800">${component.type}</span>
                            <span class="px-2 py-1 text-xs font-medium rounded bg-green-100 text-green-800">${component.lines_of_code} lines</span>
                            <span class="px-2 py-1 text-xs font-medium rounded bg-purple-100 text-purple-800">${component.complexity_score.toFixed(2)} complexity</span>
                        </div>
                    </div>
                    <div class="text-sm text-gray-500">
                        <p>${component.file_path}</p>
                    </div>
                </div>
            `;
            return div;
        }

        function createScriptElement(script) {
            const div = document.createElement('div');
            div.className = 'border border-gray-200 rounded-lg p-4 hover:bg-gray-50';
            div.innerHTML = `
                <div class="flex justify-between items-start">
                    <div>
                        <h3 class="text-lg font-medium text-gray-900">${script.name}</h3>
                        <p class="text-sm text-gray-600">${script.description}</p>
                        <p class="text-sm text-gray-500 mt-1">${script.purpose}</p>
                        <div class="mt-2 flex flex-wrap gap-2">
                            <span class="px-2 py-1 text-xs font-medium rounded bg-orange-100 text-orange-800">${script.type}</span>
                            <span class="px-2 py-1 text-xs font-medium rounded bg-blue-100 text-blue-800">${script.usage_count} uses</span>
                            <span class="px-2 py-1 text-xs font-medium rounded bg-green-100 text-green-800">${(script.success_rate * 100).toFixed(1)}% success</span>
                        </div>
                    </div>
                    <div class="text-sm text-gray-500">
                        <p>${script.file_path}</p>
                    </div>
                </div>
            `;
            return div;
        }

        function createSearchResultElement(result) {
            const div = document.createElement('div');
            div.className = 'border border-gray-200 rounded-lg p-4 hover:bg-gray-50 cursor-pointer';
            div.innerHTML = `
                <div class="flex justify-between items-start">
                    <div>
                        <h3 class="text-lg font-medium text-gray-900">${result.name}</h3>
                        <p class="text-sm text-gray-600">${result.description}</p>
                        <p class="text-sm text-gray-500 mt-1">${result.file_path}</p>
                        <span class="px-2 py-1 text-xs font-medium rounded bg-indigo-100 text-indigo-800">${result.type}</span>
                    </div>
                </div>
            `;
            return div;
        }

        function updateArchitectureStats(architectureData) {
            const container = document.getElementById('architecture-stats');
            container.innerHTML = `
                <div class="space-y-2">
                    <div class="flex justify-between">
                        <span class="text-sm font-medium text-gray-600">Total Nodes:</span>
                        <span class="text-sm font-medium text-gray-900">${architectureData.total_nodes}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-sm font-medium text-gray-600">Total Edges:</span>
                        <span class="text-sm font-medium text-gray-900">${architectureData.total_edges}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-sm font-medium text-gray-600">Graph Density:</span>
                        <span class="text-sm font-medium text-gray-900">${(architectureData.graph_density * 100).toFixed(2)}%</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-sm font-medium text-gray-600">Connected:</span>
                        <span class="text-sm font-medium text-gray-900">${architectureData.is_connected ? 'Yes' : 'No'}</span>
                    </div>
                </div>
            `;
        }

        function updateComponentChart(components) {
            const ctx = document.getElementById('component-chart').getContext('2d');
            const data = Object.values(components.by_type);
            const labels = Object.keys(components.by_type);
            
            new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: labels,
                    datasets: [{
                        data: data,
                        backgroundColor: [
                            '#e74c3c', '#3498db', '#2ecc71', '#f39c12',
                            '#9b59b6', '#e67e22', '#1abc9c', '#34495e',
                            '#8e44ad', '#e74c3c', '#f39c12', '#9b59b6'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            position: 'bottom'
                        }
                    }
                }
            });
        }

        function updateScriptChart(scripts) {
            const ctx = document.getElementById('script-chart').getContext('2d');
            const data = Object.values(scripts.by_type);
            const labels = Object.keys(scripts.by_type);
            
            new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: data,
                        backgroundColor: [
                            '#f59e0b', '#ef4444', '#10b981', '#3b82f6',
                            '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            position: 'bottom'
                        }
                    }
                }
            });
        }

        function updatePerformanceChart(metrics) {
            const ctx = document.getElementById('performance-chart').getContext('2d');
            
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: ['Components', 'Scripts', 'Architecture'],
                    datasets: [{
                        label: 'Items Count',
                        data: [
                            metrics.components.total,
                            metrics.scripts.total,
                            metrics.architecture.total_nodes
                        ],
                        backgroundColor: [
                            'rgba(59, 130, 246, 0.5)',
                            'rgba(16, 185, 129, 0.5)',
                            'rgba(245, 158, 11, 0.5)'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            display: false
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        }

        // Scan codebase
        async function scanCodebase() {
            try {
                const response = await fetch('/api/scan', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ force: false })
                });
                const result = await response.json();
                
                // Show notification
                showNotification(result.status === 'completed' ? 'success' : 'error', 
                             result.status === 'completed' ? 'Codebase scanned successfully' : 'Scan failed');
                
                // Reload data
                await loadDashboardData();
                updateOverviewCards();
                updateCurrentView();
                
            } catch (error) {
                console.error('Scan failed:', error);
                showNotification('error', 'Scan failed');
            }
        }

        // Show notification
        function showNotification(type, message) {
            const notification = document.createElement('div');
            notification.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 ${
                type === 'success' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'
            }`;
            notification.textContent = message;
            document.body.appendChild(notification);
            
            setTimeout(() => {
                document.body.removeChild(notification);
            }, 3000);
        }

        // WebSocket connection
        const ws = new WebSocket('ws://localhost:8090/ws');
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'scan_completed') {
                showNotification('success', 'Codebase scan completed');
                loadDashboardData();
                updateOverviewCards();
                updateCurrentView();
            }
        };
    </script>
</body>
</html>
        """
        
        # Write the template
        with open(self.templates_dir / "dashboard.html", 'w') as f:
            f.write(dashboard_html)
        
        logger.info("Created dashboard template")
    
    def _create_static_files(self):
        """Create static CSS and JS files"""
        # Create CSS file
        css_content = """
/* Custom dashboard styles */
.dashboard-container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 0 20px;
}

.metric-card {
    transition: all 0.3s ease;
}

.metric-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.component-card {
    transition: all 0.3s ease;
}

.component-card:hover {
    background-color: #f9fafb;
}

.dark .component-card:hover {
    background-color: #374151;
}

.search-highlight {
    background-color: #fef3c7;
    border-color: #f59e0b;
}

.dark .search-highlight {
    background-color: #1f2937;
    border-color: #d97706;
}

.loading-spinner {
    border: 3px solid #f3f4f6;
    border-top: 3px solid #3498db;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
        """
        
        with open(self.static_dir / "dashboard.css", 'w') as f:
            f.write(css_content)
        
        logger.info("Created static CSS file")
    
    async def run(self):
        """Run the web dashboard"""
        logger.info(f"Starting JARVIS Codebase Dashboard on {self.host}:{self.port}")
        
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        
        await uvicorn.run(config)


# Global instance
_web_dashboard = None


def get_web_dashboard() -> JARVISWebDashboard:
    """Get global web dashboard instance"""
    global _web_dashboard
    if _web_dashboard is None:
        _web_dashboard = JARVISWebDashboard()
    return _web_dashboard


if __name__ == "__main__":
    dashboard = get_web_dashboard()
    asyncio.run(dashboard.run())
