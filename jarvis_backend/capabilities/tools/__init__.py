"""
JARVIS TOOL / CONNECTOR CAPABILITY
===================================

Tools and connectors are capabilities that interact with external systems.
This wraps the existing browser infrastructure and adds GitHub and PostgreSQL
connectors.

Security boundary:
    Brain
     |
    Tool request
     |
    Authorization
     |
    Connector
     |
    Credential boundary (secrets never reach Brain)
     |
    External system
     |
    Sanitized result
     |
    Brain
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import Capability, CapabilityStatus, ExecutionContext, ExecutionResult
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import ToolExecutionLog, AuditLog


class ToolCapability(Capability):
    """
    Tool and connector execution capability.

    Each tool operates through a security/credential boundary:
    - The Brain requests an action
    - Authorization is checked
    - The connector accesses credentials through the vault
    - External system is called
    - Results are sanitized before returning to the Brain
    """

    name = "tool"
    version = "1.0.0"
    category = "tools"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._registered_tools: Dict[str, Any] = {}
        self._init_tools()

    def _init_tools(self):
        """Register available tools."""
        from jarvis_backend.capabilities.tools.github import GitHubTool
        from jarvis_backend.capabilities.tools.postgresql import PostgreSQLTool
        from jarvis_backend.capabilities.tools.browser_tool import BrowserTool
        from jarvis_backend.capabilities.tools.science_tool import ScienceTool
        from jarvis_backend.capabilities.tools.research_tool import ResearchTool

        self._registered_tools = {
            'github': GitHubTool(),
            'postgresql': PostgreSQLTool(),
            'browser': BrowserTool(),
            'science': ScienceTool(),
            'research': ResearchTool(),
        }

        # MCP tool — bridges external MCP servers into JARVIS (Phase 1)
        try:
            from jarvis_backend.capabilities.tools.mcp_tool import MCPTool
            self._registered_tools['mcp'] = MCPTool()
        except Exception:
            pass

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check - verify tool availability."""
        tool_statuses = {}
        for name, tool in self._registered_tools.items():
            try:
                health = await tool.health()
                tool_statuses[name] = health
            except Exception as e:
                tool_statuses[name] = {'status': 'error', 'error': str(e)}

        healthy_count = sum(1 for v in tool_statuses.values()
                           if v.get('status') in ('ok', 'available', 'ready'))

        return {
            'status': CapabilityStatus.READY if healthy_count > 0 else CapabilityStatus.NOT_CONFIGURED,
            'healthy': healthy_count > 0,
            'tools': tool_statuses,
            'tool_count': len(self._registered_tools),
        }

    async def health_for_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Probe only the selected tool before dispatching an action."""
        tool_name = request.get("tool", "")
        tool = self._registered_tools.get(tool_name)
        if tool is None:
            self.set_status(CapabilityStatus.UNAVAILABLE, f"Tool '{tool_name}' is not registered")
            return {
                "status": CapabilityStatus.UNAVAILABLE.value,
                "healthy": False,
                "error": f"Tool '{tool_name}' is not registered",
                "tool": tool_name,
            }
        try:
            tool_health = await tool.health()
        except Exception as error:
            tool_health = {
                "status": "error",
                "healthy": False,
                "error": str(error),
            }
        healthy = bool(tool_health.get("healthy")) and str(
            tool_health.get("status", "")
        ).lower() in {"ok", "available", "ready"}
        status = CapabilityStatus.READY if healthy else (
            CapabilityStatus.NOT_CONFIGURED
            if str(tool_health.get("status", "")).lower() in {"not_configured", "auth_required"}
            else CapabilityStatus.UNAVAILABLE
        )
        self.set_status(status, None if healthy else tool_health.get("error"))
        return {
            "status": status.value,
            "healthy": healthy,
            "tool": tool_name,
            "tools": {tool_name: tool_health},
            "error": tool_health.get("error"),
        }

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """
        Execute a tool action.

        Request fields:
        - tool: Tool name (github, postgresql, browser)
        - action: Tool-specific action
        - params: Tool-specific parameters
        - credentials: Should NOT be passed - tools access their own credentials
        """
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        tool_name = request.get('tool', '')
        action = request.get('action', '')
        params = request.get('params', {})
        start_time = time.time()
        correlation_id = context.correlation_id

        # Security boundary: tools must NOT receive credentials from request
        # They access their own credentials through the vault/secrets manager
        # Strip any credential-like params
        sanitized_params = self._strip_credentials(params)

        self._event_bus.emit(
            event_type='tool.execution.started',
            source='orchestrator',
            capability='tool',
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='started',
            payload={'tool': tool_name, 'action': action},
        )

        # Authorization check
        auth_result = self._authorize_tool(tool_name, context)
        if not auth_result['authorized']:
            self._event_bus.emit(
                event_type='tool.authorization.failed',
                source='tool',
                capability='tool',
                correlation_id=correlation_id,
                status='failed',
                payload={'tool': tool_name, 'reason': auth_result['reason']},
            )
            return ExecutionResult(
                capability=self.name,
                success=False,
                error=auth_result['reason'],
                error_type='AUTHORIZATION_FAILED',
                correlation_id=correlation_id,
                metrics={'denied': True},
            )

        self._event_bus.emit(
            event_type='tool.authorization.completed',
            source='tool',
            capability='tool',
            correlation_id=correlation_id,
            status='completed',
            payload={'tool': tool_name, 'authorized': True},
        )

        tool = self._registered_tools.get(tool_name)
        if not tool:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error=f"Tool '{tool_name}' is not registered. Available: {list(self._registered_tools.keys())}",
                error_type="TOOL_NOT_FOUND",
                correlation_id=correlation_id,
            )

        confirmation_required = (
            (tool_name, action) in {
                ("github", "create_issue"),
                ("github", "update_file"),
                ("research", "ingest_feed"),
                ("research", "ingest_url"),
                ("research", "discover_new_feeds"),
                ("research", "ingest_content"),
            }
            or tool_name == "mcp"
        )
        if confirmation_required and context.metadata.get("confirmed") is not True:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="This write action requires explicit user confirmation.",
                error_type="CONFIRMATION_REQUIRED",
                correlation_id=correlation_id,
                metrics={"denied": True},
            )

        try:
            # Execute tool
            tool_result = await tool.execute(action, sanitized_params, context)

            result = ExecutionResult(
                capability=self.name,
                success=tool_result.get('success', False),
                data=tool_result.get('data', {}),
                error=tool_result.get('error'),
                error_type=tool_result.get('error_type'),
                correlation_id=correlation_id,
                artifacts=tool_result.get('artifacts', []),
                metrics=tool_result.get('metrics', {}),
            )

        except Exception as e:
            result = ExecutionResult(
                capability=self.name,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                correlation_id=correlation_id,
            )

        result.latency_ms = (time.time() - start_time) * 1000.0
        result.correlation_id = correlation_id

        # Log tool execution
        ToolExecutionLog.log_execution(
            capability=self.name,
            tool_name=tool_name,
            request={'action': action, 'params': sanitized_params},
            response=result.to_dict(),
            success=result.success,
            error=result.error,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=result.latency_ms,
            session_id=context.session_id,
            user_id=context.user_id,
            correlation_id=correlation_id,
        )

        self._event_bus.emit(
            event_type=f'tool.{tool_name}.execution.completed',
            source='tool',
            capability='tool',
            correlation_id=correlation_id,
            status='completed' if result.success else 'failed',
            payload={'tool': tool_name, 'action': action, 'success': result.success},
        )

        AuditLog.log(
            event_type=f'tool.{tool_name}.{action}',
            source='tool',
            capability='tool',
            user_id=context.user_id,
            session_id=context.session_id,
            action=f'{tool_name}:{action}',
            result='success' if result.success else 'error',
        )

        return result

    def _strip_credentials(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Remove any credential-like fields from params."""
        secret_patterns = ('key', 'secret', 'token', 'password', 'credential', 'authorization')
        sanitized = {}

        def _clean(obj):
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()
                        if not any(s in k.lower() for s in secret_patterns)}
            elif isinstance(obj, list):
                return [_clean(v) for v in obj]
            return obj

        return _clean(params)

    def _authorize_tool(self, tool_name: str, context: ExecutionContext) -> Dict[str, Any]:
        """Check if user is authorized to use this tool.
        
        This is the security boundary. Credentials never reach the Brain.
        Tools access their own credentials through the vault.
        """
        # Check permissions
        required_perms = {
            'github': ['tool.github'],
            'postgresql': ['tool.database'],
            'browser': ['tool.browser'],
            'science': ['tool.science'],
            'research': ['tool.research'],
            'mcp': ['tool.mcp'],
        }

        required = required_perms.get(tool_name, [])
        if required:
            has_perm = any(perm in context.permissions for perm in required)
            # Admin users have all permissions
            is_admin = 'admin' in context.permissions

            if not has_perm and not is_admin:
                return {
                    'authorized': False,
                    'reason': f"Permission required: {', '.join(required)}. "
                              f"Current permissions: {context.permissions}",
                }

        return {'authorized': True, 'reason': ''}

    def list_tools(self) -> List[Dict[str, Any]]:
        """Describe registered tools and only their implemented actions."""
        action_specs = {
            "github": [
                ("get_repo", "Read a repository", {"owner": "string", "repo": "string"}, ["tool.github"]),
                ("list_repos", "List repositories available to the configured account", {}, ["tool.github"]),
                ("list_issues", "Read repository issues", {"owner": "string", "repo": "string", "state": "string"}, ["tool.github"]),
                ("list_commits", "Read recent repository commits", {"owner": "string", "repo": "string"}, ["tool.github"]),
                ("create_issue", "Create a repository issue", {"owner": "string", "repo": "string", "title": "string", "body": "string"}, ["tool.github", "confirmation"]),
                ("update_file", "Create or update a repository file", {"owner": "string", "repo": "string", "path": "string", "content": "string", "message": "string", "branch": "string"}, ["tool.github", "confirmation"]),
            ],
            "postgresql": [
                ("query", "Execute a configured database query", {"query": "string"}, ["tool.database"]),
                ("list_tables", "List tables in the configured database", {}, ["tool.database"]),
                ("describe_table", "Describe a configured database table", {"table": "string"}, ["tool.database"]),
            ],
            "browser": [
                ("search", "Search the public web", {"query": "string"}, ["tool.browser"]),
                ("fetch", "Fetch a public HTTP(S) page", {"url": "string"}, ["tool.browser"]),
                ("extract_links", "Extract links from a public HTTP(S) page", {"url": "string"}, ["tool.browser"]),
                ("extract_text", "Extract readable text from a public HTTP(S) page", {"url": "string"}, ["tool.browser"]),
            ],
            "science": [
                ("solve", "Solve a mathematical or scientific problem", {
                    "problem": "string",
                    "operation": "string",
                    "variable": "string",
                    "domain": "string",
                }, ["tool.science"]),
            ],
            "research": [
                ("ingest_feed", "Ingest a configured research feed", {"feed_id": "string"}, ["tool.research", "confirmation"]),
                ("search_arxiv", "Search academic papers on arXiv", {"query": "string", "max_results": "integer"}, ["tool.research"]),
                ("ingest_url", "Add page content to the knowledge store", {"url": "string"}, ["tool.research", "confirmation"]),
                ("get_knowledge_graph", "Read the research knowledge graph", {}, ["tool.research"]),
                ("discover_new_feeds", "Discover and add research feeds", {}, ["tool.research", "confirmation"]),
                ("get_status", "Read research service status", {}, ["tool.research"]),
                ("ingest_content", "Add provided content to the knowledge store", {"content": "string", "title": "string"}, ["tool.research", "confirmation"]),
            ],
            "mcp": [],
        }
        descriptions = {
            "github": "GitHub API connector",
            "postgresql": "Configured PostgreSQL connector",
            "browser": "HTTP browser and public web search",
            "science": "Scientific computation tools",
            "research": "Research and knowledge tools",
            "mcp": "Tools discovered from connected MCP servers",
        }
        required_permissions = {
            "github": ["tool.github"],
            "postgresql": ["tool.database"],
            "browser": ["tool.browser"],
            "science": ["tool.science"],
            "research": ["tool.research"],
            "mcp": ["tool.mcp"],
        }
        return [
            {
                "id": name,
                "name": name,
                "version": tool.version,
                "type": tool.category,
                "description": descriptions.get(name, getattr(tool, "description", name)),
                "permissions": required_permissions.get(name, []),
                "actions": [
                    {
                        "id": action,
                        "name": action,
                        "description": description,
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                key: {"type": value} for key, value in properties.items()
                            },
                            "required": [
                                key for key in properties
                                if key in {"owner", "repo", "query", "url", "title", "problem", "path", "content", "message"}
                            ],
                        },
                        "permissions": permissions,
                        "execution_supported": True,
                    }
                    for action, description, properties, permissions
                    in action_specs.get(name, [])
                ],
            }
            for name, tool in self._registered_tools.items()
        ]

    async def discover_actions(self) -> List[Dict[str, Any]]:
        """Return the registered action contract, including live MCP schemas."""
        descriptors = self.list_tools()
        mcp_tool = self._registered_tools.get("mcp")
        discover = getattr(mcp_tool, "discover_actions", None)
        if callable(discover):
            discovered = await discover()
            for descriptor in descriptors:
                if descriptor["id"] == "mcp":
                    descriptor["actions"] = [
                        {
                            "id": tool["qualified_name"],
                            "name": tool["qualified_name"],
                            "description": tool.get("description", ""),
                            "input_schema": tool.get("input_schema") or {"type": "object"},
                            "permissions": ["tool.mcp", "confirmation"],
                            "execution_supported": True,
                        }
                        for tool in discovered
                    ]
        return descriptors

    async def cancel(self, correlation_id: str) -> bool:
        return False

    async def shutdown(self) -> bool:
        for tool in self._registered_tools.values():
            if hasattr(tool, 'shutdown'):
                await tool.shutdown()
        self.set_status(CapabilityStatus.OFFLINE)
        return True


from datetime import datetime, timezone

__all__ = ['ToolCapability']
