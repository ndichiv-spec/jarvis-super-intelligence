"""
JARVIS Autonomous Agent Swarm Intelligence
==========================================
Self-organizing intelligence without central control for complex problem solving.
"""

import asyncio
import random
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)

class AgentState(Enum):
    IDLE = "idle"
    WORKING = "working"
    COORDINATING = "coordinating"
    WAITING = "waiting"

class TaskPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class SwarmTask:
    id: str
    description: str
    priority: TaskPriority
    required_agents: int
    current_agents: int = 0
    status: str = "pending"
    result: Optional[Any] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

@dataclass
class Agent:
    id: str
    name: str
    capabilities: List[str]
    state: AgentState = AgentState.IDLE
    current_task: Optional[str] = None
    performance_score: float = 1.0
    tasks_completed: int = 0
    last_active: float = field(default_factory=time.time)

class SwarmIntelligence:
    """Autonomous agent swarm intelligence system"""
    
    def __init__(self, num_agents: int = 5):
        self.agents: List[Agent] = []
        self.tasks: List[SwarmTask] = []
        self.task_counter = 0
        self.running = False
        self.swarm_metrics = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "avg_completion_time": 0.0,
            "coordination_events": 0
        }
        
        # Initialize agents with different capabilities
        capabilities_list = [
            ["analysis", "optimization"],
            ["generation", "reasoning"],
            ["monitoring", "coordination"],
            ["learning", "adaptation"],
            ["communication", "integration"]
        ]
        
        for i in range(num_agents):
            agent = Agent(
                id=f"agent_{i}",
                name=f"Swarm Agent {i+1}",
                capabilities=capabilities_list[i % len(capabilities_list)]
            )
            self.agents.append(agent)
    
    async def initialize(self):
        """Initialize the swarm intelligence system"""
        logger.info(f"Initializing swarm with {len(self.agents)} agents")
        self.running = True
        # Start coordination loop
        asyncio.create_task(self.coordination_loop())
        # Start task processing
        asyncio.create_task(self.task_processing_loop())
    
    async def shutdown(self):
        """Shutdown the swarm intelligence system"""
        logger.info("Shutting down swarm intelligence")
        self.running = False
    
    def create_task(self, description: str, priority: TaskPriority = TaskPriority.MEDIUM, 
                   required_agents: int = 1) -> str:
        """Create a new task for the swarm"""
        self.task_counter += 1
        task = SwarmTask(
            id=f"task_{self.task_counter}",
            description=description,
            priority=priority,
            required_agents=required_agents
        )
        self.tasks.append(task)
        self.swarm_metrics["total_tasks"] += 1
        logger.info(f"Created task {task.id}: {description}")
        return task.id
    
    def get_available_agents(self, required_capabilities: List[str] = None) -> List[Agent]:
        """Get available agents with required capabilities"""
        available = [agent for agent in self.agents if agent.state == AgentState.IDLE]
        if required_capabilities:
            available = [
                agent for agent in available 
                if any(cap in agent.capabilities for cap in required_capabilities)
            ]
        return available
    
    async def coordination_loop(self):
        """Main coordination loop for swarm intelligence"""
        while self.running:
            try:
                # Self-organize task assignment
                await self.self_organize_tasks()
                
                # Update agent performance scores
                await self.update_agent_performance()
                
                # Swarm communication
                await self.swarm_communication()
                
                await asyncio.sleep(1)  # Coordination interval
            except Exception as e:
                logger.error(f"Coordination error: {e}")
    
    async def self_organize_tasks(self):
        """Self-organize task assignment without central control"""
        pending_tasks = [task for task in self.tasks if task.status == "pending"]
        
        # Sort by priority
        pending_tasks.sort(key=lambda t: t.priority.value, reverse=True)
        
        for task in pending_tasks:
            available_agents = self.get_available_agents()
            
            if len(available_agents) >= task.required_agents:
                # Assign agents to task
                assigned_agents = available_agents[:task.required_agents]
                
                for agent in assigned_agents:
                    agent.state = AgentState.WORKING
                    agent.current_task = task.id
                    task.current_agents += 1
                
                task.status = "in_progress"
                task.started_at = time.time()
                self.swarm_metrics["coordination_events"] += 1
                logger.info(f"Assigned {len(assigned_agents)} agents to task {task.id}")
    
    async def task_processing_loop(self):
        """Process assigned tasks"""
        while self.running:
            try:
                in_progress_tasks = [task for task in self.tasks if task.status == "in_progress"]
                
                for task in in_progress_tasks:
                    # Simulate task processing
                    task_agents = [agent for agent in self.agents if agent.current_task == task.id]
                    
                    if task_agents:
                        # Simulate progress
                        progress = random.randint(5, 15)
                        
                        # Check if task is complete
                        if random.random() < 0.1:  # 10% chance to complete
                            await self.complete_task(task, task_agents)
                
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Task processing error: {e}")
    
    async def complete_task(self, task: SwarmTask, agents: List[Agent]):
        """Complete a task and release agents"""
        task.status = "completed"
        task.completed_at = time.time()
        task.result = {
            "success": True,
            "output": f"Task {task.id} completed successfully",
            "agents_involved": len(agents)
        }
        
        # Release agents
        for agent in agents:
            agent.state = AgentState.IDLE
            agent.current_task = None
            agent.tasks_completed += 1
            agent.last_active = time.time()
        
        # Update metrics
        completion_time = task.completed_at - task.started_at
        self.swarm_metrics["completed_tasks"] += 1
        self.swarm_metrics["avg_completion_time"] = (
            (self.swarm_metrics["avg_completion_time"] * (self.swarm_metrics["completed_tasks"] - 1) + completion_time) /
            self.swarm_metrics["completed_tasks"]
        )
        
        logger.info(f"Task {task.id} completed in {completion_time:.2f}s")
    
    async def update_agent_performance(self):
        """Update agent performance scores based on task completion"""
        for agent in self.agents:
            if agent.tasks_completed > 0:
                # Performance based on tasks completed and recency
                time_factor = 1.0 / (1.0 + (time.time() - agent.last_active) / 3600)
                agent.performance_score = min(1.0, agent.tasks_completed * 0.1 * time_factor)
    
    async def swarm_communication(self):
        """Simulate swarm communication between agents"""
        # Random agent coordination events
        if random.random() < 0.2:  # 20% chance of coordination
            coordinating_agents = [agent for agent in self.agents if agent.state == AgentState.WORKING]
            if len(coordinating_agents) >= 2:
                # Agents coordinate with each other
                for agent in coordinating_agents[:2]:
                    agent.state = AgentState.COORDINATING
                    await asyncio.sleep(0.1)
                    agent.state = AgentState.WORKING
                self.swarm_metrics["coordination_events"] += 1
    
    def get_swarm_status(self) -> Dict[str, Any]:
        """Get current swarm status"""
        return {
            "agents": [
                {
                    "id": agent.id,
                    "name": agent.name,
                    "state": agent.state.value,
                    "current_task": agent.current_task,
                    "performance_score": agent.performance_score,
                    "tasks_completed": agent.tasks_completed,
                    "capabilities": agent.capabilities
                }
                for agent in self.agents
            ],
            "tasks": [
                {
                    "id": task.id,
                    "description": task.description,
                    "priority": task.priority.name,
                    "status": task.status,
                    "current_agents": task.current_agents,
                    "required_agents": task.required_agents
                }
                for task in self.tasks[-10:]  # Last 10 tasks
            ],
            "metrics": self.swarm_metrics
        }
    
    def get_agent_by_id(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID"""
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None
    
    def get_task_by_id(self, task_id: str) -> Optional[SwarmTask]:
        """Get task by ID"""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

# Global swarm instance
swarm_intelligence: Optional[SwarmIntelligence] = None

def get_swarm_intelligence() -> SwarmIntelligence:
    """Get or create swarm intelligence instance"""
    global swarm_intelligence
    if swarm_intelligence is None:
        swarm_intelligence = SwarmIntelligence()
    return swarm_intelligence
