"""
JARVIS Advanced Memory and Knowledge Graph
==========================================
Comprehensive memory system with knowledge graph for persistent learning and reasoning.
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class MemoryType(Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    WORKING = "working"

class RelationType(Enum):
    CAUSES = "causes"
    ENABLES = "enables"
    REQUIRES = "requires"
    RELATED_TO = "related_to"
    PART_OF = "part_of"
    INSTANCE_OF = "instance_of"

@dataclass
class Memory:
    id: str
    content: Any
    memory_type: MemoryType
    importance: float
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class KnowledgeNode:
    id: str
    label: str
    node_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None

@dataclass
class KnowledgeEdge:
    source: str
    target: str
    relation: RelationType
    weight: float
    metadata: Dict[str, Any] = field(default_factory=dict)

class AdvancedMemorySystem:
    """Advanced memory system with knowledge graph"""
    
    def __init__(self):
        self.memories: Dict[str, Memory] = {}
        self.knowledge_nodes: Dict[str, KnowledgeNode] = {}
        self.knowledge_edges: List[KnowledgeEdge] = []
        self.memory_counter = 0
        self.node_counter = 0
        self.working_memory: List[str] = []
        self.memory_metrics = {
            "total_memories": 0,
            "total_nodes": 0,
            "total_edges": 0,
            "avg_importance": 0.0,
            "retrieval_count": 0
        }
    
    async def initialize(self):
        """Initialize memory system"""
        logger.info("Initializing Advanced Memory and Knowledge Graph")
        self._initialize_base_knowledge()
    
    def _initialize_base_knowledge(self):
        """Initialize base knowledge graph"""
        # Create base nodes
        nodes = [
            KnowledgeNode("node_1", "JARVIS", "system", {"version": "3.0"}),
            KnowledgeNode("node_2", "Drive Engine", "component", {"status": "active"}),
            KnowledgeNode("node_3", "AI", "capability", {"level": "advanced"}),
            KnowledgeNode("node_4", "Swarm Intelligence", "feature", {"agents": 5}),
            KnowledgeNode("node_5", "Multimodal AI", "feature", {"modalities": 4})
        ]
        
        for node in nodes:
            self.knowledge_nodes[node.id] = node
        
        # Create base edges
        edges = [
            KnowledgeEdge("node_1", "node_2", RelationType.PART_OF, 1.0),
            KnowledgeEdge("node_2", "node_3", RelationType.ENABLES, 0.9),
            KnowledgeEdge("node_3", "node_4", RelationType.RELATED_TO, 0.8),
            KnowledgeEdge("node_3", "node_5", RelationType.RELATED_TO, 0.8)
        ]
        
        self.knowledge_edges = edges
        self.memory_metrics["total_nodes"] = len(self.knowledge_nodes)
        self.memory_metrics["total_edges"] = len(self.knowledge_edges)
    
    async def store_memory(self, content: Any, memory_type: MemoryType,
                          importance: float = 0.5) -> str:
        """Store a new memory"""
        self.memory_counter += 1
        memory_id = f"memory_{self.memory_counter}"
        
        memory = Memory(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            importance=importance
        )
        
        self.memories[memory_id] = memory
        self.memory_metrics["total_memories"] += 1
        
        # Update average importance
        self.memory_metrics["avg_importance"] = (
            (self.memory_metrics["avg_importance"] * 
             (self.memory_metrics["total_memories"] - 1) + importance) /
            self.memory_metrics["total_memories"]
        )
        
        logger.info(f"Stored memory {memory_id} of type {memory_type.value}")
        return memory_id
    
    async def retrieve_memory(self, memory_id: str) -> Optional[Memory]:
        """Retrieve a memory by ID"""
        if memory_id not in self.memories:
            return None
        
        memory = self.memories[memory_id]
        memory.access_count += 1
        memory.last_accessed = time.time()
        self.memory_metrics["retrieval_count"] += 1
        
        return memory
    
    async def search_memories(self, query: str, memory_type: Optional[MemoryType] = None,
                           limit: int = 10) -> List[Memory]:
        """Search memories by content"""
        results = []
        
        for memory in self.memories.values():
            # Filter by memory type if specified
            if memory_type and memory.memory_type != memory_type:
                continue
            
            # Simple text matching (in production, use embeddings)
            content_str = str(memory.content).lower()
            if query.lower() in content_str:
                results.append(memory)
        
        # Sort by importance and access count
        results.sort(key=lambda m: (m.importance, m.access_count), reverse=True)
        
        return results[:limit]
    
    async def add_to_working_memory(self, memory_id: str):
        """Add memory to working memory"""
        if memory_id in self.memories and memory_id not in self.working_memory:
            self.working_memory.append(memory_id)
            # Limit working memory size
            if len(self.working_memory) > 7:  # Miller's magic number
                self.working_memory.pop(0)
    
    async def clear_working_memory(self):
        """Clear working memory"""
        self.working_memory.clear()
    
    async def get_working_memory(self) -> List[Memory]:
        """Get current working memory contents"""
        return [
            self.memories[mid] for mid in self.working_memory
            if mid in self.memories
        ]
    
    async def add_knowledge_node(self, label: str, node_type: str,
                                properties: Dict[str, Any] = None) -> str:
        """Add a node to the knowledge graph"""
        self.node_counter += 1
        node_id = f"node_{self.node_counter}"
        
        node = KnowledgeNode(
            id=node_id,
            label=label,
            node_type=node_type,
            properties=properties or {}
        )
        
        self.knowledge_nodes[node_id] = node
        self.memory_metrics["total_nodes"] += 1
        
        logger.info(f"Added knowledge node {node_id}: {label}")
        return node_id
    
    async def add_knowledge_edge(self, source: str, target: str,
                                relation: RelationType, weight: float = 1.0) -> bool:
        """Add an edge to the knowledge graph"""
        if source not in self.knowledge_nodes or target not in self.knowledge_nodes:
            return False
        
        edge = KnowledgeEdge(
            source=source,
            target=target,
            relation=relation,
            weight=weight
        )
        
        self.knowledge_edges.append(edge)
        self.memory_metrics["total_edges"] += 1
        
        logger.info(f"Added edge {source} -> {target} ({relation.value})")
        return True
    
    async def query_knowledge_graph(self, node_id: str, 
                                   relation: Optional[RelationType] = None,
                                   direction: str = "outgoing") -> List[Dict[str, Any]]:
        """Query knowledge graph starting from a node"""
        if node_id not in self.knowledge_nodes:
            return []
        
        results = []
        
        for edge in self.knowledge_edges:
            if relation and edge.relation != relation:
                continue
            
            if direction == "outgoing" and edge.source == node_id:
                target_node = self.knowledge_nodes[edge.target]
                results.append({
                    "node": target_node,
                    "relation": edge.relation.value,
                    "weight": edge.weight
                })
            elif direction == "incoming" and edge.target == node_id:
                source_node = self.knowledge_nodes[edge.source]
                results.append({
                    "node": source_node,
                    "relation": edge.relation.value,
                    "weight": edge.weight
                })
        
        return results
    
    async def find_path(self, source: str, target: str) -> Optional[List[str]]:
        """Find shortest path between two nodes using BFS"""
        if source not in self.knowledge_nodes or target not in self.knowledge_nodes:
            return None
        
        from collections import deque
        
        queue = deque([(source, [source])])
        visited = set()
        
        while queue:
            current, path = queue.popleft()
            
            if current == target:
                return path
            
            if current in visited:
                continue
            
            visited.add(current)
            
            # Find neighbors
            for edge in self.knowledge_edges:
                if edge.source == current and edge.target not in visited:
                    queue.append((edge.target, path + [edge.target]))
        
        return None
    
    async def consolidate_memories(self):
        """Consolidate and optimize memories"""
        # Remove low-importance memories that haven't been accessed recently
        current_time = time.time()
        memories_to_remove = []
        
        for memory_id, memory in self.memories.items():
            age = current_time - memory.last_accessed
            if age > 86400 and memory.importance < 0.3:  # 24 hours old and low importance
                memories_to_remove.append(memory_id)
        
        for memory_id in memories_to_remove:
            del self.memories[memory_id]
            self.memory_metrics["total_memories"] -= 1
        
        logger.info(f"Consolidated memories, removed {len(memories_to_remove)} old memories")
    
    async def get_memory_status(self) -> Dict[str, Any]:
        """Get memory system status"""
        return {
            "total_memories": len(self.memories),
            "working_memory_size": len(self.working_memory),
            "knowledge_nodes": len(self.knowledge_nodes),
            "knowledge_edges": len(self.knowledge_edges),
            "metrics": self.memory_metrics,
            "memory_types": {
                memory_type.value: len([m for m in self.memories.values() 
                                       if m.memory_type == memory_type])
                for memory_type in MemoryType
            },
            "system_health": "operational"
        }

# Global memory system instance
memory_system: Optional[AdvancedMemorySystem] = None

def get_memory_system() -> AdvancedMemorySystem:
    """Get or create memory system instance"""
    global memory_system
    if memory_system is None:
        memory_system = AdvancedMemorySystem()
    return memory_system
