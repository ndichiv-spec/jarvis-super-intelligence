from __future__ import annotations

from typing import Any


class ServiceRegistry:
    def __init__(self) -> None:
        self._services: dict[str, list[dict[str, Any]]] = {}

    async def initialize(self) -> None:
        return None

    async def register_service(
        self,
        name: str,
        host: str,
        port: int,
        health_endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        instance = {
            "name": name,
            "host": host,
            "port": port,
            "health_endpoint": health_endpoint,
            "healthy": True,
            "metadata": dict(kwargs),
        }
        self._services.setdefault(name, []).append(instance)
        return instance

    async def get_service_instances(self, name: str) -> list[dict[str, Any]]:
        return list(self._services.get(name, []))

    async def get_healthy_instances(self, name: str) -> list[dict[str, Any]]:
        return [service for service in self._services.get(name, []) if service.get("healthy")]

    async def get_service_stats(self) -> dict[str, Any]:
        total_instances = sum(len(instances) for instances in self._services.values())
        return {"total_services": len(self._services), "total_instances": total_instances}

    async def get_all_services(self) -> dict[str, list[dict[str, Any]]]:
        return {name: list(instances) for name, instances in self._services.items()}

    async def shutdown(self) -> None:
        self._services.clear()


_registry = ServiceRegistry()


def get_service_registry() -> ServiceRegistry:
    return _registry


__all__ = ["ServiceRegistry", "get_service_registry"]
