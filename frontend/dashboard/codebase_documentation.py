"""
JARVIS Codebase Documentation and Presentation System
=================================================
Comprehensive codebase documentation, architecture visualization, and web dashboard
presentation for all JARVIS components, scripts, and architecture.

Features:
- Complete codebase inventory and documentation
- Interactive architecture visualization
- Real-time code metrics and statistics
- Searchable codebase index
- Component dependency mapping
- Script automation tracking
- Performance monitoring
- Web dashboard integration
"""

import asyncio
import json
import logging
import os
import ast
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid
import inspect
import importlib.util
from pathlib import Path
import networkx as nx
from collections import defaultdict, Counter
import re

logger = logging.getLogger(__name__)


class ComponentType(Enum):
    """Component type enumeration"""
    CORE = "core"
    API = "api"
    WEB = "web"
    MOBILE = "mobile"
    ANALYTICS = "analytics"
    SECURITY = "security"
    PERFORMANCE = "performance"
    MONITORING = "monitoring"
    TRAINING = "training"
    UTILITIES = "utilities"
    TESTS = "tests"
    DEPLOYMENT = "deployment"
    CONFIGURATION = "configuration"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    MESSAGING = "messaging"
    STORAGE = "storage"
    NETWORKING = "networking"
    AI = "ai"
    ML = "ml"
    NEUROMORPHIC = "neuromorphic"
    QUANTUM = "quantum"
    BLOCKCHAIN = "blockchain"
    IOT = "iot"
    EDGE = "edge"
    CLOUD = "cloud"


class ScriptType(Enum):
    """Script type enumeration"""
    DEPLOYMENT = "deployment"
    BUILD = "build"
    TEST = "test"
    MONITORING = "monitoring"
    BACKUP = "backup"
    MIGRATION = "migration"
    CLEANUP = "cleanup"
    AUTOMATION = "automation"
    UTILITIES = "utilities"
    DEVOPS = "devops"
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"
    PERFORMANCE = "performance"


@dataclass
class CodeComponent:
    """Code component documentation"""
    id: str
    name: str
    type: ComponentType
    file_path: str
    description: str
    functions: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)
    lines_of_code: int = 0
    complexity_score: float = 0.0
    test_coverage: float = 0.0
    last_modified: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScriptDocumentation:
    """Script documentation"""
    id: str
    name: str
    type: ScriptType
    file_path: str
    description: str
    purpose: str
    dependencies: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    usage_count: int = 0
    last_run: Optional[datetime] = None
    success_rate: float = 0.0
    execution_time: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)


@dataclass
class ArchitectureNode:
    """Architecture visualization node"""
    id: str
    name: str
    type: ComponentType
    level: int
    position: Dict[str, float] = field(default_factory=dict)
    connections: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    status: str = "active"
    color: str = "#3498db"


class CodebaseDocumentationSystem:
    """Comprehensive codebase documentation system"""
    
    def __init__(self, project_root: str = "c:\\Users\\Administrator\\Jarvis"):
        self.project_root = Path(project_root)
        self.components: Dict[str, CodeComponent] = {}
        self.scripts: Dict[str, ScriptDocumentation] = {}
        self.architecture_graph = nx.DiGraph()
        self.codebase_index: Dict[str, List[str]] = {}
        
        # Documentation cache
        self.last_scan_time = None
        self.scan_interval = timedelta(hours=1)
        
        # Initialize system
        self._initialize_system()
    
    def _initialize_system(self):
        """Initialize the documentation system"""
        try:
            # Create documentation directories
            self.docs_dir = self.project_root / "docs" / "codebase"
            self.docs_dir.mkdir(parents=True, exist_ok=True)
            
            # Initialize component type mapping
            self.component_type_mapping = self._create_component_type_mapping()
            
            # Initialize script type mapping
            self.script_type_mapping = self._create_script_type_mapping()
            
            logger.info("Codebase documentation system initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize documentation system: {e}")
    
    def _create_component_type_mapping(self) -> Dict[str, ComponentType]:
        """Create mapping from directory names to component types"""
        return {
            'core': ComponentType.CORE,
            'api': ComponentType.API,
            'web': ComponentType.WEB,
            'mobile': ComponentType.MOBILE,
            'analytics': ComponentType.ANALYTICS,
            'security': ComponentType.SECURITY,
            'performance': ComponentType.PERFORMANCE,
            'monitoring': ComponentType.MONITORING,
            'tests': ComponentType.TESTS,
            'deploy': ComponentType.DEPLOYMENT,
            'config': ComponentType.CONFIGURATION,
            'database': ComponentType.DATABASE,
            'cache': ComponentType.CACHE,
            'queue': ComponentType.QUEUE,
            'auth': ComponentType.AUTHENTICATION,
            'messaging': ComponentType.MESSAGING,
            'storage': ComponentType.STORAGE,
            'networking': ComponentType.NETWORKING,
            'ai': ComponentType.AI,
            'ml': ComponentType.ML,
            'neuromorphic': ComponentType.NEUROMORPHIC,
            'quantum': ComponentType.QUANTUM,
            'blockchain': ComponentType.BLOCKCHAIN,
            'iot': ComponentType.IOT,
            'edge': ComponentType.EDGE,
            'cloud': ComponentType.CLOUD
        }
    
    def _create_script_type_mapping(self) -> Dict[str, ScriptType]:
        """Create mapping from script names to script types"""
        return {
            'deploy': ScriptType.DEPLOYMENT,
            'build': ScriptType.BUILD,
            'test': ScriptType.TEST,
            'monitor': ScriptType.MONITORING,
            'backup': ScriptType.BACKUP,
            'migrate': ScriptType.MIGRATION,
            'clean': ScriptType.CLEANUP,
            'run': ScriptType.AUTOMATION,
            'setup': ScriptType.INFRASTRUCTURE,
            'security': ScriptType.SECURITY,
            'perf': ScriptType.PERFORMANCE,
            'install': ScriptType.UTILITIES,
            'start': ScriptType.DEPLOYMENT,
            'stop': ScriptType.DEPLOYMENT,
            'restart': ScriptType.DEPLOYMENT
        }
    
    async def scan_codebase(self, force: bool = False) -> Dict[str, Any]:
        """Comprehensive codebase scan and documentation"""
        try:
            # Check if scan is needed
            current_time = datetime.now()
            if not force and self.last_scan_time and (current_time - self.last_scan_time) < self.scan_interval:
                return {"status": "cached", "timestamp": self.last_scan_time.isoformat()}
            
            logger.info("Starting comprehensive codebase scan...")
            
            # Scan Python files
            await self._scan_python_files()
            
            # Scan scripts
            await self._scan_scripts()
            
            # Scan configuration files
            await self._scan_configuration_files()
            
            # Scan documentation files
            await self._scan_documentation_files()
            
            # Build architecture graph
            await self._build_architecture_graph()
            
            # Generate codebase index
            await self._generate_codebase_index()
            
            # Calculate metrics
            await self._calculate_metrics()
            
            # Save documentation
            await self._save_documentation()
            
            self.last_scan_time = current_time
            
            logger.info("Codebase scan completed successfully")
            
            return {
                "status": "completed",
                "timestamp": current_time.isoformat(),
                "components_found": len(self.components),
                "scripts_found": len(self.scripts),
                "architecture_nodes": self.architecture_graph.number_of_nodes()
            }
            
        except Exception as e:
            logger.error(f"Codebase scan failed: {e}")
            return {"status": "failed", "error": str(e)}
    
    async def _scan_python_files(self):
        """Scan all Python files in the project"""
        python_files = list(self.project_root.rglob("*.py"))
        
        for file_path in python_files:
            try:
                # Skip test files for now (they'll be scanned separately)
                if 'tests' in str(file_path):
                    continue
                
                # Parse the Python file
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Parse AST
                tree = ast.parse(content)
                
                # Extract component information
                component = await self._extract_component_info(file_path, tree, content)
                
                if component:
                    self.components[component.id] = component
                
            except Exception as e:
                logger.warning(f"Failed to scan Python file {file_path}: {e}")
    
    async def _extract_component_info(self, file_path: Path, tree: ast.AST, content: str) -> Optional[CodeComponent]:
        """Extract component information from Python file"""
        try:
            # Determine component type
            component_type = self._determine_component_type(file_path)
            
            # Extract functions
            functions = []
            classes = []
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
            
            # Calculate lines of code
            lines_of_code = len([line for line in content.split('\n') if line.strip()])
            
            # Calculate complexity score (simplified)
            complexity_score = self._calculate_complexity(tree)
            
            # Create component
            component = CodeComponent(
                id=str(file_path.relative_to(self.project_root)).replace('\\', '/').replace('/', '_'),
                name=file_path.stem,
                type=component_type,
                file_path=str(file_path.relative_to(self.project_root)),
                description=self._extract_description(tree, content),
                functions=functions,
                classes=classes,
                imports=imports,
                lines_of_code=lines_of_code,
                complexity_score=complexity_score,
                last_modified=datetime.fromtimestamp(file_path.stat().st_mtime),
                tags=self._extract_tags(file_path, content)
            )
            
            return component
            
        except Exception as e:
            logger.error(f"Failed to extract component info from {file_path}: {e}")
            return None
    
    def _determine_component_type(self, file_path: Path) -> ComponentType:
        """Determine component type from file path"""
        path_parts = file_path.parts
        
        for part in path_parts:
            part_lower = part.lower()
            if part_lower in self.component_type_mapping:
                return self.component_type_mapping[part_lower]
        
        # Default based on file location
        if 'api' in str(file_path).lower():
            return ComponentType.API
        elif 'core' in str(file_path).lower():
            return ComponentType.CORE
        elif 'web' in str(file_path).lower():
            return ComponentType.WEB
        elif 'mobile' in str(file_path).lower():
            return ComponentType.MOBILE
        else:
            return ComponentType.UTILITIES
    
    def _extract_description(self, tree: ast.AST, content: str) -> str:
        """Extract description from docstring or comments"""
        # Try to get module docstring
        if (tree.body and isinstance(tree.body[0], ast.Expr) and 
            isinstance(tree.body[0].value, ast.Constant)):
            return str(tree.body[0].value.value).strip()
        
        # Try to find first comment
        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                return stripped[3:-3].strip()
            elif stripped.startswith('#'):
                return stripped[1:].strip()
        
        return f"Component: {tree.__class__.__name__}"
    
    def _extract_tags(self, file_path: Path, content: str) -> List[str]:
        """Extract tags from file content and path"""
        tags = []
        
        # Extract from path
        path_parts = file_path.parts
        for part in path_parts:
            if part.lower() in ['ai', 'ml', 'quantum', 'neuromorphic', 'security', 'performance']:
                tags.append(part.lower())
        
        # Extract from content
        if 'advanced' in content.lower():
            tags.append('advanced')
        if 'quantum' in content.lower():
            tags.append('quantum')
        if 'neuromorphic' in content.lower():
            tags.append('neuromorphic')
        if 'security' in content.lower():
            tags.append('security')
        if 'performance' in content.lower():
            tags.append('performance')
        
        return list(set(tags))
    
    def _calculate_complexity(self, tree: ast.AST) -> float:
        """Calculate complexity score from AST"""
        complexity = 0.0
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                complexity += 1.0
                complexity += len(node.args.args) * 0.1
            elif isinstance(node, ast.ClassDef):
                complexity += 2.0
                complexity += len(node.bases) * 0.5
            elif isinstance(node, ast.If):
                complexity += 0.5
            elif isinstance(node, ast.For):
                complexity += 0.5
            elif isinstance(node, ast.While):
                complexity += 0.5
            elif isinstance(node, ast.Try):
                complexity += 0.3
        
        return min(10.0, complexity)
    
    async def _scan_scripts(self):
        """Scan all script files"""
        script_files = []
        
        # Look for common script patterns
        script_extensions = ['.py', '.sh', '.bat', '.cmd', '.ps1']
        
        for ext in script_extensions:
            script_files.extend(self.project_root.rglob(f"*{ext}"))
        
        for file_path in script_files:
            try:
                script = await self._extract_script_info(file_path)
                if script:
                    self.scripts[script.id] = script
            except Exception as e:
                logger.warning(f"Failed to scan script {file_path}: {e}")
    
    async def _extract_script_info(self, file_path: Path) -> Optional[ScriptDocumentation]:
        """Extract script information"""
        try:
            # Determine script type
            script_type = self._determine_script_type(file_path)
            
            # Read content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract basic info
            script = ScriptDocumentation(
                id=str(file_path.relative_to(self.project_root)).replace('\\', '/').replace('/', '_'),
                name=file_path.stem,
                type=script_type,
                file_path=str(file_path.relative_to(self.project_root)),
                description=self._extract_script_description(content),
                purpose=self._extract_script_purpose(content),
                created_at=datetime.fromtimestamp(file_path.stat().st_mtime),
                tags=self._extract_script_tags(file_path, content)
            )
            
            return script
            
        except Exception as e:
            logger.error(f"Failed to extract script info from {file_path}: {e}")
            return None
    
    def _determine_script_type(self, file_path: Path) -> ScriptType:
        """Determine script type from file name"""
        filename = file_path.stem.lower()
        
        for keyword, script_type in self.script_type_mapping.items():
            if keyword in filename:
                return script_type
        
        return ScriptType.UTILITIES
    
    def _extract_script_description(self, content: str) -> str:
        """Extract description from script content"""
        lines = content.split('\n')
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                return stripped[3:-3].strip()
            elif stripped.startswith('#'):
                return stripped[1:].strip()
        
        return f"Script: {len(content)} characters"
    
    def _extract_script_purpose(self, content: str) -> str:
        """Extract script purpose from content"""
        # Look for common purpose indicators
        if 'deploy' in content.lower():
            return "Deployment automation"
        elif 'test' in content.lower():
            return "Testing automation"
        elif 'monitor' in content.lower():
            return "Monitoring automation"
        elif 'backup' in content.lower():
            return "Backup automation"
        elif 'build' in content.lower():
            return "Build automation"
        else:
            return "General automation"
    
    def _extract_script_tags(self, file_path: Path, content: str) -> List[str]:
        """Extract tags from script"""
        tags = []
        
        # Extract from filename
        filename = file_path.stem.lower()
        if 'deploy' in filename:
            tags.append('deployment')
        if 'test' in filename:
            tags.append('testing')
        if 'monitor' in filename:
            tags.append('monitoring')
        if 'backup' in filename:
            tags.append('backup')
        
        # Extract from content
        if 'docker' in content.lower():
            tags.append('docker')
        if 'kubernetes' in content.lower():
            tags.append('kubernetes')
        if 'aws' in content.lower():
            tags.append('aws')
        if 'azure' in content.lower():
            tags.append('azure')
        
        return list(set(tags))
    
    async def _scan_configuration_files(self):
        """Scan configuration files"""
        config_extensions = ['.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf']
        
        for ext in config_extensions:
            config_files = self.project_root.rglob(f"*{ext}")
            
            for file_path in config_files:
                try:
                    # Add as configuration component
                    component = CodeComponent(
                        id=str(file_path.relative_to(self.project_root)).replace('\\', '/').replace('/', '_'),
                        name=file_path.stem,
                        type=ComponentType.CONFIGURATION,
                        file_path=str(file_path.relative_to(self.project_root)),
                        description=f"Configuration file: {file_path.suffix}",
                        last_modified=datetime.fromtimestamp(file_path.stat().st_mtime),
                        tags=['configuration', file_path.suffix[1:]]
                    )
                    
                    self.components[component.id] = component
                    
                except Exception as e:
                    logger.warning(f"Failed to scan config file {file_path}: {e}")
    
    async def _scan_documentation_files(self):
        """Scan documentation files"""
        doc_extensions = ['.md', '.rst', '.txt']
        
        for ext in doc_extensions:
            doc_files = self.project_root.rglob(f"*{ext}")
            
            for file_path in doc_files:
                try:
                    # Add as documentation component
                    component = CodeComponent(
                        id=str(file_path.relative_to(self.project_root)).replace('\\', '/').replace('/', '_'),
                        name=file_path.stem,
                        type=ComponentType.UTILITIES,
                        file_path=str(file_path.relative_to(self.project_root)),
                        description=f"Documentation file: {file_path.suffix}",
                        last_modified=datetime.fromtimestamp(file_path.stat().st_mtime),
                        tags=['documentation', file_path.suffix[1:]]
                    )
                    
                    self.components[component.id] = component
                    
                except Exception as e:
                    logger.warning(f"Failed to scan doc file {file_path}: {e}")
    
    async def _build_architecture_graph(self):
        """Build architecture dependency graph"""
        self.architecture_graph = nx.DiGraph()
        
        # Add nodes for all components
        for component in self.components.values():
            node = ArchitectureNode(
                id=component.id,
                name=component.name,
                type=component.type,
                level=self._calculate_component_level(component),
                metrics={
                    'lines_of_code': component.lines_of_code,
                    'complexity_score': component.complexity_score,
                    'functions': len(component.functions),
                    'classes': len(component.classes)
                },
                color=self._get_component_color(component.type)
            )
            
            self.architecture_graph.add_node(component.id, **node.__dict__)
        
        # Add edges for dependencies
        for component in self.components.values():
            for import_name in component.imports:
                # Find matching component
                for other_component in self.components.values():
                    if (import_name in other_component.name.lower() or 
                        other_component.name.lower() in import_name.lower()):
                        self.architecture_graph.add_edge(component.id, other_component.id)
    
    def _calculate_component_level(self, component: CodeComponent) -> int:
        """Calculate component level in architecture"""
        level_mapping = {
            ComponentType.CORE: 0,
            ComponentType.DATABASE: 1,
            ComponentType.CACHE: 1,
            ComponentType.QUEUE: 1,
            ComponentType.AUTHENTICATION: 2,
            ComponentType.AUTHORIZATION: 2,
            ComponentType.SECURITY: 2,
            ComponentType.API: 3,
            ComponentType.AI: 3,
            ComponentType.ML: 3,
            ComponentType.NEUROMORPHIC: 3,
            ComponentType.QUANTUM: 3,
            ComponentType.WEB: 4,
            ComponentType.MOBILE: 4,
            ComponentType.ANALYTICS: 4,
            ComponentType.MONITORING: 5,
            ComponentType.PERFORMANCE: 5,
            ComponentType.TESTS: 6,
            ComponentType.DEPLOYMENT: 6,
            ComponentType.UTILITIES: 6
        }
        
        return level_mapping.get(component.type, 3)
    
    def _get_component_color(self, component_type: ComponentType) -> str:
        """Get color for component type"""
        color_mapping = {
            ComponentType.CORE: "#e74c3c",
            ComponentType.API: "#3498db",
            ComponentType.WEB: "#2ecc71",
            ComponentType.MOBILE: "#f39c12",
            ComponentType.ANALYTICS: "#9b59b6",
            ComponentType.SECURITY: "#e67e22",
            ComponentType.PERFORMANCE: "#1abc9c",
            ComponentType.MONITORING: "#34495e",
            ComponentType.AI: "#8e44ad",
            ComponentType.ML: "#e74c3c",
            ComponentType.NEUROMORPHIC: "#f39c12",
            ComponentType.QUANTUM: "#9b59b6",
            ComponentType.DATABASE: "#2c3e50",
            ComponentType.CACHE: "#f1c40f",
            ComponentType.QUEUE: "#e67e22",
            ComponentType.AUTHENTICATION: "#3498db",
            ComponentType.AUTHORIZATION: "#e74c3c"
        }
        
        return color_mapping.get(component_type, "#95a5a6")
    
    async def _generate_codebase_index(self):
        """Generate searchable codebase index"""
        self.codebase_index = {
            'components_by_type': defaultdict(list),
            'components_by_tag': defaultdict(list),
            'scripts_by_type': defaultdict(list),
            'scripts_by_tag': defaultdict(list),
            'search_index': {}
        }
        
        # Index components
        for component in self.components.values():
            self.codebase_index['components_by_type'][component.type.value].append(component.id)
            
            for tag in component.tags:
                self.codebase_index['components_by_tag'][tag].append(component.id)
            
            # Add to search index
            search_text = f"{component.name} {component.description} {' '.join(component.tags)} {' '.join(component.functions)} {' '.join(component.classes)}"
            self.codebase_index['search_index'][component.id] = search_text.lower()
        
        # Index scripts
        for script in self.scripts.values():
            self.codebase_index['scripts_by_type'][script.type.value].append(script.id)
            
            for tag in script.tags:
                self.codebase_index['scripts_by_tag'][tag].append(script.id)
            
            # Add to search index
            search_text = f"{script.name} {script.description} {script.purpose} {' '.join(script.tags)}"
            self.codebase_index['search_index'][script.id] = search_text.lower()
    
    async def _calculate_metrics(self):
        """Calculate codebase metrics"""
        total_metrics = {
            'total_components': len(self.components),
            'total_scripts': len(self.scripts),
            'total_lines_of_code': sum(c.lines_of_code for c in self.components.values()),
            'average_complexity': sum(c.complexity_score for c in self.components.values()) / len(self.components) if self.components else 0,
            'components_by_type': Counter(c.type.value for c in self.components.values()),
            'scripts_by_type': Counter(s.type.value for s in self.scripts.values()),
            'most_complex_components': sorted(self.components.values(), key=lambda x: x.complexity_score, reverse=True)[:10],
            'largest_components': sorted(self.components.values(), key=lambda x: x.lines_of_code, reverse=True)[:10]
        }
        
        # Store metrics in components
        for component in self.components.values():
            component.metrics = {
                'rank_in_complexity': len([c for c in self.components.values() if c.complexity_score > component.complexity_score]),
                'rank_in_size': len([c for c in self.components.values() if c.lines_of_code > component.lines_of_code]),
                'type_count': total_metrics['components_by_type'][component.type.value]
            }
    
    async def _save_documentation(self):
        """Save documentation to files"""
        try:
            # Save components
            components_data = {
                component_id: {
                    'id': component.id,
                    'name': component.name,
                    'type': component.type.value,
                    'file_path': component.file_path,
                    'description': component.description,
                    'functions': component.functions,
                    'classes': component.classes,
                    'imports': component.imports,
                    'lines_of_code': component.lines_of_code,
                    'complexity_score': component.complexity_score,
                    'last_modified': component.last_modified.isoformat(),
                    'tags': component.tags,
                    'metrics': component.metrics
                }
                for component_id, component in self.components.items()
            }
            
            with open(self.docs_dir / 'components.json', 'w') as f:
                json.dump(components_data, f, indent=2)
            
            # Save scripts
            scripts_data = {
                script_id: {
                    'id': script.id,
                    'name': script.name,
                    'type': script.type.value,
                    'file_path': script.file_path,
                    'description': script.description,
                    'purpose': script.purpose,
                    'dependencies': script.dependencies,
                    'usage_count': script.usage_count,
                    'success_rate': script.success_rate,
                    'execution_time': script.execution_time,
                    'created_at': script.created_at.isoformat(),
                    'tags': script.tags
                }
                for script_id, script in self.scripts.items()
            }
            
            with open(self.docs_dir / 'scripts.json', 'w') as f:
                json.dump(scripts_data, f, indent=2)
            
            # Save architecture graph
            graph_data = {
                'nodes': [
                    {
                        'id': node_id,
                        'data': self.architecture_graph.nodes[node_id]
                    }
                    for node_id in self.architecture_graph.nodes()
                ],
                'edges': [
                    {
                        'source': edge[0],
                        'target': edge[1],
                        'data': self.architecture_graph.edges[edge]
                    }
                    for edge in self.architecture_graph.edges()
                ]
            }
            
            with open(self.docs_dir / 'architecture.json', 'w') as f:
                json.dump(graph_data, f, indent=2)
            
            # Save index
            with open(self.docs_dir / 'index.json', 'w') as f:
                # Convert defaultdict to regular dict for JSON serialization
                serializable_index = {}
                for key, value in self.codebase_index.items():
                    if isinstance(value, defaultdict):
                        serializable_index[key] = dict(value)
                    else:
                        serializable_index[key] = value
                
                json.dump(serializable_index, f, indent=2)
            
            logger.info(f"Documentation saved to {self.docs_dir}")
            
        except Exception as e:
            logger.error(f"Failed to save documentation: {e}")
    
    def get_component(self, component_id: str) -> Optional[CodeComponent]:
        """Get component by ID"""
        return self.components.get(component_id)
    
    def get_script(self, script_id: str) -> Optional[ScriptDocumentation]:
        """Get script by ID"""
        return self.scripts.get(script_id)
    
    def search_codebase(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """Search codebase"""
        query_lower = query.lower()
        results = []
        
        # Search in index
        for item_id, search_text in self.codebase_index['search_index'].items():
            if query_lower in search_text:
                if item_id in self.components:
                    results.append(('component', item_id))
                elif item_id in self.scripts:
                    results.append(('script', item_id))
        
        # Limit results
        results = results[:limit]
        
        # Format results
        formatted_results = []
        for result_type, result_id in results:
            if result_type == 'component':
                component = self.components[result_id]
                formatted_results.append({
                    'type': 'component',
                    'id': component.id,
                    'name': component.name,
                    'description': component.description,
                    'file_path': component.file_path,
                    'component_type': component.type.value
                })
            else:
                script = self.scripts[result_id]
                formatted_results.append({
                    'type': 'script',
                    'id': script.id,
                    'name': script.name,
                    'description': script.description,
                    'file_path': script.file_path,
                    'script_type': script.type.value
                })
        
        return {
            'query': query,
            'results': formatted_results,
            'total_found': len(results)
        }
    
    def get_architecture_overview(self) -> Dict[str, Any]:
        """Get architecture overview"""
        return {
            'total_nodes': self.architecture_graph.number_of_nodes(),
            'total_edges': self.architecture_graph.number_of_edges(),
            'components_by_level': {
                level: len([n for n, d in self.architecture_graph.nodes(data=True) if d['level'] == level])
                for level in range(7)  # 0-6 levels
            },
            'components_by_type': {
                component_type.value: len([n for n, d in self.architecture_graph.nodes(data=True) if d['type'] == component_type])
                for component_type in ComponentType
            },
            'graph_density': nx.density(self.architecture_graph),
            'is_connected': nx.is_connected(self.architecture_graph.to_undirected())
        }
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for web dashboard"""
        return {
            'overview': {
                'total_components': len(self.components),
                'total_scripts': len(self.scripts),
                'last_scan': self.last_scan_time.isoformat() if self.last_scan_time else None,
                'architecture_nodes': self.architecture_graph.number_of_nodes(),
                'architecture_edges': self.architecture_graph.number_of_edges()
            },
            'components': {
                'by_type': dict(Counter(c.type.value for c in self.components.values())),
                'by_complexity': {
                    'low': len([c for c in self.components.values() if c.complexity_score < 2]),
                    'medium': len([c for c in self.components.values() if 2 <= c.complexity_score < 5]),
                    'high': len([c for c in self.components.values() if c.complexity_score >= 5])
                },
                'total_lines': sum(c.lines_of_code for c in self.components.values())
            },
            'scripts': {
                'by_type': dict(Counter(s.type.value for s in self.scripts.values())),
                'total_usage': sum(s.usage_count for s in self.scripts.values()),
                'average_success_rate': sum(s.success_rate for s in self.scripts.values()) / len(self.scripts) if self.scripts else 0
            },
            'architecture': self.get_architecture_overview()
        }


# Global instance
_codebase_documentation = None


def get_codebase_documentation_system() -> CodebaseDocumentationSystem:
    """Get global codebase documentation system instance"""
    global _codebase_documentation
    if _codebase_documentation is None:
        _codebase_documentation = CodebaseDocumentationSystem()
    return _codebase_documentation
