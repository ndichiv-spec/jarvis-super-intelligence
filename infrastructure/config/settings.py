"""
Application settings defined using the ConfigLoader with typed access.
All config keys follow: JARVIS_<SECTION>_<KEY> convention.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from .loader import (
    ConfigLoader,
    ConfigRule,
    default_config_loader,
    DeploymentEnvironment,
)


@dataclass
class DatabaseSettings:
    url: str = "sqlite+aiosqlite:///./jarvis.db"
    host: str = "localhost"
    port: int = 5432
    name: str = "jarvis"
    user: str = "jarvis"
    password: str = ""
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False


@dataclass
class RedisSettings:
    url: str = "redis://localhost:6379/0"
    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    pool_max_size: int = 20
    socket_timeout: int = 5


@dataclass
class ServerSettings:
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    api_prefix: str = "/api/v1"
    debug: bool = False
    log_level: str = "info"
    reload: bool = False


@dataclass
class AISettings:
    default_model: str = "auto"
    ollama_url: str = "http://localhost:11434"
    openai_key: str = ""
    google_gemini_key: str = ""
    anthropic_key: str = ""
    huggingface_key: str = ""
    replicate_key: str = ""
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    max_tokens: int = 4096
    temperature: float = 0.7


@dataclass
class LoggingSettings:
    level: str = "INFO"
    format: str = "json"
    directory: str = "logs"
    max_bytes: int = 10485760
    backup_count: int = 10
    enable_console: bool = True
    enable_file: bool = True
    enable_sentry: bool = False
    sentry_dsn: str = ""


@dataclass
class MonitoringSettings:
    enable_prometheus: bool = True
    enable_grafana: bool = False
    health_check_interval: int = 30
    metrics_retention_days: int = 30


@dataclass
class SecuritySettings:
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    bcrypt_rounds: int = 12
    allowed_hosts: List[str] = field(default_factory=lambda: ["*"])
    rate_limit_per_minute: int = 60
    enable_cors: bool = True


@dataclass
class StorageSettings:
    data_dir: str = "data"
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 100
    backup_dir: str = "backups"


@dataclass
class Settings:
    environment: str = "development"
    app_name: str = "JARVIS AI"
    app_version: str = "3.0.0"
    debug: bool = False
    testing: bool = False

    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    redis: RedisSettings = field(default_factory=RedisSettings)
    server: ServerSettings = field(default_factory=ServerSettings)
    ai: AISettings = field(default_factory=AISettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    monitoring: MonitoringSettings = field(default_factory=MonitoringSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)
    storage: StorageSettings = field(default_factory=StorageSettings)


RULES: List[ConfigRule] = [
    # Environment
    ConfigRule("env", default="development", choices=["local", "development", "staging", "production", "test"], description="Deployment environment"),
    ConfigRule("app_name", default="JARVIS AI", description="Application name"),
    ConfigRule("app_version", default="3.0.0", description="Application version"),
    ConfigRule("debug", default=False, type_=bool, description="Debug mode"),
    ConfigRule("testing", default=False, type_=bool, description="Testing mode"),

    # Server
    ConfigRule("server.host", default="0.0.0.0", description="Server host"),
    ConfigRule("server.port", default=8000, type_=int, min_value=1, max_value=65535, description="Server port"),
    ConfigRule("server.workers", default=4, type_=int, min_value=1, description="Number of workers"),
    ConfigRule("server.cors_origins", default="*", description="CORS origins (comma-separated)"),
    ConfigRule("server.api_prefix", default="/api/v1", description="API prefix"),
    ConfigRule("server.log_level", default="info", choices=["debug", "info", "warning", "error", "critical"], description="Log level"),

    # Database
    ConfigRule("database.url", default="sqlite+aiosqlite:///./jarvis.db", description="Database URL"),
    ConfigRule("database.host", default="localhost", description="Database host"),
    ConfigRule("database.port", default=5432, type_=int, description="Database port"),
    ConfigRule("database.name", default="jarvis", description="Database name"),
    ConfigRule("database.user", default="jarvis", description="Database user"),
    ConfigRule("database.password", default="", sensitive=True, description="Database password"),
    ConfigRule("database.pool_size", default=5, type_=int, description="Connection pool size"),

    # Redis
    ConfigRule("redis.url", default="redis://localhost:6379/0", description="Redis URL"),
    ConfigRule("redis.host", default="localhost", description="Redis host"),
    ConfigRule("redis.port", default=6379, type_=int, description="Redis port"),
    ConfigRule("redis.password", default="", sensitive=True, description="Redis password"),

    # AI Providers
    ConfigRule("ai.default_model", default="auto", description="Default AI model"),
    ConfigRule("ai.ollama_url", default="http://localhost:11434", description="Ollama URL"),
    ConfigRule("ai.openai_key", default="", sensitive=True, description="OpenAI API key"),
    ConfigRule("ai.google_gemini_key", default="", sensitive=True, description="Google Gemini API key"),
    ConfigRule("ai.anthropic_key", default="", sensitive=True, description="Anthropic API key"),

    # Security
    ConfigRule("security.secret_key", default="change-me-in-production", sensitive=True, description="Secret key for JWT signing"),
    ConfigRule("security.jwt_expire_minutes", default=60, type_=int, description="JWT token expiry"),
    ConfigRule("security.rate_limit_per_minute", default=60, type_=int, description="Rate limit per minute"),

    # Logging
    ConfigRule("logging.level", default="info", choices=["debug", "info", "warning", "error", "critical"], description="Logging level"),
    ConfigRule("logging.format", default="json", choices=["json", "text"], description="Log format"),
    ConfigRule("logging.directory", default="logs", description="Log directory"),

    # Storage
    ConfigRule("storage.data_dir", default="data", description="Data directory"),
    ConfigRule("storage.upload_dir", default="uploads", description="Upload directory"),
    ConfigRule("storage.max_upload_size_mb", default=100, type_=int, description="Max upload size (MB)"),
]


def settings_from_loader(loader: Optional[ConfigLoader] = None) -> Settings:
    """Load settings from a ConfigLoader or create a default one."""
    if loader is None:
        loader = default_config_loader()
    loader.add_rules(RULES)
    config = loader.load()

    def g(key: str, default: Any = None) -> Any:
        return config.get(key, default)

    return Settings(
        environment=g("env", "development"),
        app_name=g("app_name", "JARVIS AI"),
        app_version=g("app_version", "3.0.0"),
        debug=g("debug", False),
        testing=g("testing", False),
        database=DatabaseSettings(
            url=g("database.url", "sqlite+aiosqlite:///./jarvis.db"),
            host=g("database.host", "localhost"),
            port=g("database.port", 5432),
            name=g("database.name", "jarvis"),
            user=g("database.user", "jarvis"),
            password=g("database.password", ""),
            pool_size=g("database.pool_size", 5),
            max_overflow=g("database.max_overflow", 10),
            echo=g("debug", False),
        ),
        redis=RedisSettings(
            url=g("redis.url", "redis://localhost:6379/0"),
            host=g("redis.host", "localhost"),
            port=g("redis.port", 6379),
            password=g("redis.password", ""),
            db=g("redis.db", 0),
            pool_max_size=g("redis.pool_max_size", 20),
        ),
        server=ServerSettings(
            host=g("server.host", "0.0.0.0"),
            port=g("server.port", 8000),
            workers=g("server.workers", 4),
            cors_origins=loader.get_list("server.cors_origins", ["*"]),
            api_prefix=g("server.api_prefix", "/api/v1"),
            debug=g("debug", False),
            log_level=g("server.log_level", "info"),
            reload=g("debug", False),
        ),
        ai=AISettings(
            default_model=g("ai.default_model", "auto"),
            ollama_url=g("ai.ollama_url", "http://localhost:11434"),
            openai_key=g("ai.openai_key", ""),
            google_gemini_key=g("ai.google_gemini_key", ""),
            anthropic_key=g("ai.anthropic_key", ""),
            huggingface_key=g("ai.huggingface_key", ""),
            replicate_key=g("ai.replicate_key", ""),
            embedding_model=g("ai.embedding_model", "sentence-transformers/all-MiniLM-L6-v2"),
            max_tokens=g("ai.max_tokens", 4096),
            temperature=g("ai.temperature", 0.7),
        ),
        logging=LoggingSettings(
            level=g("logging.level", "INFO").upper(),
            format=g("logging.format", "json"),
            directory=g("logging.directory", "logs"),
            max_bytes=g("logging.max_bytes", 10485760),
            backup_count=g("logging.backup_count", 10),
            enable_console=g("logging.enable_console", True),
            enable_file=g("logging.enable_file", True),
            enable_sentry=g("logging.enable_sentry", False),
            sentry_dsn=g("logging.sentry_dsn", ""),
        ),
        monitoring=MonitoringSettings(
            enable_prometheus=g("monitoring.enable_prometheus", True),
            enable_grafana=g("monitoring.enable_grafana", False),
            health_check_interval=g("monitoring.health_check_interval", 30),
            metrics_retention_days=g("monitoring.metrics_retention_days", 30),
        ),
        security=SecuritySettings(
            secret_key=g("security.secret_key", "change-me-in-production"),
            jwt_algorithm=g("security.jwt_algorithm", "HS256"),
            jwt_expire_minutes=g("security.jwt_expire_minutes", 60),
            bcrypt_rounds=g("security.bcrypt_rounds", 12),
            allowed_hosts=loader.get_list("security.allowed_hosts", ["*"]),
            rate_limit_per_minute=g("security.rate_limit_per_minute", 60),
            enable_cors=g("security.enable_cors", True),
        ),
        storage=StorageSettings(
            data_dir=g("storage.data_dir", "data"),
            upload_dir=g("storage.upload_dir", "uploads"),
            max_upload_size_mb=g("storage.max_upload_size_mb", 100),
            backup_dir=g("storage.backup_dir", "backups"),
        ),
    )


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings singleton."""
    global _settings
    if _settings is None:
        _settings = settings_from_loader()
    return _settings


def reset_settings():
    """Reset the settings singleton (useful for testing)."""
    global _settings
    _settings = None
