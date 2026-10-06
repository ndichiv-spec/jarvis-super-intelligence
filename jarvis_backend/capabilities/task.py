"""
JARVIS TASK CAPABILITY
======================

Tasks and autonomous work capability. Wraps the existing scheduler/infrastructure.

JARVIS must be able to:
- create task
- execute task
- pause
- resume
- cancel
- retry
- monitor
- persist
- recover
- report
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import Capability, CapabilityStatus, ExecutionContext, ExecutionResult
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import TaskRepository, AuditLog


class TaskCapability(Capability):
    """
    Task and autonomous work capability.

    Tasks persist across restarts and recover automatically.
    """

    name = "task"
    version = "1.0.0"
    category = "tasks"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._task_queue: asyncio.Queue = asyncio.Queue()

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check - verify task database."""
        try:
            # Real check
            test_id = TaskRepository.create_task(
                user_id="health-check",
                capability="task",
                title="Health Check Task",
                input_data={'health_check': True},
            )

            retrieved = TaskRepository.get_task(test_id)

            from jarvis_backend.persistence import db_session, tasks_table, delete
            with db_session() as conn:
                conn.execute(delete(tasks_table).where(tasks_table.c.id == test_id))

            ok = retrieved is not None and retrieved['id'] == test_id
            return {
                'status': CapabilityStatus.READY if ok else CapabilityStatus.DEGRADED,
                'healthy': ok,
                'running_tasks': len(self._running_tasks),
                'db_connected': True,
            }
        except Exception as e:
            return {
                'status': CapabilityStatus.ERROR,
                'error': str(e),
                'healthy': False,
                'db_connected': False,
            }

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """
        Execute a task operation.

        Actions:
        - 'create': Create a new task
        - 'execute': Start task execution
        - 'pause': Pause task
        - 'resume': Resume task
        - 'cancel': Cancel task
        - 'retry': Retry failed task
        - 'get': Get task status
        - 'list': List tasks
        - 'recover': Recover tasks after restart
        """
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        action = request.get('action', 'create')
        start_time = time.time()
        correlation_id = context.correlation_id

        self._event_bus.emit(
            event_type=f'task.{action}.started',
            source='orchestrator',
            capability='task',
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='started',
            payload={'action': action},
        )

        try:
            if action == 'create':
                result = await self._create_task(request, context)
            elif action == 'execute':
                result = await self._execute_task(request, context)
            elif action == 'pause':
                result = await self._pause_task(request, context)
            elif action == 'resume':
                result = await self._resume_task(request, context)
            elif action == 'cancel':
                result = await self._cancel_task(request, context)
            elif action == 'retry':
                result = await self._retry_task(request, context)
            elif action == 'get':
                result = await self._get_task(request, context)
            elif action == 'list':
                result = await self._list_tasks(request, context)
            elif action == 'recover':
                result = await self._recover_tasks(request, context)
            else:
                result = ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=f"Unknown task action: {action}",
                    error_type="INVALID_ACTION",
                    correlation_id=correlation_id,
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

        self._event_bus.emit(
            event_type=f'task.{action}.completed',
            source='task',
            capability='task',
            correlation_id=correlation_id,
            status='completed' if result.success else 'failed',
            payload={'success': result.success},
        )

        return result

    async def _create_task(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Create a new task."""
        task_id = TaskRepository.create_task(
            user_id=context.user_id,
            capability=request.get('capability', 'brain'),
            title=request.get('title', 'Untitled Task'),
            description=request.get('description'),
            input_data=request.get('input'),
            priority=request.get('priority', 0),
            scheduled_at=request.get('scheduled_at'),
            max_retries=request.get('max_retries', 3),
            parent_task_id=request.get('parent_task_id'),
            correlation_id=context.correlation_id,
            metadata=request.get('metadata'),
        )

        self._event_bus.emit(
            event_type='task.created',
            source='task',
            capability='task',
            correlation_id=context.correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='started',
            payload={'task_id': task_id, 'title': request.get('title')},
        )

        AuditLog.log(
            event_type='task.created',
            source='task',
            capability='task',
            user_id=context.user_id,
            session_id=context.session_id,
            action='create',
            resource=f'task/{task_id}',
        )

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'task_id': task_id},
            correlation_id=context.correlation_id,
        )

    async def _execute_task(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Start task execution."""
        task_id = request.get('task_id', '')
        task = TaskRepository.get_task(task_id)

        if not task:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error=f"Task {task_id} not found",
                error_type="NOT_FOUND",
                correlation_id=context.correlation_id,
            )

        if task['status'] not in ('pending', 'paused'):
            return ExecutionResult(
                capability=self.name,
                success=False,
                error=f"Task {task_id} is not in a runnable state (current: {task['status']})",
                error_type="INVALID_STATE",
                correlation_id=context.correlation_id,
            )

        TaskRepository.update_task(
            task_id=task_id,
            status='running',
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        self._event_bus.emit(
            event_type='task.started',
            source='task',
            capability='task',
            correlation_id=context.correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='started',
            payload={'task_id': task_id},
        )

        # Execute the task in the background
        input_data = json.loads(task['input_json']) if task.get('input_json') else {}

        # Get the orchestrator to execute the task's capability
        orchestrator = self._get_orchestrator()
        if orchestrator:
            exec_context = ExecutionContext(
                user_id=task.get('user_id', context.user_id),
                session_id=context.session_id,
                correlation_id=context.correlation_id,
                permissions=context.permissions,
            )

            try:
                cap_result = await orchestrator.execute_capability(
                    capability_name=task.get('capability', 'brain'),
                    request=input_data,
                    context=exec_context,
                )

                if cap_result.success:
                    TaskRepository.update_task(
                        task_id=task_id,
                        status='completed',
                        completed_at=datetime.now(timezone.utc).isoformat(),
                        output_data=cap_result.to_dict(),
                    )
                    self._event_bus.emit(
                        event_type='task.completed',
                        source='task',
                        capability='task',
                        correlation_id=context.correlation_id,
                        session_id=context.session_id,
                        user_id=context.user_id,
                        status='completed',
                        payload={'task_id': task_id},
                    )
                    return ExecutionResult(
                        capability=self.name,
                        success=True,
                        data={'task_id': task_id, 'status': 'completed', 'result': cap_result.to_dict()},
                        correlation_id=context.correlation_id,
                    )
                else:
                    if task.get('retry_count', 0) < task.get('max_retries', 3):
                        TaskRepository.update_task(
                            task_id=task_id,
                            status='failed',
                            error=cap_result.error,
                            retry_count=task.get('retry_count', 0) + 1,
                        )
                    else:
                        TaskRepository.update_task(
                            task_id=task_id,
                            status='failed',
                            error=cap_result.error,
                        )
                    self._event_bus.emit(
                        event_type='task.failed',
                        source='task',
                        capability='task',
                        correlation_id=context.correlation_id,
                        session_id=context.session_id,
                        user_id=context.user_id,
                        status='failed',
                        payload={'task_id': task_id, 'error': cap_result.error},
                    )
                    return ExecutionResult(
                        capability=self.name,
                        success=False,
                        error=cap_result.error,
                        error_type='TASK_EXECUTION_FAILED',
                        correlation_id=context.correlation_id,
                    )

            except Exception as e:
                TaskRepository.update_task(
                    task_id=task_id,
                    status='failed',
                    error=str(e),
                )
                return ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=str(e),
                    error_type=type(e).__name__,
                    correlation_id=context.correlation_id,
                )
        else:
            TaskRepository.update_task(
                task_id=task_id,
                status='failed',
                error='Orchestrator not available',
            )
            return ExecutionResult(
                capability=self.name,
                success=False,
                error='Orchestrator not available to execute task',
                error_type='ORCHESTRATOR_UNAVAILABLE',
                correlation_id=context.correlation_id,
            )

    def _get_orchestrator(self):
        """Get the global orchestrator."""
        from jarvis_backend.capability import get_orchestrator
        return get_orchestrator()

    async def _pause_task(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Pause a task."""
        task_id = request.get('task_id', '')
        TaskRepository.update_task(task_id, 'paused')

        self._event_bus.emit(
            event_type='task.paused',
            source='task',
            capability='task',
            correlation_id=context.correlation_id,
            payload={'task_id': task_id},
        )

        return ExecutionResult(
            capability=self.name, success=True,
            data={'task_id': task_id, 'status': 'paused'},
            correlation_id=context.correlation_id,
        )

    async def _resume_task(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Resume a paused task."""
        task_id = request.get('task_id', '')
        task = TaskRepository.get_task(task_id)

        if not task or task['status'] not in ('paused', 'pending'):
            return ExecutionResult(
                capability=self.name,
                success=False,
                error=f"Cannot resume task in state: {task['status'] if task else 'not_found'}",
                error_type="INVALID_STATE",
                correlation_id=context.correlation_id,
            )

        # Re-execute
        return await self._execute_task(
            {'task_id': task_id},
            ExecutionContext(
                user_id=task['user_id'] or context.user_id,
                session_id=context.session_id,
                correlation_id=context.correlation_id,
            )
        )

    async def _cancel_task(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Cancel a task."""
        task_id = request.get('task_id', '')
        TaskRepository.update_task(task_id, 'cancelled')

        # Cancel running task if any
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()

        self._event_bus.emit(
            event_type='task.cancelled',
            source='task',
            capability='task',
            correlation_id=context.correlation_id,
            payload={'task_id': task_id},
        )

        return ExecutionResult(
            capability=self.name, success=True,
            data={'task_id': task_id, 'status': 'cancelled'},
            correlation_id=context.correlation_id,
        )

    async def _retry_task(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Retry a failed task."""
        task_id = request.get('task_id', '')
        task = TaskRepository.get_task(task_id)

        if not task:
            return ExecutionResult(
                capability=self.name, success=False,
                error="Task not found",
                error_type="NOT_FOUND",
                correlation_id=context.correlation_id,
            )

        TaskRepository.update_task(
            task_id=task_id,
            status='pending',
            started_at=None,
            completed_at=None,
        )

        return await self._execute_task(
            {'task_id': task_id},
            ExecutionContext(
                user_id=task['user_id'] or context.user_id,
                session_id=context.session_id,
                correlation_id=context.correlation_id,
            )
        )

    async def _get_task(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Get task status."""
        task_id = request.get('task_id', '')
        task = TaskRepository.get_task(task_id)

        if task:
            # Parse JSON fields
            if task.get('input_json'):
                task['input'] = json.loads(task['input_json'])
            if task.get('output_json'):
                task['output'] = json.loads(task['output_json'])
            if task.get('metadata_json'):
                task['metadata'] = json.loads(task['metadata_json'])

        return ExecutionResult(
            capability=self.name, success=True,
            data={'task': task} if task else {'task': None, 'error': 'not found'},
            correlation_id=context.correlation_id,
        )

    async def _list_tasks(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """List tasks."""
        status_filter = request.get('status', 'all')
        capability = request.get('capability')

        if status_filter == 'all':
            tasks = TaskRepository.get_by_status('pending', capability, limit=50)
            tasks += TaskRepository.get_by_status('running', capability, limit=50)
            tasks += TaskRepository.get_by_status('paused', capability, limit=50)
            tasks += TaskRepository.get_by_status('completed', capability, limit=50)
            tasks += TaskRepository.get_by_status('failed', capability, limit=50)
        else:
            tasks = TaskRepository.get_by_status(status_filter, capability, limit=100)

        for task in tasks:
            if task.get('input_json'):
                task['input'] = json.loads(task['input_json'])
            if task.get('metadata_json'):
                task['metadata'] = json.loads(task['metadata_json'])

        return ExecutionResult(
            capability=self.name, success=True,
            data={'tasks': tasks, 'count': len(tasks)},
            correlation_id=context.correlation_id,
        )

    async def _recover_tasks(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Recover tasks after restart."""
        incomplete = TaskRepository.get_incomplete_tasks()

        for task in incomplete:
            if task['status'] == 'running':
                # Re-check if task actually completed
                TaskRepository.update_task(
                    task_id=task['id'],
                    status='failed',
                    error='Recovered after restart - execution state unknown',
                )
            elif task['status'] == 'pending':
                # Keep as pending for retry
                pass

        self._event_bus.emit(
            event_type='task.recovered',
            source='task',
            capability='task',
            correlation_id=context.correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='completed',
            payload={
                'recovered_tasks': len(incomplete),
                'task_ids': [t['id'] for t in incomplete],
            },
        )

        return ExecutionResult(
            capability=self.name, success=True,
            data={
                'recovered_count': len(incomplete),
                'tasks': [t['id'] for t in incomplete],
            },
            correlation_id=context.correlation_id,
        )

    async def cancel(self, correlation_id: str) -> bool:
        return False

    async def shutdown(self) -> bool:
        for task in self._running_tasks.values():
            task.cancel()
        self._running_tasks.clear()
        self.set_status(CapabilityStatus.OFFLINE)
        return True


import json

__all__ = ['TaskCapability']
