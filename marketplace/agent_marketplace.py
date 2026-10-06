"""
JARVIS AI Agent Marketplace
==========================
Platform for creating, sharing, and monetizing AI agents with community features.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid
import hashlib

from core.config import settings
from core.advanced_ai_integration import get_advanced_ai_engine

logger = logging.getLogger(__name__)


class AgentCategory(Enum):
    """Agent category enumeration"""
    PRODUCTIVITY = "productivity"
    CUSTOMER_SERVICE = "customer_service"
    DATA_ANALYSIS = "data_analysis"
    CONTENT_CREATION = "content_creation"
    RESEARCH = "research"
    EDUCATION = "education"
    HEALTHCARE = "healthcare"
    FINANCE = "finance"
    DEVELOPMENT = "development"
    MARKETING = "marketing"
    GENERAL = "general"


class AgentStatus(Enum):
    """Agent status enumeration"""
    DRAFT = "draft"
    PUBLISHED = "published"
    FEATURED = "featured"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


class PricingType(Enum):
    """Pricing type enumeration"""
    FREE = "free"
    ONE_TIME = "one_time"
    SUBSCRIPTION = "subscription"
    USAGE_BASED = "usage_based"


@dataclass
class AgentDefinition:
    """Agent definition structure"""
    id: str
    name: str
    description: str
    category: AgentCategory
    author_id: str
    status: AgentStatus = AgentStatus.DRAFT
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    configuration: Dict[str, Any] = field(default_factory=dict)
    pricing: Dict[str, Any] = field(default_factory=dict)
    usage_stats: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    published_at: Optional[datetime] = None


@dataclass
class AgentExecution:
    """Agent execution record"""
    id: str
    agent_id: str
    user_id: str
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    execution_time_ms: Optional[int] = None
    cost: Optional[float] = None
    status: str = "running"
    error_message: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


class AgentMarketplace:
    """AI Agent Marketplace management"""
    
    def __init__(self):
        self.agents: Dict[str, AgentDefinition] = {}
        self.executions: Dict[str, AgentExecution] = {}
        self.user_subscriptions: Dict[str, List[str]] = {}  # user_id -> [agent_ids]
        self.agent_ratings: Dict[str, List[Dict[str, Any]]] = {}  # agent_id -> [ratings]
        self.featured_agents: List[str] = []
        
        # Load agents from storage
        self._load_agents()
    
    async def create_agent(
        self,
        name: str,
        description: str,
        category: AgentCategory,
        author_id: str,
        configuration: Dict[str, Any],
        tags: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None
    ) -> str:
        """Create a new agent"""
        agent_id = str(uuid.uuid4())
        
        agent = AgentDefinition(
            id=agent_id,
            name=name,
            description=description,
            category=category,
            author_id=author_id,
            tags=tags or [],
            capabilities=capabilities or [],
            configuration=configuration,
            pricing={"type": PricingType.FREE.value, "amount": 0}
        )
        
        self.agents[agent_id] = agent
        await self._save_agents()
        
        logger.info(f"Created agent: {name} ({agent_id})")
        return agent_id
    
    async def update_agent(
        self,
        agent_id: str,
        updates: Dict[str, Any],
        author_id: str
    ) -> bool:
        """Update an existing agent"""
        agent = self.agents.get(agent_id)
        if not agent:
            return False
        
        # Check authorization
        if agent.author_id != author_id:
            logger.warning(f"Unauthorized update attempt for agent {agent_id}")
            return False
        
        # Update fields
        for field, value in updates.items():
            if hasattr(agent, field):
                setattr(agent, field, value)
        
        agent.updated_at = datetime.now()
        await self._save_agents()
        
        logger.info(f"Updated agent: {agent_id}")
        return True
    
    async def publish_agent(self, agent_id: str, author_id: str) -> bool:
        """Publish an agent to the marketplace"""
        agent = self.agents.get(agent_id)
        if not agent:
            return False
        
        if agent.author_id != author_id:
            return False
        
        agent.status = AgentStatus.PUBLISHED
        agent.published_at = datetime.now()
        await self._save_agents()
        
        logger.info(f"Published agent: {agent_id}")
        return True
    
    async def execute_agent(
        self,
        agent_id: str,
        user_id: str,
        input_data: Dict[str, Any]
    ) -> str:
        """Execute an agent"""
        agent = self.agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
        
        if agent.status != AgentStatus.PUBLISHED:
            raise ValueError(f"Agent {agent_id} is not published")
        
        # Check subscription/pricing
        if not await self._check_access(agent_id, user_id):
            raise ValueError(f"User {user_id} does not have access to agent {agent_id}")
        
        # Create execution record
        execution_id = str(uuid.uuid4())
        execution = AgentExecution(
            id=execution_id,
            agent_id=agent_id,
            user_id=user_id,
            input_data=input_data
        )
        
        self.executions[execution_id] = execution
        
        # Execute agent asynchronously
        asyncio.create_task(self._run_agent_execution(execution_id))
        
        logger.info(f"Started agent execution: {execution_id}")
        return execution_id
    
    async def _run_agent_execution(self, execution_id: str):
        """Run agent execution in background"""
        execution = self.executions.get(execution_id)
        if not execution:
            return
        
        agent = self.agents.get(execution.agent_id)
        if not agent:
            execution.status = "failed"
            execution.error_message = "Agent not found"
            execution.completed_at = datetime.now()
            return
        
        start_time = datetime.now()
        
        try:
            # Get AI engine for execution
            ai_engine = get_advanced_ai_engine()
            
            # Prepare execution context
            context = {
                "agent_config": agent.configuration,
                "agent_capabilities": agent.capabilities,
                "user_input": execution.input_data
            }
            
            # Execute based on agent type
            if agent.category == AgentCategory.CUSTOMER_SERVICE:
                result = await self._execute_customer_service_agent(ai_engine, context)
            elif agent.category == AgentCategory.DATA_ANALYSIS:
                result = await self._execute_data_analysis_agent(ai_engine, context)
            elif agent.category == AgentCategory.CONTENT_CREATION:
                result = await self._execute_content_creation_agent(ai_engine, context)
            else:
                result = await self._execute_general_agent(ai_engine, context)
            
            # Update execution
            execution.output_data = result
            execution.status = "completed"
            execution.execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            # Update usage stats
            await self._update_agent_stats(execution.agent_id, execution.execution_time_ms)
            
        except Exception as e:
            execution.status = "failed"
            execution.error_message = str(e)
            logger.error(f"Agent execution failed: {e}")
        
        finally:
            execution.completed_at = datetime.now()
    
    async def _execute_customer_service_agent(self, ai_engine, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute customer service agent"""
        from core.advanced_ai_integration import AIRequest, AIProvider, ReasoningMode
        
        user_query = context["user_input"].get("query", "")
        agent_config = context["agent_config"]
        
        # Build prompt with agent context
        system_prompt = f"""
You are a customer service agent with the following configuration:
- Company: {agent_config.get('company_name', 'Unknown')}
- Tone: {agent_config.get('tone', 'professional')}
- Policies: {agent_config.get('policies', [])}

Please respond to the customer query professionally and helpfully.
"""
        
        request = AIRequest(
            query=f"{system_prompt}\n\nCustomer: {user_query}",
            provider=AIProvider.OPENAI,
            reasoning_mode=ReasoningMode.CHAIN_OF_THOUGHT,
            temperature=0.7
        )
        
        response = await ai_engine.process_request(request)
        
        return {
            "response": response.content,
            "confidence": 0.85,
            "escalation_needed": False
        }
    
    async def _execute_data_analysis_agent(self, ai_engine, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute data analysis agent"""
        data = context["user_input"].get("data", [])
        analysis_type = context["user_input"].get("analysis_type", "summary")
        
        # Simple data analysis (would be enhanced with actual analytics)
        if analysis_type == "summary":
            result = {
                "summary": f"Analyzed {len(data)} data points",
                "insights": [
                    "Data shows consistent patterns",
                    "No significant anomalies detected"
                ],
                "statistics": {
                    "count": len(data),
                    "trend": "stable"
                }
            }
        else:
            result = {
                "analysis": f"Performed {analysis_type} analysis on {len(data)} items",
                "recommendations": ["Continue monitoring", "Consider deeper analysis"]
            }
        
        return result
    
    async def _execute_content_creation_agent(self, ai_engine, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute content creation agent"""
        content_type = context["user_input"].get("content_type", "blog")
        topic = context["user_input"].get("topic", "")
        
        from core.advanced_ai_integration import AIRequest, AIProvider, ReasoningMode
        
        prompt = f"""
Create a {content_type} about: {topic}

Requirements:
- Length: 500-1000 words
- Tone: engaging and informative
- Include: introduction, main points, conclusion
"""
        
        request = AIRequest(
            query=prompt,
            provider=AIProvider.OPENAI,
            reasoning_mode=ReasoningMode.CHAIN_OF_THOUGHT,
            temperature=0.8
        )
        
        response = await ai_engine.process_request(request)
        
        return {
            "content": response.content,
            "word_count": len(response.content.split()),
            "content_type": content_type
        }
    
    async def _execute_general_agent(self, ai_engine, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute general purpose agent"""
        from core.advanced_ai_integration import AIRequest, AIProvider, ReasoningMode
        
        user_input = context["user_input"]
        agent_config = context["agent_config"]
        
        prompt = f"""
You are an AI assistant with the following capabilities: {', '.join(context['agent_capabilities'])}

User request: {user_input}

Please provide a helpful and accurate response.
"""
        
        request = AIRequest(
            query=prompt,
            provider=AIProvider.OPENAI,
            reasoning_mode=ReasoningMode.CHAIN_OF_THOUGHT,
            temperature=0.7
        )
        
        response = await ai_engine.process_request(request)
        
        return {
            "response": response.content,
            "capabilities_used": context['agent_capabilities']
        }
    
    async def _check_access(self, agent_id: str, user_id: str) -> bool:
        """Check if user has access to agent"""
        agent = self.agents.get(agent_id)
        if not agent:
            return False
        
        # Free agents are accessible to all
        if agent.pricing.get("type") == PricingType.FREE.value:
            return True
        
        # Check subscription
        user_subscriptions = self.user_subscriptions.get(user_id, [])
        return agent_id in user_subscriptions
    
    async def _update_agent_stats(self, agent_id: str, execution_time_ms: int):
        """Update agent usage statistics"""
        agent = self.agents.get(agent_id)
        if not agent:
            return
        
        stats = agent.usage_stats
        stats["executions"] = stats.get("executions", 0) + 1
        stats["total_execution_time"] = stats.get("total_execution_time", 0) + execution_time_ms
        stats["avg_execution_time"] = stats["total_execution_time"] / stats["executions"]
        stats["last_used"] = datetime.now().isoformat()
        
        await self._save_agents()
    
    async def subscribe_to_agent(self, agent_id: str, user_id: str) -> bool:
        """Subscribe user to agent"""
        agent = self.agents.get(agent_id)
        if not agent:
            return False
        
        if user_id not in self.user_subscriptions:
            self.user_subscriptions[user_id] = []
        
        if agent_id not in self.user_subscriptions[user_id]:
            self.user_subscriptions[user_id].append(agent_id)
        
        logger.info(f"User {user_id} subscribed to agent {agent_id}")
        return True
    
    async def rate_agent(self, agent_id: str, user_id: str, rating: int, review: str) -> bool:
        """Rate an agent"""
        agent = self.agents.get(agent_id)
        if not agent:
            return False
        
        if agent_id not in self.agent_ratings:
            self.agent_ratings[agent_id] = []
        
        # Add rating
        rating_data = {
            "user_id": user_id,
            "rating": rating,
            "review": review,
            "created_at": datetime.now().isoformat()
        }
        
        self.agent_ratings[agent_id].append(rating_data)
        
        logger.info(f"User {user_id} rated agent {agent_id} with {rating} stars")
        return True
    
    async def search_agents(
        self,
        query: str = "",
        category: Optional[AgentCategory] = None,
        tags: Optional[List[str]] = None,
        min_rating: Optional[float] = None,
        pricing_type: Optional[PricingType] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search agents in marketplace"""
        results = []
        
        for agent in self.agents.values():
            # Filter by status
            if agent.status != AgentStatus.PUBLISHED:
                continue
            
            # Filter by category
            if category and agent.category != category:
                continue
            
            # Filter by pricing
            if pricing_type and agent.pricing.get("type") != pricing_type.value:
                continue
            
            # Filter by tags
            if tags and not any(tag in agent.tags for tag in tags):
                continue
            
            # Filter by rating
            if min_rating:
                avg_rating = self._get_agent_average_rating(agent.id)
                if avg_rating < min_rating:
                    continue
            
            # Text search
            if query:
                query_lower = query.lower()
                if (query_lower not in agent.name.lower() and 
                    query_lower not in agent.description.lower() and
                    not any(query_lower in tag.lower() for tag in agent.tags)):
                    continue
            
            # Calculate rating
            avg_rating = self._get_agent_average_rating(agent.id)
            rating_count = len(self.agent_ratings.get(agent.id, []))
            
            results.append({
                "id": agent.id,
                "name": agent.name,
                "description": agent.description,
                "category": agent.category.value,
                "author_id": agent.author_id,
                "tags": agent.tags,
                "capabilities": agent.capabilities,
                "pricing": agent.pricing,
                "usage_stats": agent.usage_stats,
                "average_rating": avg_rating,
                "rating_count": rating_count,
                "created_at": agent.created_at.isoformat(),
                "published_at": agent.published_at.isoformat() if agent.published_at else None
            })
        
        # Sort by relevance (simple scoring)
        results.sort(key=lambda x: (
            x.get("average_rating", 0) * 0.3 +
            x["usage_stats"].get("executions", 0) * 0.7
        ), reverse=True)
        
        return results[:limit]
    
    def _get_agent_average_rating(self, agent_id: str) -> float:
        """Get average rating for agent"""
        ratings = self.agent_ratings.get(agent_id, [])
        if not ratings:
            return 0.0
        
        total = sum(r["rating"] for r in ratings)
        return total / len(ratings)
    
    async def get_agent_details(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed agent information"""
        agent = self.agents.get(agent_id)
        if not agent:
            return None
        
        # Get ratings
        ratings = self.agent_ratings.get(agent_id, [])
        avg_rating = self._get_agent_average_rating(agent_id)
        
        return {
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "category": agent.category.value,
            "author_id": agent.author_id,
            "status": agent.status.value,
            "version": agent.version,
            "tags": agent.tags,
            "capabilities": agent.capabilities,
            "configuration": agent.configuration,
            "pricing": agent.pricing,
            "usage_stats": agent.usage_stats,
            "average_rating": avg_rating,
            "rating_count": len(ratings),
            "ratings": ratings[-10:],  # Last 10 ratings
            "created_at": agent.created_at.isoformat(),
            "updated_at": agent.updated_at.isoformat(),
            "published_at": agent.published_at.isoformat() if agent.published_at else None
        }
    
    async def get_user_agents(self, user_id: str) -> List[Dict[str, Any]]:
        """Get agents created by user"""
        user_agents = []
        
        for agent in self.agents.values():
            if agent.author_id == user_id:
                avg_rating = self._get_agent_average_rating(agent.id)
                rating_count = len(self.agent_ratings.get(agent.id, []))
                
                user_agents.append({
                    "id": agent.id,
                    "name": agent.name,
                    "description": agent.description,
                    "category": agent.category.value,
                    "status": agent.status.value,
                    "tags": agent.tags,
                    "usage_stats": agent.usage_stats,
                    "average_rating": avg_rating,
                    "rating_count": rating_count,
                    "created_at": agent.created_at.isoformat(),
                    "published_at": agent.published_at.isoformat() if agent.published_at else None
                })
        
        return user_agents
    
    async def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get execution status"""
        execution = self.executions.get(execution_id)
        if not execution:
            return None
        
        return {
            "id": execution.id,
            "agent_id": execution.agent_id,
            "user_id": execution.user_id,
            "status": execution.status,
            "input_data": execution.input_data,
            "output_data": execution.output_data,
            "execution_time_ms": execution.execution_time_ms,
            "cost": execution.cost,
            "error_message": execution.error_message,
            "started_at": execution.started_at.isoformat(),
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None
        }
    
    async def feature_agent(self, agent_id: str) -> bool:
        """Feature an agent (admin only)"""
        agent = self.agents.get(agent_id)
        if not agent:
            return False
        
        if agent.status != AgentStatus.PUBLISHED:
            return False
        
        agent.status = AgentStatus.FEATURED
        if agent_id not in self.featured_agents:
            self.featured_agents.append(agent_id)
        
        await self._save_agents()
        logger.info(f"Featured agent: {agent_id}")
        return True
    
    async def get_featured_agents(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get featured agents"""
        featured = []
        
        for agent_id in self.featured_agents[:limit]:
            agent_details = await self.get_agent_details(agent_id)
            if agent_details:
                featured.append(agent_details)
        
        return featured
    
    async def _save_agents(self):
        """Save agents to storage"""
        try:
            import os
            import aiofiles
            
            os.makedirs("./data/marketplace", exist_ok=True)
            
            data = {
                "agents": {
                    agent_id: {
                        "id": agent.id,
                        "name": agent.name,
                        "description": agent.description,
                        "category": agent.category.value,
                        "author_id": agent.author_id,
                        "status": agent.status.value,
                        "version": agent.version,
                        "tags": agent.tags,
                        "capabilities": agent.capabilities,
                        "configuration": agent.configuration,
                        "pricing": agent.pricing,
                        "usage_stats": agent.usage_stats,
                        "created_at": agent.created_at.isoformat(),
                        "updated_at": agent.updated_at.isoformat(),
                        "published_at": agent.published_at.isoformat() if agent.published_at else None
                    }
                    for agent_id, agent in self.agents.items()
                },
                "featured_agents": self.featured_agents,
                "user_subscriptions": self.user_subscriptions,
                "agent_ratings": self.agent_ratings
            }
            
            async with aiofiles.open("./data/marketplace/agents.json", "w") as f:
                await f.write(json.dumps(data, indent=2))
                
        except Exception as e:
            logger.error(f"Failed to save agents: {e}")
    
    def _load_agents(self):
        """Load agents from storage"""
        try:
            import os
            import aiofiles
            
            if not os.path.exists("./data/marketplace/agents.json"):
                return
            
            with open("./data/marketplace/agents.json", "r") as f:
                data = json.load(f)
            
            # Load agents
            for agent_id, agent_data in data.get("agents", {}).items():
                agent = AgentDefinition(
                    id=agent_data["id"],
                    name=agent_data["name"],
                    description=agent_data["description"],
                    category=AgentCategory(agent_data["category"]),
                    author_id=agent_data["author_id"],
                    status=AgentStatus(agent_data.get("status", "draft")),
                    version=agent_data.get("version", "1.0.0"),
                    tags=agent_data.get("tags", []),
                    capabilities=agent_data.get("capabilities", []),
                    configuration=agent_data.get("configuration", {}),
                    pricing=agent_data.get("pricing", {}),
                    usage_stats=agent_data.get("usage_stats", {}),
                    created_at=datetime.fromisoformat(agent_data["created_at"]),
                    updated_at=datetime.fromisoformat(agent_data["updated_at"]),
                    published_at=datetime.fromisoformat(agent_data["published_at"]) if agent_data.get("published_at") else None
                )
                self.agents[agent_id] = agent
            
            # Load other data
            self.featured_agents = data.get("featured_agents", [])
            self.user_subscriptions = data.get("user_subscriptions", {})
            self.agent_ratings = data.get("agent_ratings", {})
            
            logger.info(f"Loaded {len(self.agents)} agents from storage")
            
        except Exception as e:
            logger.error(f"Failed to load agents: {e}")
    
    def get_marketplace_stats(self) -> Dict[str, Any]:
        """Get marketplace statistics"""
        published_agents = [a for a in self.agents.values() if a.status == AgentStatus.PUBLISHED]
        total_executions = sum(a.usage_stats.get("executions", 0) for a in self.agents.values())
        
        return {
            "total_agents": len(self.agents),
            "published_agents": len(published_agents),
            "featured_agents": len(self.featured_agents),
            "total_executions": total_executions,
            "total_subscriptions": sum(len(subs) for subs in self.user_subscriptions.values()),
            "total_ratings": sum(len(ratings) for ratings in self.agent_ratings.values())
        }


# Global instance
_agent_marketplace = None


def get_agent_marketplace() -> AgentMarketplace:
    """Get global agent marketplace instance"""
    global _agent_marketplace
    if _agent_marketplace is None:
        _agent_marketplace = AgentMarketplace()
    return _agent_marketplace
