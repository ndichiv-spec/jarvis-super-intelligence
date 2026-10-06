"""
JARVIS Architecture Visualizer
=============================
Interactive architecture visualization for JARVIS codebase with advanced
graph layouts, filtering, and real-time updates.

Features:
- Interactive graph visualization
- Multiple layout algorithms
- Component filtering and search
- Real-time updates
- Dependency mapping
- Performance metrics visualization
- Export capabilities
- 3D visualization support
"""

import asyncio
import json
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid
import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)


class LayoutAlgorithm(Enum):
    """Layout algorithm enumeration"""
    FORCE_DIRECTED = "force_directed"
    HIERARCHICAL = "hierarchical"
    CIRCULAR = "circular"
    GRID = "grid"
    SPRING = "spring"
    KAMADA_KAWAI = "kamada_kawai"
    SPECTRAL = "spectral"
    SHELL = "shell"
    RANDOM = "random"
    CUSTOM = "custom"


class VisualizationMode(Enum):
    """Visualization mode enumeration"""
    DEPENDENCY_GRAPH = "dependency_graph"
    COMPONENT_MAP = "component_map"
    ARCHITECTURE_LAYERS = "architecture_layers"
    DATA_FLOW = "data_flow"
    CALL_GRAPH = "call_graph"
    MODULE_VIEW = "module_view"
    3D_VIEW = "3d_view"


@dataclass
class VisualizationNode:
    """Visualization node data structure"""
    id: str
    label: str
    type: str
    level: int
    position: Dict[str, float] = field(default_factory=dict)
    velocity: Dict[str, float] = field(default_factory=dict)
    force: Dict[str, float] = field(default_factory=dict)
    color: str = "#3498db"
    size: float = 20.0
    shape: str = "dot"
    border_width: float = 1.0
    border_color: str = "#2c3e50"
    font_size: float = 12.0
    font_color: str = "#2c3e50"
    opacity: float = 1.0
    visible: bool = True
    selected: bool = False
    highlighted: bool = False
    metrics: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VisualizationEdge:
    """Visualization edge data structure"""
    id: str
    source: str
    target: str
    type: str
    width: float = 1.0
    color: str = "#95a5a6"
    style: str = "solid"  # solid, dashed, dotted
    opacity: float = 0.8
    visible: bool = True
    selected: bool = False
    highlighted: bool = False
    label: str = ""
    font_size: float = 10.0
    font_color: str = "#7f8c8d"
    arrows: str = "to"  # to, from, both, none
    length: float = 100.0
    strength: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VisualizationLayout:
    """Visualization layout configuration"""
    algorithm: LayoutAlgorithm = LayoutAlgorithm.FORCE_DIRECTED
    width: float = 1200.0
    height: float = 800.0
    padding: float = 50.0
    node_spacing: float = 100.0
    level_spacing: float = 150.0
    iterations: int = 1000
    gravity: float = 0.1
    repulsion: float = 1000.0
    attraction: float = 0.01
    damping: float = 0.9
    min_velocity: float = 0.01
    max_velocity: float = 10.0


class ArchitectureVisualizer:
    """Advanced architecture visualizer for JARVIS codebase"""
    
    def __init__(self):
        self.nodes: Dict[str, VisualizationNode] = {}
        self.edges: Dict[str, VisualizationEdge] = {}
        self.graph = nx.DiGraph()
        
        # Visualization configuration
        self.layout = VisualizationLayout()
        self.mode = VisualizationMode.DEPENDENCY_GRAPH
        
        # Visualization state
        self.selected_nodes: List[str] = []
        self.highlighted_nodes: List[str] = []
        self.filtered_types: List[str] = []
        self.search_query: str = ""
        
        # Performance metrics
        self.render_time: float = 0.0
        self.node_count: int = 0
        self.edge_count: int = 0
        self.update_frequency: float = 30.0  # seconds
        
        # Color schemes
        self.color_schemes = {
            'component_type': {
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
                'quantum': '#9b59b6',
                'database': '#2c3e50',
                'cache': '#f1c40f',
                'queue': '#e67e22',
                'auth': '#3498db',
                'authorization': '#e74c3c'
            },
            'complexity': {
                'low': '#2ecc71',
                'medium': '#f39c12',
                'high': '#e67e22',
                'critical': '#e74c3c'
            },
            'performance': {
                'excellent': '#2ecc71',
                'good': '#3498db',
                'average': '#f39c12',
                'poor': '#e67e22',
                'critical': '#e74c3c'
            }
        }
    
    def load_graph(self, nodes_data: List[Dict[str, Any]], edges_data: List[Dict[str, Any]]):
        """Load graph data from documentation system"""
        try:
            # Clear existing data
            self.nodes.clear()
            self.edges.clear()
            self.graph.clear()
            
            # Load nodes
            for node_data in nodes_data:
                node = VisualizationNode(
                    id=node_data['id'],
                    label=node_data['name'],
                    type=node_data['type'],
                    level=node_data.get('level', 0),
                    color=self._get_node_color(node_data['type']),
                    size=self._get_node_size(node_data),
                    metrics=node_data.get('metrics', {}),
                    metadata=node_data
                )
                
                self.nodes[node.id] = node
                self.graph.add_node(node.id, **node_data)
            
            # Load edges
            for edge_data in edges_data:
                edge = VisualizationEdge(
                    id=f"{edge_data['source']}-{edge_data['target']}",
                    source=edge_data['source'],
                    target=edge_data['target'],
                    type=edge_data.get('type', 'dependency'),
                    color=self._get_edge_color(edge_data.get('type', 'dependency')),
                    width=self._get_edge_width(edge_data),
                    metadata=edge_data
                )
                
                self.edges[edge.id] = edge
                self.graph.add_edge(edge.source, edge.target, **edge_data)
            
            # Update counts
            self.node_count = len(self.nodes)
            self.edge_count = len(self.edges)
            
            logger.info(f"Loaded graph: {self.node_count} nodes, {self.edge_count} edges")
            
        except Exception as e:
            logger.error(f"Failed to load graph: {e}")
    
    def _get_node_color(self, node_type: str) -> str:
        """Get node color based on type"""
        return self.color_schemes['component_type'].get(node_type, '#95a5a6')
    
    def _get_node_size(self, node_data: Dict[str, Any]) -> float:
        """Get node size based on metrics"""
        metrics = node_data.get('metrics', {})
        
        # Base size
        size = 20.0
        
        # Adjust based on lines of code
        lines = metrics.get('lines_of_code', 0)
        if lines > 1000:
            size += 10
        elif lines > 500:
            size += 5
        elif lines > 100:
            size += 2
        
        # Adjust based on complexity
        complexity = metrics.get('complexity_score', 0)
        if complexity > 5:
            size += 8
        elif complexity > 3:
            size += 4
        elif complexity > 1:
            size += 2
        
        return min(size, 50.0)  # Cap at 50
    
    def _get_edge_color(self, edge_type: str) -> str:
        """Get edge color based on type"""
        edge_colors = {
            'dependency': '#95a5a6',
            'import': '#3498db',
            'call': '#2ecc71',
            'data_flow': '#f39c12',
            'inheritance': '#9b59b6',
            'composition': '#e67e22',
            'aggregation': '#1abc9c'
        }
        return edge_colors.get(edge_type, '#95a5a6')
    
    def _get_edge_width(self, edge_data: Dict[str, Any]) -> float:
        """Get edge width based on strength"""
        strength = edge_data.get('strength', 1.0)
        return min(5.0, 1.0 + strength * 2.0)
    
    async def apply_layout(self, algorithm: LayoutAlgorithm = None):
        """Apply layout algorithm to graph"""
        try:
            start_time = datetime.now()
            
            # Use specified algorithm or default
            algo = algorithm or self.layout.algorithm
            
            # Filter visible nodes
            visible_nodes = [n for n in self.nodes.values() if n.visible]
            visible_node_ids = [n.id for n in visible_nodes]
            
            if not visible_node_ids:
                return
            
            # Create subgraph with visible nodes
            subgraph = self.graph.subgraph(visible_node_ids)
            
            # Apply layout
            positions = await self._calculate_layout(subgraph, algo)
            
            # Update node positions
            for node_id, pos in positions.items():
                if node_id in self.nodes:
                    node = self.nodes[node_id]
                    node.position = {'x': pos[0], 'y': pos[1]}
            
            # Calculate render time
            self.render_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"Applied {algo.value} layout in {self.render_time:.3f}s")
            
        except Exception as e:
            logger.error(f"Failed to apply layout: {e}")
    
    async def _calculate_layout(self, graph: nx.Graph, algorithm: LayoutAlgorithm) -> Dict[str, Tuple[float, float]]:
        """Calculate node positions using specified algorithm"""
        try:
            if algorithm == LayoutAlgorithm.FORCE_DIRECTED:
                return await self._force_directed_layout(graph)
            elif algorithm == LayoutAlgorithm.HIERARCHICAL:
                return await self._hierarchical_layout(graph)
            elif algorithm == LayoutAlgorithm.CIRCULAR:
                return await self._circular_layout(graph)
            elif algorithm == LayoutAlgorithm.GRID:
                return await self._grid_layout(graph)
            elif algorithm == LayoutAlgorithm.SPRING:
                return nx.spring_layout(graph, k=self.layout.node_spacing / 1000, iterations=self.layout.iterations)
            elif algorithm == LayoutAlgorithm.KAMADA_KAWAI:
                return nx.kamada_kawai_layout(graph)
            elif algorithm == LayoutAlgorithm.SPECTRAL:
                return nx.spectral_layout(graph)
            elif algorithm == LayoutAlgorithm.SHELL:
                return nx.shell_layout(graph)
            elif algorithm == LayoutAlgorithm.RANDOM:
                return nx.random_layout(graph)
            else:
                return await self._force_directed_layout(graph)
        
        except Exception as e:
            logger.error(f"Layout calculation failed: {e}")
            # Fallback to simple layout
            return await self._simple_layout(graph)
    
    async def _force_directed_layout(self, graph: nx.Graph) -> Dict[str, Tuple[float, float]]:
        """Force-directed layout algorithm"""
        # Initialize positions
        positions = {}
        for node in graph.nodes():
            positions[node] = (
                np.random.uniform(0, self.layout.width),
                np.random.uniform(0, self.layout.height)
            )
        
        # Force-directed simulation
        for iteration in range(self.layout.iterations):
            # Calculate forces
            forces = {node: [0.0, 0.0] for node in graph.nodes()}
            
            # Repulsion between all nodes
            for node1 in graph.nodes():
                for node2 in graph.nodes():
                    if node1 != node2:
                        dx = positions[node2][0] - positions[node1][0]
                        dy = positions[node2][1] - positions[node1][1]
                        distance = math.sqrt(dx**2 + dy**2)
                        
                        if distance > 0:
                            # Repulsion force
                            force = self.layout.repulsion / (distance**2)
                            forces[node1][0] -= force * dx / distance
                            forces[node1][1] -= force * dy / distance
            
            # Attraction along edges
            for edge in graph.edges():
                node1, node2 = edge
                dx = positions[node2][0] - positions[node1][0]
                dy = positions[node2][1] - positions[node1][1]
                distance = math.sqrt(dx**2 + dy**2)
                
                if distance > 0:
                    # Attraction force
                    force = self.layout.attraction * distance
                    forces[node1][0] += force * dx / distance
                    forces[node1][1] += force * dy / distance
                    forces[node2][0] -= force * dx / distance
                    forces[node2][1] -= force * dy / distance
            
            # Update positions
            for node in graph.nodes():
                # Apply damping
                forces[node][0] *= self.layout.damping
                forces[node][1] *= self.layout.damping
                
                # Limit velocity
                velocity = math.sqrt(forces[node][0]**2 + forces[node][1]**2)
                if velocity > self.layout.max_velocity:
                    forces[node][0] = forces[node][0] / velocity * self.layout.max_velocity
                    forces[node][1] = forces[node][1] / velocity * self.layout.max_velocity
                
                # Update position
                positions[node] = (
                    positions[node][0] + forces[node][0],
                    positions[node][1] + forces[node][1]
                )
                
                # Keep within bounds
                positions[node] = (
                    max(self.layout.padding, min(self.layout.width - self.layout.padding, positions[node][0])),
                    max(self.layout.padding, min(self.layout.height - self.layout.padding, positions[node][1]))
                )
        
        return positions
    
    async def _hierarchical_layout(self, graph: nx.Graph) -> Dict[str, Tuple[float, float]]:
        """Hierarchical layout algorithm"""
        # Group nodes by level
        levels = {}
        max_level = 0
        
        for node in graph.nodes():
            if node in self.nodes:
                level = self.nodes[node].level
                levels.setdefault(level, []).append(node)
                max_level = max(max_level, level)
        
        positions = {}
        level_height = (self.layout.height - 2 * self.layout.padding) / (max_level + 1)
        
        for level, nodes in levels.items():
            # Calculate positions for this level
            level_width = self.layout.width - 2 * self.layout.padding
            node_width = level_width / len(nodes)
            
            for i, node in enumerate(nodes):
                x = self.layout.padding + i * node_width + node_width / 2
                y = self.layout.padding + level * level_height + level_height / 2
                positions[node] = (x, y)
        
        return positions
    
    async def _circular_layout(self, graph: nx.Graph) -> Dict[str, Tuple[float, float]]:
        """Circular layout algorithm"""
        positions = {}
        center_x = self.layout.width / 2
        center_y = self.layout.height / 2
        radius = min(center_x, center_y) - self.layout.padding
        
        nodes = list(graph.nodes())
        angle_step = 2 * math.pi / len(nodes)
        
        for i, node in enumerate(nodes):
            angle = i * angle_step
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            positions[node] = (x, y)
        
        return positions
    
    async def _grid_layout(self, graph: nx.Graph) -> Dict[str, Tuple[float, float]]:
        """Grid layout algorithm"""
        positions = {}
        nodes = list(graph.nodes())
        
        # Calculate grid dimensions
        grid_size = math.ceil(math.sqrt(len(nodes)))
        cell_width = (self.layout.width - 2 * self.layout.padding) / grid_size
        cell_height = (self.layout.height - 2 * self.layout.padding) / grid_size
        
        for i, node in enumerate(nodes):
            row = i // grid_size
            col = i % grid_size
            x = self.layout.padding + col * cell_width + cell_width / 2
            y = self.layout.padding + row * cell_height + cell_height / 2
            positions[node] = (x, y)
        
        return positions
    
    async def _simple_layout(self, graph: nx.Graph) -> Dict[str, Tuple[float, float]]:
        """Simple fallback layout"""
        positions = {}
        nodes = list(graph.nodes())
        
        for i, node in enumerate(nodes):
            x = self.layout.padding + (i % 10) * 100
            y = self.layout.padding + (i // 10) * 100
            positions[node] = (x, y)
        
        return positions
    
    def filter_nodes(self, node_types: List[str] = None, search_query: str = None):
        """Filter nodes by type and search query"""
        try:
            # Reset visibility
            for node in self.nodes.values():
                node.visible = True
                node.highlighted = False
            
            for edge in self.edges.values():
                edge.visible = True
                edge.highlighted = False
            
            # Filter by type
            if node_types:
                for node in self.nodes.values():
                    if node.type not in node_types:
                        node.visible = False
            
            # Filter by search query
            if search_query:
                query_lower = search_query.lower()
                for node in self.nodes.values():
                    if (query_lower not in node.label.lower() and 
                        query_lower not in node.type.lower()):
                        node.visible = False
                    else:
                        node.highlighted = True
            
            # Update edge visibility based on node visibility
            for edge in self.edges.values():
                source_visible = edge.source in self.nodes and self.nodes[edge.source].visible
                target_visible = edge.target in self.nodes and self.nodes[edge.target].visible
                
                edge.visible = source_visible and target_visible
                
                # Highlight edges connected to highlighted nodes
                if (edge.source in self.nodes and self.nodes[edge.source].highlighted) or \
                   (edge.target in self.nodes and self.nodes[edge.target].highlighted):
                    edge.highlighted = True
            
            # Store filter state
            self.filtered_types = node_types or []
            self.search_query = search_query or ""
            
            logger.info(f"Filtered nodes: {len([n for n in self.nodes.values() if n.visible])} visible")
            
        except Exception as e:
            logger.error(f"Failed to filter nodes: {e}")
    
    def select_nodes(self, node_ids: List[str]):
        """Select nodes for detailed view"""
        try:
            # Clear previous selection
            for node in self.nodes.values():
                node.selected = False
            
            for edge in self.edges.values():
                edge.selected = False
            
            # Select new nodes
            for node_id in node_ids:
                if node_id in self.nodes:
                    self.nodes[node_id].selected = True
            
            # Select connected edges
            for edge in self.edges.values():
                if edge.source in node_ids or edge.target in node_ids:
                    edge.selected = True
            
            self.selected_nodes = node_ids
            
            logger.info(f"Selected {len(node_ids)} nodes")
            
        except Exception as e:
            logger.error(f"Failed to select nodes: {e}")
    
    def get_subgraph(self, center_node: str, depth: int = 2) -> Dict[str, Any]:
        """Get subgraph centered on a specific node"""
        try:
            if center_node not in self.nodes:
                return {"error": "Node not found"}
            
            # Get nodes within specified depth
            subgraph_nodes = {center_node}
            current_nodes = {center_node}
            
            for d in range(depth):
                next_nodes = set()
                for node in current_nodes:
                    # Get neighbors
                    neighbors = set(self.graph.neighbors(node))
                    neighbors.update(self.graph.predecessors(node))
                    next_nodes.update(neighbors)
                
                subgraph_nodes.update(next_nodes)
                current_nodes = next_nodes
            
            # Get edges between these nodes
            subgraph_edges = []
            for edge in self.edges.values():
                if edge.source in subgraph_nodes and edge.target in subgraph_nodes:
                    subgraph_edges.append(edge.id)
            
            return {
                "center_node": center_node,
                "depth": depth,
                "nodes": list(subgraph_nodes),
                "edges": subgraph_edges,
                "total_nodes": len(subgraph_nodes),
                "total_edges": len(subgraph_edges)
            }
            
        except Exception as e:
            logger.error(f"Failed to get subgraph: {e}")
            return {"error": str(e)}
    
    def get_visualization_data(self) -> Dict[str, Any]:
        """Get current visualization data for rendering"""
        try:
            # Get visible nodes
            visible_nodes = []
            for node in self.nodes.values():
                if node.visible:
                    visible_nodes.append({
                        "id": node.id,
                        "label": node.label,
                        "type": node.type,
                        "level": node.level,
                        "x": node.position.get("x", 0),
                        "y": node.position.get("y", 0),
                        "color": node.color,
                        "size": node.size,
                        "shape": node.shape,
                        "selected": node.selected,
                        "highlighted": node.highlighted,
                        "metrics": node.metrics
                    })
            
            # Get visible edges
            visible_edges = []
            for edge in self.edges.values():
                if edge.visible:
                    source_pos = self.nodes[edge.source].position if edge.source in self.nodes else {"x": 0, "y": 0}
                    target_pos = self.nodes[edge.target].position if edge.target in self.nodes else {"x": 0, "y": 0}
                    
                    visible_edges.append({
                        "id": edge.id,
                        "source": edge.source,
                        "target": edge.target,
                        "type": edge.type,
                        "source_x": source_pos.get("x", 0),
                        "source_y": source_pos.get("y", 0),
                        "target_x": target_pos.get("x", 0),
                        "target_y": target_pos.get("y", 0),
                        "color": edge.color,
                        "width": edge.width,
                        "style": edge.style,
                        "selected": edge.selected,
                        "highlighted": edge.highlighted
                    })
            
            return {
                "nodes": visible_nodes,
                "edges": visible_edges,
                "layout": {
                    "algorithm": self.layout.algorithm.value,
                    "width": self.layout.width,
                    "height": self.layout.height
                },
                "mode": self.mode.value,
                "stats": {
                    "total_nodes": self.node_count,
                    "visible_nodes": len(visible_nodes),
                    "total_edges": self.edge_count,
                    "visible_edges": len(visible_edges),
                    "render_time": self.render_time,
                    "selected_nodes": len(self.selected_nodes)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get visualization data: {e}")
            return {"error": str(e)}
    
    def get_node_details(self, node_id: str) -> Dict[str, Any]:
        """Get detailed information about a node"""
        try:
            if node_id not in self.nodes:
                return {"error": "Node not found"}
            
            node = self.nodes[node_id]
            
            # Get connected nodes
            neighbors = list(self.graph.neighbors(node_id))
            predecessors = list(self.graph.predecessors(node_id))
            
            # Get connected edges
            connected_edges = []
            for edge in self.edges.values():
                if edge.source == node_id or edge.target == node_id:
                    connected_edges.append(edge.id)
            
            # Calculate additional metrics
            degree = self.graph.degree(node_id)
            in_degree = self.graph.in_degree(node_id)
            out_degree = self.graph.out_degree(node_id)
            
            return {
                "id": node.id,
                "label": node.label,
                "type": node.type,
                "level": node.level,
                "position": node.position,
                "metrics": node.metrics,
                "metadata": node.metadata,
                "connections": {
                    "neighbors": neighbors,
                    "predecessors": predecessors,
                    "degree": degree,
                    "in_degree": in_degree,
                    "out_degree": out_degree
                },
                "edges": connected_edges
            }
            
        except Exception as e:
            logger.error(f"Failed to get node details: {e}")
            return {"error": str(e)}
    
    def export_visualization(self, format: str = "json") -> Dict[str, Any]:
        """Export visualization data"""
        try:
            data = self.get_visualization_data()
            
            if format == "json":
                return data
            elif format == "graphml":
                # Export as GraphML
                return {"graphml": nx.to_graphml(self.graph)}
            elif format == "gexf":
                # Export as GEXF
                return {"gexf": nx.to_gexf(self.graph)}
            else:
                return {"error": "Unsupported format"}
                
        except Exception as e:
            logger.error(f"Failed to export visualization: {e}")
            return {"error": str(e)}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get visualization statistics"""
        try:
            # Graph statistics
            graph_stats = {
                "nodes": self.graph.number_of_nodes(),
                "edges": self.graph.number_of_edges(),
                "density": nx.density(self.graph),
                "is_connected": nx.is_connected(self.graph.to_undirected()),
                "is_dag": nx.is_directed_acyclic_graph(self.graph)
            }
            
            # Component statistics
            component_stats = {}
            for node_type, nodes in self.color_schemes['component_type'].items():
                count = len([n for n in self.nodes.values() if n.type == node_type])
                if count > 0:
                    component_stats[node_type] = count
            
            # Performance statistics
            performance_stats = {
                "render_time": self.render_time,
                "update_frequency": self.update_frequency,
                "visible_nodes": len([n for n in self.nodes.values() if n.visible]),
                "visible_edges": len([e for e in self.edges.values() if e.visible]),
                "selected_nodes": len(self.selected_nodes)
            }
            
            return {
                "graph": graph_stats,
                "components": component_stats,
                "performance": performance_stats,
                "layout": {
                    "algorithm": self.layout.algorithm.value,
                    "width": self.layout.width,
                    "height": self.layout.height
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {"error": str(e)}


# Global instance
_architecture_visualizer = None


def get_architecture_visualizer() -> ArchitectureVisualizer:
    """Get global architecture visualizer instance"""
    global _architecture_visualizer
    if _architecture_visualizer is None:
        _architecture_visualizer = ArchitectureVisualizer()
    return _architecture_visualizer
