"""
JARVIS Neuro-Symbolic Integration
==================================
Combines neural networks with symbolic reasoning for more interpretable and reasoning-capable AI.
"""

import asyncio
import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class ReasoningType(Enum):
    DEDUCTIVE = "deductive"
    INDUCTIVE = "inductive"
    ABDUCTIVE = "abductive"
    ANALOGICAL = "analogical"

@dataclass
class SymbolicRule:
    id: str
    name: str
    premises: List[str]
    conclusion: str
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class NeuralPattern:
    id: str
    pattern_type: str
    features: List[float]
    activation_threshold: float
    learned_from: str = "neural_network"

@dataclass
class NeuroSymbolicInference:
    reasoning_type: ReasoningType
    neural_evidence: Dict[str, float]
    symbolic_rules: List[SymbolicRule]
    conclusion: str
    confidence: float
    explanation: str

class NeuroSymbolicIntegration:
    """Neuro-symbolic integration system"""
    
    def __init__(self):
        self.symbolic_rules: List[SymbolicRule] = []
        self.neural_patterns: Dict[str, NeuralPattern] = {}
        self.inference_history: List[NeuroSymbolicInference] = []
        self.integration_metrics = {
            "total_inferences": 0,
            "neural_dominant": 0,
            "symbolic_dominant": 0,
            "hybrid_inferences": 0,
            "avg_confidence": 0.0
        }
    
    async def initialize(self):
        """Initialize neuro-symbolic integration"""
        logger.info("Initializing Neuro-Symbolic Integration")
        self._initialize_default_rules()
        self._initialize_default_patterns()
    
    def _initialize_default_rules(self):
        """Initialize default symbolic rules"""
        self.symbolic_rules = [
            SymbolicRule(
                id="rule_1",
                name="System Load Rule",
                premises=["high_cpu_usage", "high_memory_usage"],
                conclusion="system_overload",
                confidence=0.9
            ),
            SymbolicRule(
                id="rule_2",
                name="Performance Rule",
                premises=["low_response_time", "high_throughput"],
                conclusion="optimal_performance",
                confidence=0.85
            ),
            SymbolicRule(
                id="rule_3",
                name="Error Pattern Rule",
                premises=["frequent_errors", "decreasing_success_rate"],
                conclusion="system_degradation",
                confidence=0.95
            ),
            SymbolicRule(
                id="rule_4",
                name="User Satisfaction Rule",
                premises=["fast_response", "accurate_results"],
                conclusion="high_user_satisfaction",
                confidence=0.88
            )
        ]
    
    def _initialize_default_patterns(self):
        """Initialize default neural patterns"""
        patterns = [
            NeuralPattern(
                id="pattern_1",
                pattern_type="load_spike",
                features=[0.8, 0.9, 0.7, 0.6],
                activation_threshold=0.75
            ),
            NeuralPattern(
                id="pattern_2",
                pattern_type="normal_operation",
                features=[0.3, 0.4, 0.35, 0.3],
                activation_threshold=0.5
            ),
            NeuralPattern(
                id="pattern_3",
                pattern_type="anomaly",
                features=[0.95, 0.92, 0.88, 0.9],
                activation_threshold=0.85
            )
        ]
        
        for pattern in patterns:
            self.neural_patterns[pattern.id] = pattern
    
    async def neural_pattern_matching(self, input_features: List[float]) -> Dict[str, float]:
        """Match input features against neural patterns"""
        pattern_activations = {}
        
        for pattern_id, pattern in self.neural_patterns.items():
            # Calculate pattern similarity (cosine-like)
            similarity = sum(
                a * b for a, b in zip(input_features, pattern.features)
            ) / (len(input_features) ** 0.5)
            
            if similarity >= pattern.activation_threshold:
                pattern_activations[pattern_id] = similarity
        
        return pattern_activations
    
    async def symbolic_reasoning(self, facts: List[str]) -> List[SymbolicRule]:
        """Apply symbolic reasoning to facts"""
        applicable_rules = []
        
        for rule in self.symbolic_rules:
            # Check if all premises are satisfied
            premises_satisfied = all(
                any(fact in premise for premise in rule.premises)
                for fact in facts
            )
            
            if premises_satisfied:
                applicable_rules.append(rule)
        
        return applicable_rules
    
    async def neuro_symbolic_inference(self, input_features: List[float],
                                      facts: List[str],
                                      reasoning_type: ReasoningType) -> NeuroSymbolicInference:
        """Perform neuro-symbolic inference"""
        self.integration_metrics["total_inferences"] += 1
        
        try:
            # Get neural evidence
            neural_evidence = await self.neural_pattern_matching(input_features)
            
            # Get symbolic rules
            symbolic_rules = await self.symbolic_reasoning(facts)
            
            # Combine neural and symbolic evidence
            conclusion, confidence, explanation = await self._combine_evidence(
                neural_evidence, symbolic_rules, reasoning_type
            )
            
            # Determine dominance
            if len(neural_evidence) > len(symbolic_rules):
                self.integration_metrics["neural_dominant"] += 1
            elif len(symbolic_rules) > len(neural_evidence):
                self.integration_metrics["symbolic_dominant"] += 1
            else:
                self.integration_metrics["hybrid_inferences"] += 1
            
            # Update average confidence
            self.integration_metrics["avg_confidence"] = (
                (self.integration_metrics["avg_confidence"] * 
                 (self.integration_metrics["total_inferences"] - 1) + confidence) /
                self.integration_metrics["total_inferences"]
            )
            
            inference = NeuroSymbolicInference(
                reasoning_type=reasoning_type,
                neural_evidence=neural_evidence,
                symbolic_rules=symbolic_rules,
                conclusion=conclusion,
                confidence=confidence,
                explanation=explanation
            )
            
            self.inference_history.append(inference)
            return inference
            
        except Exception as e:
            logger.error(f"Neuro-symbolic inference error: {e}")
            return NeuroSymbolicInference(
                reasoning_type=reasoning_type,
                neural_evidence={},
                symbolic_rules=[],
                conclusion="inference_failed",
                confidence=0.0,
                explanation=f"Inference failed: {str(e)}"
            )
    
    async def _combine_evidence(self, neural_evidence: Dict[str, float],
                               symbolic_rules: List[SymbolicRule],
                               reasoning_type: ReasoningType) -> Tuple[str, float, str]:
        """Combine neural and symbolic evidence"""
        
        if not neural_evidence and not symbolic_rules:
            return "insufficient_evidence", 0.0, "No evidence available"
        
        # Calculate combined confidence
        neural_confidence = sum(neural_evidence.values()) / len(neural_evidence) if neural_evidence else 0
        symbolic_confidence = sum(rule.confidence for rule in symbolic_rules) / len(symbolic_rules) if symbolic_rules else 0
        
        # Weight based on reasoning type
        if reasoning_type == ReasoningType.DEDUCTIVE:
            neural_weight = 0.3
            symbolic_weight = 0.7
        elif reasoning_type == ReasoningType.INDUCTIVE:
            neural_weight = 0.7
            symbolic_weight = 0.3
        else:
            neural_weight = 0.5
            symbolic_weight = 0.5
        
        combined_confidence = (neural_confidence * neural_weight + symbolic_confidence * symbolic_weight)
        
        # Generate conclusion
        if symbolic_rules:
            conclusion = symbolic_rules[0].conclusion
        elif neural_evidence:
            pattern_id = list(neural_evidence.keys())[0]
            pattern = self.neural_patterns[pattern_id]
            conclusion = f"pattern_{pattern.pattern_type}"
        else:
            conclusion = "unknown"
        
        # Generate explanation
        explanation_parts = []
        
        if neural_evidence:
            explanation_parts.append(f"Neural patterns detected: {list(neural_evidence.keys())}")
        
        if symbolic_rules:
            explanation_parts.append(f"Symbolic rules applied: {[rule.name for rule in symbolic_rules]}")
        
        explanation_parts.append(f"Reasoning type: {reasoning_type.value}")
        explanation = ". ".join(explanation_parts)
        
        return conclusion, combined_confidence, explanation
    
    async def learn_new_rule(self, premises: List[str], conclusion: str,
                            confidence: float = 0.8) -> str:
        """Learn a new symbolic rule from neural patterns"""
        rule_id = f"rule_{len(self.symbolic_rules) + 1}"
        
        new_rule = SymbolicRule(
            id=rule_id,
            name=f"Learned Rule {rule_id}",
            premises=premises,
            conclusion=conclusion,
            confidence=confidence
        )
        
        self.symbolic_rules.append(new_rule)
        logger.info(f"Learned new symbolic rule: {rule_id}")
        
        return rule_id
    
    async def extract_symbolic_from_neural(self, pattern_id: str) -> Optional[SymbolicRule]:
        """Extract symbolic rule from neural pattern"""
        if pattern_id not in self.neural_patterns:
            return None
        
        pattern = self.neural_patterns[pattern_id]
        
        # Simulate rule extraction
        rule = SymbolicRule(
            id=f"extracted_{pattern_id}",
            name=f"Extracted from {pattern.pattern_type}",
            premises=[f"feature_{i}" for i in range(len(pattern.features))],
            conclusion=pattern.pattern_type,
            confidence=0.75
        )
        
        return rule
    
    def get_integration_status(self) -> Dict[str, Any]:
        """Get integration system status"""
        return {
            "symbolic_rules_count": len(self.symbolic_rules),
            "neural_patterns_count": len(self.neural_patterns),
            "inference_history_size": len(self.inference_history),
            "metrics": self.integration_metrics,
            "system_health": "operational"
        }

# Global neuro-symbolic instance
neuro_symbolic: Optional[NeuroSymbolicIntegration] = None

def get_neuro_symbolic() -> NeuroSymbolicIntegration:
    """Get or create neuro-symbolic instance"""
    global neuro_symbolic
    if neuro_symbolic is None:
        neuro_symbolic = NeuroSymbolicIntegration()
    return neuro_symbolic
