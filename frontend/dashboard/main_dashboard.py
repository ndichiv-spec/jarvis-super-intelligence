"""
JARVIS Codebase Dashboard - Main Integration
==========================================
Main integration script for JARVIS codebase dashboard that brings together
all components for comprehensive codebase visualization and monitoring.

Usage:
    python main_dashboard.py [--host HOST] [--port PORT] [--debug]

Features:
- Integrated dashboard with all components
- Real-time monitoring and updates
- Interactive architecture visualization
- Comprehensive code metrics
- Searchable codebase index
- Web-based interface
- WebSocket real-time updates
- Health monitoring
"""

import asyncio
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path
import sys
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import dashboard components
from frontend.dashboard.codebase_documentation import get_codebase_documentation_system
from frontend.dashboard.web_dashboard import JARVISWebDashboard
from frontend.dashboard.architecture_visualizer import get_architecture_visualizer
from frontend.dashboard.code_metrics import get_code_metrics_analyzer
from frontend.dashboard.searchable_index import get_searchable_codebase_index
from frontend.dashboard.realtime_monitoring import get_realtime_monitoring_system

logger = logging.getLogger(__name__)


class IntegratedDashboard:
    """Integrated JARVIS codebase dashboard"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8090, debug: bool = False):
        self.host = host
        self.port = port
        self.debug = debug
        
        # Initialize components
        self.doc_system = get_codebase_documentation_system()
        self.web_dashboard = JARVISWebDashboard(host, port)
        self.architecture_visualizer = get_architecture_visualizer()
        self.metrics_analyzer = get_code_metrics_analyzer()
        self.search_index = get_searchable_codebase_index()
        self.monitoring_system = get_realtime_monitoring_system()
        
# Dashboard state
        self.initialized = False
        self.last_scan = None
        
        # Setup logging
        self._setup_logging()
    
    def _setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.DEBUG if self.debug else logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('dashboard.log'),
                logging.StreamHandler()
            ]
        )
    
    async def initialize(self):
        """Initialize all dashboard components"""
        try:
            logger.info("Initializing JARVIS Codebase Dashboard...")
            
            # Start monitoring system
            await self.monitoring_system.start_monitoring()
            
            # Perform initial codebase scan
            scan_result = await self.doc_system.scan_codebase(force=True)
            self.last_scan = scan_result
            
            # Initialize architecture visualizer
            if scan_result.get('status') == 'completed':
                # Load components and scripts into visualizer
                await self._load_architecture_data()
            
# Initialize search index
            await self._initialize_search_index()
            
            # Initialize metrics analyzer
            await self._initialize_metrics_analyzer()
            
            self.initialized = True
            logger.info("Dashboard initialization completed")
            
        except Exception as e:
            logger.error(f"Dashboard initialization failed: {e}")
            raise
    
    async def _load_architecture_data(self):
        """Load architecture data into visualizer"""
        try:
            # Get components and scripts from documentation system
            components_data = {}
            for component_id, component in self.doc_system.components.items():
                components_data[component_id] = {
                    'id': component.id,
                    'name': component.name,
                    'type': component.type.value,
                    'level': self._calculate_component_level(component),
                    'metrics': component.metrics
                }
            
            scripts_data = {}
            for script_id, script in self.doc_system.scripts.items():
                scripts_data[script_id] = {
                    'id': script.id,
                    'name': script.name,
                    'type': script.type.value,
                    'dependencies': script.dependencies
                }
            
            # Build dependency edges
            edges_data = []
            for component_id, component in self.doc_system.components.items():
                for import_name in component.imports:
                    # Find matching components
                    for other_id, other_component in self.doc_system.components.items():
                        if import_name in other_component.name.lower():
                            edges_data.append({
                                'source': component_id,
                                'target': other_id,
                                'type': 'import'
                            })
            
            # Load into visualizer
            self.architecture_visualizer.load_graph(
                list(components_data.values()),
                edges_data
            )
            
            # Apply initial layout
            await self.architecture_visualizer.apply_layout()
            
            logger.info(f"Loaded {len(components_data)} components and {len(edges_data)} edges into visualizer")
            
        except Exception as e:
            logger.error(f"Failed to load architecture data: {e}")
    
    def _calculate_component_level(self, component) -> int:
        """Calculate component level for visualization"""
        level_mapping = {
            'core': 0,
            'database': 1,
            'cache': 1,
            'queue': 1,
            'authentication': 2,
            'authorization': 2,
            'security': 2,
            'api': 3,
            'ai': 3,
            'ml': 3,
            'neuromorphic': 3,
            'quantum': 3,
            'web': 4,
            'mobile': 4,
            'analytics': 4,
            'monitoring': 5,
            'performance': 5,
            'tests': 6,
            'deployment': 6,
            'utilities': 6
        }
        
        return level_mapping.get(component.type.value, 3)
    
    async def _initialize_search_index(self):
        """Initialize searchable codebase index"""
        try:
            # Convert components and scripts to search format
            components_data = {}
            for component_id, component in self.doc_system.components.items():
                components_data[component_id] = {
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
                    'tags': component.tags
                }
            
            scripts_data = {}
            for script_id, script in self.doc_system.scripts.items():
                scripts_data[script_id] = {
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
            
            # Build search index
            await self.search_index.build_index(components_data, scripts_data)
            
            logger.info(f"Search index built with {len(components_data)} components and {len(scripts_data)} scripts")
            
        except Exception as e:
            logger.error(f"Failed to initialize search index: {e}")
    
    async def _initialize_metrics_analyzer(self):
        """Initialize metrics analyzer"""
        try:
            # Analyze system metrics
            project_root = Path("c:\\Users\\Administrator\\Jarvis")
            system_metrics = await self.metrics_analyzer.analyze_system(project_root)
            
            if system_metrics:
                logger.info(f"System metrics analyzed: {system_metrics.total_files} files, {system_metrics.total_lines} lines")
            else:
                logger.warning("System metrics analysis failed")
            
        except Exception as e:
            logger.error(f"Failed to initialize metrics analyzer: {e}")
    
    async def run(self):
        """Run the integrated dashboard"""
        try:
            # Initialize components
            await self.initialize()
            
            # Add WebSocket endpoint for real-time updates
            self.web_dashboard.app.websocket("/ws/monitoring")(self.websocket_monitoring_handler)
            
            # Add API endpoints for dashboard integration
            self._add_integrated_endpoints()
            
            # Run web dashboard
            logger.info(f"Starting integrated JARVIS Dashboard on {self.host}:{self.port}")
            await self.web_dashboard.run()
            
        except Exception as e:
            logger.error(f"Failed to run dashboard: {e}")
            raise
        finally:
            # Cleanup
            await self.cleanup()
    
    async def websocket_monitoring_handler(self, websocket: WebSocket):
        """WebSocket handler for real-time monitoring updates"""
        await websocket.accept()
        
        # Register with monitoring system
        self.monitoring_system.register_websocket(websocket)
        
        try:
            # Send initial status
            await websocket.send_json({
                'type': 'initial_status',
                'data': self.monitoring_system.get_system_status()
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
            # Unregister from monitoring system
            self.monitoring_system.unregister_websocket(websocket)
    
    def _add_integrated_endpoints(self):
        """Add integrated API endpoints"""
        
        @self.web_dashboard.app.get("/api/integrated/status")
        async def get_integrated_status():
            """Get integrated dashboard status"""
            try:
                return {
                    'initialized': self.initialized,
                    'last_scan': self.last_scan,
                    'components': {
                        'doc_system': 'active',
                        'web_dashboard': 'active',
                        'architecture_visualizer': 'active',
                        'metrics_analyzer': 'active',
                        'search_index': 'active',
                        'monitoring_system': 'active'
                    },
                    'statistics': {
                        'total_components': len(self.doc_system.components),
                        'total_scripts': len(self.doc_system.scripts),
                        'architecture_nodes': self.architecture_visualizer.node_count,
                        'architecture_edges': self.architecture_visualizer.edge_count,
                        'search_index_items': len(self.search_index.index),
                        'monitoring_events': len(self.monitoring_system.event_history),
                        'monitoring_alerts': len(self.monitoring_system.alerts)
                    },
                    'timestamp': datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"Failed to get integrated status: {e}")
                return {"error": str(e)}
        
        @self.web_dashboard.app.post("/api/integrated/scan")
        async def trigger_full_scan():
            """Trigger full codebase scan"""
            try:
                # Trigger scan
                scan_result = await self.monitoring_system.trigger_full_scan()
                
                # Update architecture data
                if scan_result.get('status') == 'completed':
                    await self._load_architecture_data()
                    await self._initialize_search_index()
                    await self._initialize_metrics_analyzer()
                
                return scan_result
                
            except Exception as e:
                logger.error(f"Failed to trigger full scan: {e}")
                return {"status": "failed", "error": str(e)}
        
        @self.web_dashboard.app.get("/api/architecture/visualization")
        async def get_architecture_visualization():
            """Get architecture visualization data"""
            try:
                return self.architecture_visualizer.get_visualization_data()
            except Exception as e:
                logger.error(f"Failed to get architecture visualization: {e}")
                return {"error": str(e)}
        
        @self.web_dashboard.app.post("/api/architecture/layout")
        async def apply_architecture_layout(algorithm: str = "force_directed"):
            """Apply architecture layout"""
            try:
                from dashboard.architecture_visualizer import LayoutAlgorithm
                layout_algo = LayoutAlgorithm(algorithm)
                await self.architecture_visualizer.apply_layout(layout_algo)
                return {"status": "success", "algorithm": algorithm}
            except Exception as e:
                logger.error(f"Failed to apply layout: {e}")
                return {"status": "failed", "error": str(e)}
        
        @self.web_dashboard.app.get("/api/architecture/node/{node_id}")
        async def get_architecture_node(node_id: str):
            """Get architecture node details"""
            try:
                return self.architecture_visualizer.get_node_details(node_id)
            except Exception as e:
                logger.error(f"Failed to get node details: {e}")
                return {"error": str(e)}
        
        @self.web_dashboard.app.get("/api/metrics/summary")
        async def get_metrics_summary():
            """Get metrics summary"""
            try:
                return self.metrics_analyzer.get_metric_summary()
            except Exception as e:
                logger.error(f"Failed to get metrics summary: {e}")
                return {"error": str(e)}
        
        @self.web_dashboard.app.get("/api/metrics/trends")
        async def get_metrics_trends(metric_type: str = "code_quality", days: int = 30):
            """Get metrics trends"""
            try:
                return self.metrics_analyzer.get_trends(metric_type, days)
            except Exception as e:
                logger.error(f"Failed to get metrics trends: {e}")
                return {"error": str(e)}
        
        @self.web_dashboard.app.get("/api/metrics/recommendations")
        async def get_metrics_recommendations(category: str = None):
            """Get metrics recommendations"""
            try:
                return self.metrics_analyzer.get_recommendations(category)
            except Exception as e:
                logger.error(f"Failed to get metrics recommendations: {e}")
                return {"error": str(e)}
        
        @self.web_dashboard.app.post("/api/search")
        async def search_codebase(query: str, search_type: str = "full_text", limit: int = 20):
            """Search codebase"""
            try:
                from dashboard.searchable_index import SearchQuery, SearchType, SearchScope, ResultRanking
                
                search_query = SearchQuery(
                    query=query,
                    search_type=SearchType(search_type),
                    scope=SearchScope.ENTIRE_CODEBASE,
                    ranking=ResultRanking.RELEVANCE,
                    limit=limit
                )
                
                return await self.search_index.search(search_query)
            except Exception as e:
                logger.error(f"Failed to search codebase: {e}")
                return {"error": str(e)}
        
        @self.web_dashboard.app.get("/api/search/suggestions")
        async def get_search_suggestions(query: str, limit: int = 10):
            """Get search suggestions"""
            try:
                return {"suggestions": self.search_index.get_search_suggestions(query, limit)}
            except Exception as e:
                logger.error(f"Failed to get search suggestions: {e}")
                return {"error": str(e)}
        
        @self.web_dashboard.app.get("/api/search/analytics")
        async def get_search_analytics(days: int = 30):
            """Get search analytics"""
            try:
                return self.search_index.get_search_analytics(days)
            except Exception as e:
                logger.error(f"Failed to get search analytics: {e}")
                return {"error": str(e)}
        
        @self.web_dashboard.app.get("/api/monitoring/events")
        async def get_monitoring_events(limit: int = 50):
            """Get monitoring events"""
            try:
                return {"events": self.monitoring_system.get_recent_events(limit)}
            except Exception as e:
                logger.error(f"Failed to get monitoring events: {e}")
                return {"error": str(e)}
        
        @self.web_dashboard.app.get("/api/monitoring/alerts")
        async def get_monitoring_alerts(limit: int = 20):
            """Get monitoring alerts"""
            try:
                return {"alerts": self.monitoring_system.get_recent_alerts(limit)}
            except Exception as e:
                logger.error(f"Failed to get monitoring alerts: {e}")
                return {"error": str(e)}
        
        @self.web_dashboard.app.get("/api/monitoring/status")
        async def get_monitoring_status():
            """Get monitoring status"""
            try:
                return self.monitoring_system.get_system_status()
            except Exception as e:
                logger.error(f"Failed to get monitoring status: {e}")
                return {"error": str(e)}
        
        @self.web_dashboard.app.post("/api/monitoring/acknowledge")
        async def acknowledge_monitoring_event(event_id: str):
            """Acknowledge monitoring event"""
            try:
                success = self.monitoring_system.acknowledge_event(event_id)
                return {"success": success}
            except Exception as e:
                logger.error(f"Failed to acknowledge event: {e}")
                return {"success": False, "error": str(e)}
        
        @self.web_dashboard.app.post("/api/monitoring/clear")
        
        async def clear_monitoring_events(older_than_hours: int = 24):
            """Clear monitoring events"""
            try:
                cleared_count = self.monitoring_system.clear_events(older_than_hours)
                return {"cleared_count": cleared_count}
            except Exception as e:
                logger.error(f"Failed to clear events: {e}")
                return {"error": str(e)}
    
    async def cleanup(self):
        """Cleanup resources"""
        try:
            # Stop monitoring system
            await self.monitoring_system.stop_monitoring()
            
            logger.info("Dashboard cleanup completed")
            
        except Exception as e:
            logger.error(f"Failed to cleanup: {e}")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='JARVIS Codebase Dashboard')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8090, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Create and run dashboard
    dashboard = IntegratedDashboard(
        host=args.host,
        port=args.port,
        debug=args.debug
    )
    
    # Run with asyncio
    try:
        asyncio.run(dashboard.run())
    except KeyboardInterrupt:
        logger.info("Dashboard stopped by user")
    except Exception as e:
        logger.error(f"Dashboard failed: {e}")
        raise


if __name__ == "__main__":
    main()
