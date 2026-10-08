"""
JARVIS Project Initializer
========================
Advanced project initialization and setup system for the JARVIS project
with comprehensive environment setup, dependency management, and configuration.

Features:
- Environment detection and setup
- Dependency installation and validation
- Configuration file generation
- Database setup and migration
- Security initialization
- Performance optimization
- Service registration
- Health check setup
- Logging configuration
- Component pre-initialization
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import shutil
import yaml
import sqlite3
import hashlib
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class EnvironmentType(Enum):
    """Environment type enumeration"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class SetupStatus(Enum):
    """Setup status enumeration"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SetupConfig:
    """Setup configuration"""
    project_root: str = str(Path(__file__).parent.parent)
    environment: EnvironmentType = EnvironmentType.DEVELOPMENT
    auto_install_deps: bool = True
    setup_database: bool = True
    setup_security: bool = True
    setup_logging: bool = True
    setup_monitoring: bool = True
    create_directories: bool = True
    generate_configs: bool = True
    validate_setup: bool = True
    backup_existing: bool = True
    verbose: bool = True


@dataclass
class SetupStep:
    """Setup step definition"""
    name: str
    description: str
    status: SetupStatus = SetupStatus.NOT_STARTED
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: float = 0.0
    output: str = ""
    error: Optional[str] = None
    dependencies: List[str] = None
    
    def start(self):
        """Start setup step"""
        self.status = SetupStatus.IN_PROGRESS
        self.start_time = datetime.now()
    
    def complete(self, output: str = ""):
        """Complete setup step"""
        self.status = SetupStatus.COMPLETED
        self.end_time = datetime.now()
        if self.start_time:
            self.duration = (self.end_time - self.start_time).total_seconds()
        self.output = output
    
    def fail(self, error: str):
        """Fail setup step"""
        self.status = SetupStatus.FAILED
        self.end_time = datetime.now()
        if self.start_time:
            self.duration = (self.end_time - self.start_time).total_seconds()
        self.error = error


class ProjectInitializer:
    """Advanced project initializer"""
    
    def __init__(self, config: SetupConfig):
        self.config = config
        self.project_root = Path(config.project_root)
        self.setup_steps: Dict[str, SetupStep] = {}
        self.setup_log = []
        
        # Define setup steps
        self._define_setup_steps()
    
    def _define_setup_steps(self):
        """Define all setup steps"""
        steps = [
            ("environment_detection", "Detect and validate environment"),
            ("directory_creation", "Create necessary directories"),
            ("dependency_installation", "Install Python dependencies"),
            ("configuration_generation", "Generate configuration files"),
            ("database_setup", "Setup and initialize database"),
            ("security_initialization", "Initialize security settings"),
            ("logging_setup", "Setup logging system"),
            ("monitoring_setup", "Setup monitoring system"),
            ("service_registration", "Register services"),
            ("health_check_setup", "Setup health checks"),
            ("validation", "Validate complete setup")
        ]
        
        for step_name, description in steps:
            self.setup_steps[step_name] = SetupStep(step_name, description)
    
    async def initialize_project(self) -> Dict[str, Any]:
        """Initialize the entire project"""
        logger.info("Starting JARVIS project initialization...")
        
        results = {}
        
        # Execute setup steps in order
        for step_name, step in self.setup_steps.items():
            try:
                logger.info(f"Executing step: {step_name}")
                step.start()
                
                # Execute step
                if step_name == "environment_detection":
                    result = await self._detect_environment()
                elif step_name == "directory_creation":
                    result = await self._create_directories()
                elif step_name == "dependency_installation":
                    result = await self._install_dependencies()
                elif step_name == "configuration_generation":
                    result = await self._generate_configurations()
                elif step_name == "database_setup":
                    result = await self._setup_database()
                elif step_name == "security_initialization":
                    result = await self._initialize_security()
                elif step_name == "logging_setup":
                    result = await self._setup_logging()
                elif step_name == "monitoring_setup":
                    result = await self._setup_monitoring()
                elif step_name == "service_registration":
                    result = await self._register_services()
                elif step_name == "health_check_setup":
                    result = await self._setup_health_checks()
                elif step_name == "validation":
                    result = await self._validate_setup()
                else:
                    result = {"success": False, "message": f"Unknown step: {step_name}"}
                
                if result.get("success", False):
                    step.complete(result.get("message", "Completed successfully"))
                    results[step_name] = result
                else:
                    step.fail(result.get("error", "Unknown error"))
                    results[step_name] = result
                    
                    # Stop on critical failure
                    if step_name in ["environment_detection", "dependency_installation"]:
                        logger.error(f"Critical step {step_name} failed, stopping initialization")
                        break
                
            except Exception as e:
                step.fail(str(e))
                results[step_name] = {"success": False, "error": str(e)}
                logger.error(f"Step {step_name} failed: {e}")
        
        # Generate summary
        summary = self._generate_setup_summary(results)
        
        logger.info("Project initialization completed")
        return summary
    
    async def _detect_environment(self) -> Dict[str, Any]:
        """Detect and validate environment"""
        try:
            logger.info("Detecting environment...")
            
            # Check Python version
            python_version = sys.version_info
            if python_version < (3, 8):
                return {
                    "success": False,
                    "error": f"Python {python_version.major}.{python_version.minor} is not supported. Requires Python 3.8+"
                }
            
            # Check project directory
            if not self.project_root.exists():
                return {
                    "success": False,
                    "error": f"Project directory {self.project_root} does not exist"
                }
            
            # Check write permissions
            if not os.access(self.project_root, os.W_OK):
                return {
                    "success": False,
                    "error": f"No write permissions for project directory {self.project_root}"
                }
            
            # Detect environment type
            env_type = self.config.environment
            env_file = self.project_root / ".env"
            
            if env_file.exists():
                with open(env_file, 'r') as f:
                    for line in f:
                        if line.startswith("JARVIS_ENV="):
                            env_type = EnvironmentType(line.split("=")[1].strip().lower())
                            break
            
            # Check system resources
            try:
                import psutil
                memory_gb = psutil.virtual_memory().total / (1024**3)
                cpu_cores = psutil.cpu_count()
                
                system_info = {
                    "python_version": f"{python_version.major}.{python_version.minor}.{python_version.micro}",
                    "platform": sys.platform,
                    "memory_gb": round(memory_gb, 2),
                    "cpu_cores": cpu_cores,
                    "environment": env_type.value
                }
                
                return {
                    "success": True,
                    "message": "Environment detected successfully",
                    "system_info": system_info
                }
                
            except ImportError:
                return {
                    "success": True,
                    "message": "Environment detected successfully (psutil not available for detailed info)"
                }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _create_directories(self) -> Dict[str, Any]:
        """Create necessary directories"""
        try:
            logger.info("Creating directories...")
            
            directories = [
                "logs",
                "data",
                "config",
                "cache",
                "temp",
                "backups",
                "uploads",
                "exports",
                "monitoring",
                "tests/reports",
                "docs/generated"
            ]
            
            created_dirs = []
            
            for dir_name in directories:
                dir_path = self.project_root / dir_name
                dir_path.mkdir(parents=True, exist_ok=True)
                created_dirs.append(str(dir_path))
                
                # Create .gitkeep if directory is empty
                if not any(dir_path.iterdir()):
                    (dir_path / ".gitkeep").touch()
            
            return {
                "success": True,
                "message": f"Created {len(created_dirs)} directories",
                "directories": created_dirs
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _install_dependencies(self) -> Dict[str, Any]:
        """Install Python dependencies"""
        try:
            logger.info("Installing dependencies...")
            
            requirements_file = self.project_root / "requirements.txt"
            
            if not requirements_file.exists():
                return {
                    "success": False,
                    "error": "requirements.txt file not found"
                }
            
            # Check if pip is available
            try:
                subprocess.run([sys.executable, "-m", "pip", "--version"], 
                             check=True, capture_output=True)
            except subprocess.CalledProcessError:
                return {
                    "success": False,
                    "error": "pip is not available"
                }
            
            # Install dependencies
            cmd = [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)]
            
            if self.config.verbose:
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, 
                                         stderr=subprocess.STDOUT, text=True)
                output, _ = process.communicate()
                success = process.returncode == 0
            else:
                result = subprocess.run(cmd, capture_output=True, text=True)
                output = result.stdout + result.stderr
                success = result.returncode == 0
            
            if success:
                return {
                    "success": True,
                    "message": "Dependencies installed successfully"
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to install dependencies: {output}"
                }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _generate_configurations(self) -> Dict[str, Any]:
        """Generate configuration files"""
        try:
            logger.info("Generating configuration files...")
            
            config_dir = self.project_root / "config"
            config_dir.mkdir(exist_ok=True)
            
            # Generate main configuration
            main_config = {
                "project": {
                    "name": "JARVIS",
                    "version": "3.0.0",
                    "environment": self.config.environment.value,
                    "debug": self.config.environment == EnvironmentType.DEVELOPMENT
                },
                "database": {
                    "url": f"sqlite:///{self.project_root}/data/jarvis.db",
                    "echo": False,
                    "pool_size": 10,
                    "max_overflow": 20
                },
                "api": {
                    "host": "0.0.0.0",
                    "port": 8080,
                    "workers": 4,
                    "cors_origins": ["*"],
                    "rate_limit": {"calls": 100, "period": 60}
                },
                "security": {
                    "secret_key": self._generate_secret_key(),
                    "algorithm": "HS256",
                    "access_token_expire_minutes": 30
                },
                "logging": {
                    "level": "INFO" if self.config.environment != EnvironmentType.DEVELOPMENT else "DEBUG",
                    "format": "json",
                    "file_path": "logs/jarvis.log",
                    "max_file_size": 10485760,
                    "backup_count": 5
                },
                "monitoring": {
                    "enabled": True,
                    "metrics_port": 9090,
                    "health_check_interval": 30
                }
            }
            
            config_file = config_dir / "config.yaml"
            with open(config_file, 'w') as f:
                yaml.dump(main_config, f, default_flow_style=False)
            
            # Generate environment file
            env_file = self.project_root / ".env"
            env_config = {
                "JARVIS_ENV": self.config.environment.value,
                "JARVIS_DEBUG": str(self.config.environment == EnvironmentType.DEVELOPMENT).lower(),
                "JARVIS_LOG_LEVEL": "DEBUG" if self.config.environment == EnvironmentType.DEVELOPMENT else "INFO",
                "JARVIS_DB_URL": f"sqlite:///{self.project_root}/data/jarvis.db",
                "JARVIS_SECRET_KEY": main_config["security"]["secret_key"],
                "JARVIS_API_HOST": "0.0.0.0",
                "JARVIS_API_PORT": "8080"
            }
            
            with open(env_file, 'w') as f:
                for key, value in env_config.items():
                    f.write(f"{key}={value}\n")
            
            return {
                "success": True,
                "message": "Configuration files generated successfully",
                "files": [str(config_file), str(env_file)]
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _setup_database(self) -> Dict[str, Any]:
        """Setup and initialize database"""
        try:
            logger.info("Setting up database...")
            
            data_dir = self.project_root / "data"
            data_dir.mkdir(exist_ok=True)
            
            db_path = data_dir / "jarvis.db"
            
            # Create database connection
            conn = sqlite3.connect(str(db_path))
            
            # Create basic tables
            cursor = conn.cursor()
            
            # Components table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS components (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Configuration table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS configuration (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    type TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    component_id TEXT,
                    message TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)
            
            # Metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    value REAL NOT NULL,
                    component_id TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    labels TEXT
                )
            """)
            
            conn.commit()
            conn.close()
            
            return {
                "success": True,
                "message": "Database setup completed successfully",
                "database_path": str(db_path)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _initialize_security(self) -> Dict[str, Any]:
        """Initialize security settings"""
        try:
            logger.info("Initializing security...")
            
            # Create security directory
            security_dir = self.project_root / "security"
            security_dir.mkdir(exist_ok=True)
            
            # Generate SSL certificates for development
            if self.config.environment == EnvironmentType.DEVELOPMENT:
                cert_path = security_dir / "cert.pem"
                key_path = security_dir / "key.pem"
                
                # Generate self-signed certificate
                try:
                    from cryptography.hazmat.primitives import hashes, serialization
                    from cryptography.hazmat.primitives.asymmetric import rsa
                    from cryptography import x509
                    from cryptography.x509.oid import NameOID
                    
                    # Generate private key
                    private_key = rsa.generate_private_key(
                        public_exponent=65537,
                        key_size=2048
                    )
                    
                    # Create certificate
                    subject = issuer = x509.Name([
                        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
                        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "JARVIS"),
                        x509.NameAttribute(NameOID.COMMON_NAME, "localhost")
                    ])
                    
                    cert = x509.CertificateBuilder().subject_name(
                        subject
                    ).issuer_name(
                        issuer
                    ).public_key(
                        private_key.public_key()
                    ).serial_number(
                        x509.random_serial_number()
                    ).not_valid_before(
                        datetime.utcnow()
                    ).not_valid_after(
                        datetime.utcnow() + timedelta(days=365)
                    ).add_extension(
                        x509.SubjectAlternativeName([
                            x509.DNSName("localhost"),
                            x509.DNSName("127.0.0.1")
                        ]),
                        critical=False
                    ).sign(private_key, hashes.SHA256())
                    
                    # Save certificate and key
                    with open(cert_path, "wb") as f:
                        f.write(cert.public_bytes(serialization.Encoding.PEM))
                    
                    with open(key_path, "wb") as f:
                        f.write(private_key.private_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PrivateFormat.PKCS8,
                            encryption_algorithm=serialization.NoEncryption()
                        ))
                    
                    security_files = [str(cert_path), str(key_path)]
                    
                except ImportError:
                    logger.warning("cryptography not available, skipping SSL certificate generation")
                    security_files = []
            else:
                security_files = []
            
            # Create security configuration
            security_config = {
                "encryption": {
                    "algorithm": "AES-256-GCM",
                    "key_derivation": "PBKDF2"
                },
                "authentication": {
                    "session_timeout": 3600,
                    "max_login_attempts": 5,
                    "lockout_duration": 900
                },
                "authorization": {
                    "rbac_enabled": True,
                    "default_permissions": ["read"]
                },
                "ssl": {
                    "enabled": self.config.environment != EnvironmentType.DEVELOPMENT,
                    "cert_path": "security/cert.pem",
                    "key_path": "security/key.pem"
                }
            }
            
            security_config_file = security_dir / "security.yaml"
            with open(security_config_file, 'w') as f:
                yaml.dump(security_config, f, default_flow_style=False)
            
            return {
                "success": True,
                "message": "Security initialized successfully",
                "files": security_files + [str(security_config_file)]
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _setup_logging(self) -> Dict[str, Any]:
        """Setup logging system"""
        try:
            logger.info("Setting up logging...")
            
            logs_dir = self.project_root / "logs"
            logs_dir.mkdir(exist_ok=True)
            
            # Create logging configuration
            logging_config = {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "standard": {
                        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
                    },
                    "json": {
                        "format": "%(asctime)s",
                        "class": "pythonjsonlogger.jsonlogger.JsonFormatter"
                    }
                },
                "handlers": {
                    "console": {
                        "level": "INFO",
                        "class": "logging.StreamHandler",
                        "formatter": "standard"
                    },
                    "file": {
                        "level": "DEBUG",
                        "class": "logging.handlers.RotatingFileHandler",
                        "filename": str(logs_dir / "jarvis.log"),
                        "maxBytes": 10485760,
                        "backupCount": 5,
                        "formatter": "json"
                    },
                    "error_file": {
                        "level": "ERROR",
                        "class": "logging.handlers.RotatingFileHandler",
                        "filename": str(logs_dir / "error.log"),
                        "maxBytes": 10485760,
                        "backupCount": 5,
                        "formatter": "json"
                    }
                },
                "loggers": {
                    "": {
                        "handlers": ["console", "file"],
                        "level": "INFO",
                        "propagate": False
                    },
                    "jarvis": {
                        "handlers": ["console", "file", "error_file"],
                        "level": "DEBUG",
                        "propagate": False
                    }
                }
            }
            
            logging_config_file = self.project_root / "config" / "logging.yaml"
            with open(logging_config_file, 'w') as f:
                yaml.dump(logging_config, f, default_flow_style=False)
            
            return {
                "success": True,
                "message": "Logging setup completed successfully",
                "config_file": str(logging_config_file)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _setup_monitoring(self) -> Dict[str, Any]:
        """Setup monitoring system"""
        try:
            logger.info("Setting up monitoring...")
            
            monitoring_dir = self.project_root / "monitoring"
            monitoring_dir.mkdir(exist_ok=True)
            
            # Create monitoring configuration
            monitoring_config = {
                "prometheus": {
                    "enabled": True,
                    "port": 9090,
                    "metrics_path": "/metrics"
                },
                "grafana": {
                    "enabled": False,
                    "port": 3000,
                    "admin_password": os.environ.get("GRAFANA_ADMIN_PASSWORD", "")
                },
                "health_checks": {
                    "enabled": True,
                    "interval": 30,
                    "timeout": 10
                },
                "alerts": {
                    "enabled": True,
                    "rules_file": "monitoring/alerts.yaml"
                },
                "dashboards": {
                    "enabled": True,
                    "directory": "monitoring/dashboards"
                }
            }
            
            monitoring_config_file = monitoring_dir / "monitoring.yaml"
            with open(monitoring_config_file, 'w') as f:
                yaml.dump(monitoring_config, f, default_flow_style=False)
            
            # Create basic alerts configuration
            alerts_config = {
                "groups": [
                    {
                        "name": "jarvis_alerts",
                        "rules": [
                            {
                                "alert": "HighCPUUsage",
                                "expr": "cpu_usage > 80",
                                "for": "5m",
                                "labels": {"severity": "warning"},
                                "annotations": {"summary": "High CPU usage detected"}
                            },
                            {
                                "alert": "HighMemoryUsage",
                                "expr": "memory_usage > 85",
                                "for": "5m",
                                "labels": {"severity": "warning"},
                                "annotations": {"summary": "High memory usage detected"}
                            },
                            {
                                "alert": "ComponentDown",
                                "expr": "up == 0",
                                "for": "1m",
                                "labels": {"severity": "critical"},
                                "annotations": {"summary": "Component is down"}
                            }
                        ]
                    }
                ]
            }
            
            alerts_config_file = monitoring_dir / "alerts.yaml"
            with open(alerts_config_file, 'w') as f:
                yaml.dump(alerts_config, f, default_flow_style=False)
            
            return {
                "success": True,
                "message": "Monitoring setup completed successfully",
                "files": [str(monitoring_config_file), str(alerts_config_file)]
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _register_services(self) -> Dict[str, Any]:
        """Register services"""
        try:
            logger.info("Registering services...")
            
            # This would integrate with the unified registry
            # For now, just create a service registry file
            services_config = {
                "services": [
                    {
                        "name": "jarvis_api",
                        "type": "api",
                        "host": "0.0.0.0",
                        "port": 8080,
                        "health_check": "/health",
                        "dependencies": ["database", "cache"]
                    },
                    {
                        "name": "jarvis_dashboard",
                        "type": "web",
                        "host": "0.0.0.0",
                        "port": 3000,
                        "health_check": "/api/health",
                        "dependencies": ["jarvis_api"]
                    },
                    {
                        "name": "jarvis_monitoring",
                        "type": "monitoring",
                        "host": "0.0.0.0",
                        "port": 9090,
                        "health_check": "/metrics",
                        "dependencies": []
                    }
                ]
            }
            
            services_file = self.project_root / "config" / "services.yaml"
            with open(services_file, 'w') as f:
                yaml.dump(services_config, f, default_flow_style=False)
            
            return {
                "success": True,
                "message": "Services registered successfully",
                "services_file": str(services_file)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _setup_health_checks(self) -> Dict[str, Any]:
        """Setup health checks"""
        try:
            logger.info("Setting up health checks...")
            
            health_config = {
                "checks": {
                    "database": {
                        "type": "database",
                        "connection_string": "sqlite:///data/jarvis.db",
                        "query": "SELECT 1",
                        "timeout": 5
                    },
                    "filesystem": {
                        "type": "filesystem",
                        "paths": ["logs", "data", "cache"],
                        "check_writable": True,
                        "timeout": 3
                    },
                    "memory": {
                        "type": "memory",
                        "threshold": 85,
                        "timeout": 2
                    },
                    "disk": {
                        "type": "disk",
                        "threshold": 90,
                        "path": "/",
                        "timeout": 3
                    }
                },
                "endpoints": {
                    "health": "/health",
                    "ready": "/ready",
                    "live": "/live"
                }
            }
            
            health_config_file = self.project_root / "config" / "health.yaml"
            with open(health_config_file, 'w') as f:
                yaml.dump(health_config, f, default_flow_style=False)
            
            return {
                "success": True,
                "message": "Health checks setup completed successfully",
                "config_file": str(health_config_file)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _validate_setup(self) -> Dict[str, Any]:
        """Validate complete setup"""
        try:
            logger.info("Validating setup...")
            
            validation_results = {}
            
            # Validate directories
            required_dirs = ["logs", "data", "config", "cache"]
            dirs_valid = True
            
            for dir_name in required_dirs:
                dir_path = self.project_root / dir_name
                if not dir_path.exists() or not dir_path.is_dir():
                    dirs_valid = False
                    break
            
            validation_results["directories"] = dirs_valid
            
            # Validate configuration files
            required_configs = ["config/config.yaml", ".env"]
            configs_valid = True
            
            for config_file in required_configs:
                config_path = self.project_root / config_file
                if not config_path.exists():
                    configs_valid = False
                    break
            
            validation_results["configurations"] = configs_valid
            
            # Validate database
            db_path = self.project_root / "data" / "jarvis.db"
            database_valid = db_path.exists()
            
            if database_valid:
                try:
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = cursor.fetchall()
                    conn.close()
                    database_valid = len(tables) > 0
                except:
                    database_valid = False
            
            validation_results["database"] = database_valid
            
            # Overall validation
            all_valid = all(validation_results.values())
            
            return {
                "success": all_valid,
                "message": "Setup validation completed" if all_valid else "Setup validation failed",
                "validation_results": validation_results
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _generate_secret_key(self, length: int = 32) -> str:
        """Generate secret key"""
        import secrets
        return secrets.token_urlsafe(length)
    
    def _generate_setup_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate setup summary"""
        total_steps = len(self.setup_steps)
        completed_steps = sum(1 for step in self.setup_steps.values() if step.status == SetupStatus.COMPLETED)
        failed_steps = sum(1 for step in self.setup_steps.values() if step.status == SetupStatus.FAILED)
        
        total_duration = sum(step.duration for step in self.setup_steps.values())
        
        return {
            "success": failed_steps == 0,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "success_rate": (completed_steps / total_steps * 100) if total_steps > 0 else 0,
            "total_duration": total_duration,
            "environment": self.config.environment.value,
            "project_root": str(self.project_root),
            "steps": {
                step_name: {
                    "status": step.status.value,
                    "duration": step.duration,
                    "error": step.error
                }
                for step_name, step in self.setup_steps.items()
            },
            "results": results
        }


# Main execution function
async def initialize_jarvis_project(config: Optional[SetupConfig] = None) -> Dict[str, Any]:
    """Initialize JARVIS project"""
    if config is None:
        config = SetupConfig()
    
    initializer = ProjectInitializer(config)
    return await initializer.initialize_project()


if __name__ == "__main__":
    import asyncio
    
    # Run initialization
    result = asyncio.run(initialize_jarvis_project())
    
    print("\n=== JARVIS Project Initialization ===")
    print(f"Success: {result['success']}")
    print(f"Completed Steps: {result['completed_steps']}/{result['total_steps']}")
    print(f"Success Rate: {result['success_rate']:.1f}%")
    print(f"Total Duration: {result['total_duration']:.2f}s")
    
    if not result['success']:
        print("\nFailed Steps:")
        for step_name, step_info in result['steps'].items():
            if step_info['status'] == 'failed':
                print(f"  - {step_name}: {step_info.get('error', 'Unknown error')}")
    
    print(f"\nProject initialized at: {result['project_root']}")
