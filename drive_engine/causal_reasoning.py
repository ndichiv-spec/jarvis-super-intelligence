"""
JARVIS Causal Reasoning Engine
===============================
Deeper understanding of cause-and-effect relationships and counterfactual analysis.
"""

import asyncio
import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class CausalRelationType(Enum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    CONFOUNDING = "confounding"
    MEDIATING = "mediating"

@dataclass
class CausalNode:
    id: str
    name: str
    type: str
    value: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CausalEdge:
    source: str
    target: str
    relation_type: CausalRelationType
    strength: float
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CounterfactualScenario:
    original_state: Dict[str, Any]
    intervention: Dict[str, Any]
    predicted_outcome: Dict[str, Any]
    confidence: float
    explanation: str

class CausalReasoningEngine:
    """Advanced causal reasoning engine with counterfactual analysis"""
    
    def __init__(self):
        self.causal_graph: Dict[str, CausalNode] = {}
        self.causal_edges: List[CausalEdge] = []
        self.counterfactual_history: List[CounterfactualScenario] = []
        self.reasoning_metrics = {
            "total_inferences": 0,
            "successful_inferences": 0,
            "counterfactual_analyses": 0,
            "avg_confidence": 0.0
        }
    
    async def initialize(self):
        """Initialize causal reasoning engine"""
        logger.info("Initializing Causal Reasoning Engine")
        # Initialize with basic causal structure
        self._initialize_basic_graph()
    
    def _initialize_basic_graph(self):
        """Initialize basic causal graph structure"""
        # Create some example nodes
        nodes = [
            CausalNode("system_load", "System Load", "metric"),
            CausalNode("response_time", "Response Time", "metric"),
            CausalNode("user_satisfaction", "User Satisfaction", "metric"),
            CausalNode("error_rate", "Error Rate", "metric"),
            CausalNode("resource_allocation", "Resource Allocation", "control")
        ]
        
        for node in nodes:
            self.causal_graph[node.id] = node
        
        # Create causal relationships
        edges = [
            CausalEdge("system_load", "response_time", CausalRelationType.DIRECT, 0.8, 0.9),
            CausalEdge("response_time", "user_satisfaction", CausalRelationType.DIRECT, -0.7, 0.85),
            CausalEdge("error_rate", "user_satisfaction", CausalRelationType.DIRECT, -0.9, 0.95),
            CausalEdge("resource_allocation", "system_load", CausalRelationType.DIRECT, -0.6, 0.8),
            CausalEdge("resource_allocation", "error_rate", CausalRelationType.DIRECT, -0.5, 0.75)
        ]
        
        self.causal_edges = edges
    
    async def infer_causal_effect(self, cause: str, effect: str, 
                                  intervention: Dict[str, Any]) -> Dict[str, Any]:
        """Infer causal effect of intervention"""
        self.reasoning_metrics["total_inferences"] += 1
        
        try:
            # Find causal path
            path = self._find_causal_path(cause, effect)
            
            if not path:
                return {
                    "success": False,
                    "error": "No causal path found",
                    "confidence": 0.0
                }
            
            # Calculate effect strength
            effect_strength = self._calculate_effect_strength(path, intervention)
            
            # Generate explanation
            explanation = self._generate_causal_explanation(path, intervention, effect_strength)
            
            self.reasoning_metrics["successful_inferences"] += 1
            confidence = min(0.95, 0.7 + len(path) * 0.05)
            
            self.reasoning_metrics["avg_confidence"] = (
                (self.reasoning_metrics["avg_confidence"] * (self.reasoning_metrics["successful_inferences"] - 1) + confidence) /
                self.reasoning_metrics["successful_inferences"]
            )
            
            return {
                "success": True,
                "cause": cause,
                "effect": effect,
                "intervention": intervention,
                "causal_path": path,
                "predicted_effect": effect_strength,
                "confidence": confidence,
                "explanation": explanation
            }
            
        except Exception as e:
            logger.error(f"Causal inference error: {e}")
            return {
                "success": False,
                "error": str(e),
                "confidence": 0.0
            }
    
    def _find_causal_path(self, source: str, target: str) -> List[str]:
        """Find causal path from source to target using BFS"""
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
            
            # Find all edges from current node
            for edge in self.causal_edges:
                if edge.source == current:
                    queue.append((edge.target, path + [edge.target]))
        
        return []
    
    def _calculate_effect_strength(self, path: List[str], 
                                   intervention: Dict[str, Any]) -> float:
        """Calculate effect strength along causal path"""
        total_strength = 1.0
        
        for i in range(len(path) - 1):
            source = path[i]
            target = path[i + 1]
            
            # Find edge between these nodes
            for edge in self.causal_edges:
                if edge.source == source and edge.target == target:
                    total_strength *= edge.strength
                    break
        
        # Apply intervention magnitude
        intervention_magnitude = intervention.get("magnitude", 1.0)
        return total_strength * intervention_magnitude
    
    def _generate_causal_explanation(self, path: List[str], 
                                      intervention: Dict[str, Any],
                                      effect_strength: float) -> str:
        """Generate human-readable causal explanation"""
        if len(path) < 2:
            return "No causal relationship found"
        
        explanation = f"Intervention on {path[0]} "
        
        for i in range(len(path) - 1):
            explanation += f"affects {path[i+1]} "
            if i < len(path) - 2:
                explanation += "which in turn "
        
        explanation += f"with an estimated effect strength of {effect_strength:.2f}"
        
        return explanation
    
    async def analyze_counterfactual(self, original_state: Dict[str, Any],
                                    intervention: Dict[str, Any]) -> CounterfactualScenario:
        """Analyze counterfactual scenario"""
        self.reasoning_metrics["counterfactual_analyses"] += 1
        
        try:
            # Determine what would have happened with intervention
            predicted_outcome = {}
            
            for key, value in original_state.items():
                if key in intervention:
                    # Apply intervention
                    predicted_outcome[key] = intervention[key]
                else:
                    # Estimate effect through causal relationships
                    affected_value = self._estimate_counterfactual_effect(
                        key, original_state, intervention
                    )
                    predicted_outcome[key] = affected_value
            
            # Generate explanation
            explanation = self._generate_counterfactual_explanation(
                original_state, intervention, predicted_outcome
            )
            
            # Calculate confidence
            confidence = 0.8  # Base confidence for counterfactuals
            
            scenario = CounterfactualScenario(
                original_state=original_state,
                intervention=intervention,
                predicted_outcome=predicted_outcome,
                confidence=confidence,
                explanation=explanation
            )
            
            self.counterfactual_history.append(scenario)
            return scenario
            
        except Exception as e:
            logger.error(f"Counterfactual analysis error: {e}")
            return CounterfactualScenario(
                original_state=original_state,
                intervention=intervention,
                predicted_outcome={},
                confidence=0.0,
                explanation=f"Analysis failed: {str(e)}"
            )
    
    def _estimate_counterfactual_effect(self, variable: str,
                                        original_state: Dict[str, Any],
                                        intervention: Dict[str, Any]) -> Any:
        """Estimate effect of intervention on variable"""
        # Find all causal paths to this variable
        affected_variables = []
        
        for edge in self.causal_edges:
            if edge.target == variable and edge.source in intervention:
                affected_variables.append(edge.source)
        
        if not affected_variables:
            return original_state.get(variable)
        
        # Calculate combined effect
        original_value = original_state.get(variable, 0)
        total_effect = 0.0
        
        for source in affected_variables:
            intervention_value = intervention[source]
            original_source_value = original_state.get(source, 0)
            
            # Find edge strength
            for edge in self.causal_edges:
                if edge.source == source and edge.target == variable:
                    effect = (intervention_value - original_source_value) * edge.strength
                    total_effect += effect
                    break
        
        return original_value + total_effect
    
    def _generate_counterfactual_explanation(self, original_state: Dict[str, Any],
                                           intervention: Dict[str, Any],
                                           predicted_outcome: Dict[str, Any]) -> str:
        """Generate counterfactual explanation"""
        explanation = "Counterfactual analysis: "
        
        for key, value in intervention.items():
            original_value = original_state.get(key, "unknown")
            explanation += f"If {key} were changed from {original_value} to {value}, "
        
        explanation += "the predicted outcomes would be: "
        
        for key, value in predicted_outcome.items():
            if key in intervention:
                continue
            original_value = original_state.get(key, "unknown")
            if abs(value - original_value) > 0.01:  # Only mention significant changes
                explanation += f"{key} would change from {original_value} to {value:.2f}, "
        
        return explanation.rstrip(", ")
    
    def get_causal_graph(self) -> Dict[str, Any]:
        """Get current causal graph structure"""
        return {
            "nodes": [
                {
                    "id": node.id,
                    "name": node.name,
                    "type": node.type,
                    "value": node.value,
                    "metadata": node.metadata
                }
                for node in self.causal_graph.values()
            ],
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "relation_type": edge.relation_type.value,
                    "strength": edge.strength,
                    "confidence": edge.confidence
                }
                for edge in self.causal_edges
            ]
        }
    
    def get_reasoning_status(self) -> Dict[str, Any]:
        """Get reasoning engine status"""
        return {
            "nodes_count": len(self.causal_graph),
            "edges_count": len(self.causal_edges),
            "counterfactual_analyses": len(self.counterfactual_history),
            "metrics": self.reasoning_metrics,
            "system_health": "operational"
        }

# Global causal reasoning instance
causal_reasoning: Optional[CausalReasoningEngine] = None

def get_causal_reasoning() -> CausalReasoningEngine:
    """Get or create causal reasoning instance"""
    global causal_reasoning
    if causal_reasoning is None:
        causal_reasoning = CausalReasoningEngine()
    return causal_reasoning
