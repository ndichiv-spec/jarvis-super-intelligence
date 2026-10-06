"""
JARVIS Automated Testing and Validation System
=============================================
Comprehensive automated testing and validation system for the JARVIS drive engine
with intelligent test discovery, execution, and reporting capabilities.

Features:
- Automated test discovery
- Multi-level testing (unit, integration, system)
- Test execution orchestration
- Performance testing
- Security testing
- Validation pipelines
- Test result aggregation
- Automated test reporting
- Continuous testing
- Test environment management
- Test data management
- Test coverage analysis
- Test failure analysis
- Test optimization
"""

import asyncio
import json
import logging
import time
import unittest
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union, Callable, Type
from dataclasses import dataclass, field
from enum import Enum
import uuid
import traceback
from pathlib import Path
import inspect
import importlib.util
from concurrent.futures import ThreadPoolExecutor, as_completed
import coverage
import pytest
import requests

logger = logging.getLogger(__name__)


class TestType(Enum):
    """Test type enumeration"""
    UNIT = "unit"
    INTEGRATION = "integration"
    SYSTEM = "system"
    PERFORMANCE = "performance"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    REGRESSION = "regression"
    SMOKE = "smoke"
    ACCEPTANCE = "acceptance"
    LOAD = "load"
    STRESS = "stress"


class TestStatus(Enum):
    """Test status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class TestPriority(Enum):
    """Test priority enumeration"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class TestCase:
    """Test case definition"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    test_type: TestType = TestType.UNIT
    file_path: str = ""
    class_name: str = ""
    method_name: str = ""
    line_number: int = 0
    priority: TestPriority = TestPriority.NORMAL
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    timeout: float = 30.0
    retry_count: int = 0
    max_retries: int = 3
    parameters: Dict[str, Any] = field(default_factory=dict)
    expected_result: Optional[Any] = None
    expected_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        if not self.name and self.method_name:
            self.name = self.method_name
    
    def can_retry(self) -> bool:
        """Check if test can be retried"""
        return self.retry_count < self.max_retries


@dataclass
class TestResult:
    """Test result data structure"""
    test_id: str
    test_name: str
    test_type: TestType
    status: TestStatus = TestStatus.PENDING
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: float = 0.0
    output: str = ""
    error: Optional[str] = None
    traceback: Optional[str] = None
    assertions: int = 0
    passed_assertions: int = 0
    failed_assertions: int = 0
    coverage_data: Dict[str, float] = field(default_factory=dict)
    performance_data: Dict[str, float] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.start_time and self.end_time:
            self.duration = (self.end_time - self.start_time).total_seconds()
    
    def mark_passed(self):
        """Mark test as passed"""
        self.status = TestStatus.PASSED
        self.end_time = datetime.now()
    
    def mark_failed(self, error: str, traceback_str: str):
        """Mark test as failed"""
        self.status = TestStatus.FAILED
        self.end_time = datetime.now()
        self.error = error
        self.traceback = traceback_str
    
    def mark_skipped(self, reason: str):
        """Mark test as skipped"""
        self.status = TestStatus.SKIPPED
        self.end_time = datetime.now()
        self.output = reason
    
    def mark_error(self, error: str, traceback_str: str):
        """Mark test as error"""
        self.status = TestStatus.ERROR
        self.end_time = datetime.now()
        self.error = error
        self.traceback = traceback_str


@dataclass
class TestSuite:
    """Test suite definition"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    test_type: TestType = TestType.UNIT
    test_cases: List[TestCase] = field(default_factory=list)
    setup_function: Optional[str] = None
    teardown_function: Optional[str] = None
    fixtures: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, Any] = field(default_factory=dict)
    parallel_execution: bool = False
    max_workers: int = 4
    timeout: float = 300.0
    retry_failed_tests: bool = True
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def add_test_case(self, test_case: TestCase):
        """Add test case to suite"""
        self.test_cases.append(test_case)
    
    def get_test_cases_by_priority(self, priority: TestPriority) -> List[TestCase]:
        """Get test cases by priority"""
        return [tc for tc in self.test_cases if tc.priority == priority]


@dataclass
class TestEnvironment:
    """Test environment definition"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    environment_type: str = "development"
    configuration: Dict[str, Any] = field(default_factory=dict)
    services: Dict[str, Any] = field(default_factory=dict)
    databases: Dict[str, Any] = field(default_factory=dict)
    network_config: Dict[str, Any] = field(default_factory=dict)
    security_config: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = False
    created_at: datetime = field(default_factory=datetime.now)


class AutomatedTestingSystem:
    """Automated testing and validation system"""
    
    def __init__(self, project_root: str = str(Path(__file__).parent.parent)):
        self.project_root = Path(project_root)
        self.test_suites: Dict[str, TestSuite] = {}
        self.test_environments: Dict[str, TestEnvironment] = {}
        self.test_results: Dict[str, TestResult] = {}
        self.coverage_collector = coverage.Coverage()
        
        # Test execution
        self.test_queue = asyncio.Queue()
        self.running_tests: Dict[str, asyncio.Task] = {}
        self.executor = ThreadPoolExecutor(max_workers=8)
        
        # Test discovery
        self.test_discoverer = TestDiscoverer()
        
        # Test reporting
        self.report_generator = TestReportGenerator()
        
        # Test metrics
        self.test_metrics = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0,
            "error_tests": 0,
            "total_duration": 0.0,
            "average_duration": 0.0,
            "coverage_percentage": 0.0,
            "last_run": None
        }
        
        # Initialize default environments
        self._initialize_environments()
    
    def _initialize_environments(self):
        """Initialize default test environments"""
        environments = [
            TestEnvironment(
                name="Development",
                environment_type="development",
                configuration={"debug": True, "verbose": True}
            ),
            TestEnvironment(
                name="Testing",
                environment_type="testing",
                configuration={"debug": False, "verbose": False}
            ),
            TestEnvironment(
                name="Integration",
                environment_type="integration",
                configuration={"debug": False, "verbose": True}
            )
        ]
        
        for env in environments:
            self.test_environments[env.id] = env
    
    async def discover_tests(self, test_paths: List[str] = None) -> Dict[str, List[TestCase]]:
        """Discover tests in specified paths"""
        if test_paths is None:
            test_paths = ["tests", "core/tests", "api/tests", "dashboard/tests"]
        
        discovered_tests = {}
        
        for test_path in test_paths:
            full_path = self.project_root / test_path
            if full_path.exists():
                path_tests = await self.test_discoverer.discover_tests(full_path)
                discovered_tests.update(path_tests)
        
        return discovered_tests
    
    async def create_test_suite(self, name: str, test_type: TestType, test_cases: List[TestCase], environment_id: str = None) -> str:
        """Create test suite"""
        suite = TestSuite(
            name=name,
            test_type=test_type,
            test_cases=test_cases,
            environment=self.test_environments.get(environment_id).configuration if environment_id else {}
        )
        
        self.test_suites[suite.id] = suite
        return suite.id
    
    async def run_test_suite(self, suite_id: str, environment_id: str = None) -> Dict[str, Any]:
        """Run test suite"""
        if suite_id not in self.test_suites:
            raise ValueError(f"Test suite {suite_id} not found")
        
        suite = self.test_suites[suite_id]
        environment = self.test_environments.get(environment_id) if environment_id else None
        
        # Start coverage collection
        self.coverage_collector.start()
        
        # Setup test environment
        if environment:
            await self._setup_test_environment(environment)
        
        # Run tests and update local results store
        results = await self._run_test_cases(suite, environment)
        for r in results:
            self.test_results[r.test_id] = r
        
        # Teardown test environment
        if environment:
            await self._teardown_test_environment(environment)
        
        # Stop coverage collection
        self.coverage_collector.stop()
        
        # Generate report
        report = await self.report_generator.generate_suite_report(suite, results)
        
        # Update metrics
        self._update_test_metrics(results)
        
        return report
    
    async def _setup_test_environment(self, environment: TestEnvironment):
        """Setup test environment"""
        environment.is_active = True
        
        # Set environment variables
        for key, value in environment.configuration.items():
            os.environ[key] = str(value)
        
        # Setup services
        for service_name, service_config in environment.services.items():
            await self._setup_service(service_name, service_config)
        
        # Setup databases
        for db_name, db_config in environment.databases.items():
            await self._setup_database(db_name, db_config)
    
    async def _teardown_test_environment(self, environment: TestEnvironment):
        """Teardown test environment"""
        # Teardown databases
        for db_name in environment.databases:
            await self._teardown_database(db_name)
        
        # Teardown services
        for service_name in environment.services:
            await self._teardown_service(service_name)
        
        # Clear environment variables
        for key in environment.configuration:
            if key in os.environ:
                del os.environ[key]
        
        environment.is_active = False
    
    async def _setup_service(self, service_name: str, service_config: Dict[str, Any]):
        """Setup test service"""
        # Implementation would depend on service type
        logger.info(f"Setting up service: {service_name}")
    
    async def _teardown_service(self, service_name: str):
        """Teardown test service"""
        logger.info(f"Tearing down service: {service_name}")
    
    async def _setup_database(self, db_name: str, db_config: Dict[str, Any]):
        """Setup test database"""
        logger.info(f"Setting up database: {db_name}")
    
    async def _teardown_database(self, db_name: str):
        """Teardown test database"""
        logger.info(f"Tearing down database: {db_name}")
    
    async def _run_test_cases(self, suite: TestSuite, environment: Optional[TestEnvironment]) -> List[TestResult]:
        """Run test cases in suite"""
        results = []
        
        if suite.parallel_execution:
            results = await self._run_tests_parallel(suite, environment)
        else:
            results = await self._run_tests_sequential(suite, environment)
        
        # Retry failed tests if enabled
        if suite.retry_failed_tests:
            results = await self._retry_failed_tests(suite, results, environment)
        
        return results
    
    async def _run_tests_sequential(self, suite: TestSuite, environment: Optional[TestEnvironment]) -> List[TestResult]:
        """Run tests sequentially"""
        results = []
        
        for test_case in suite.test_cases:
            result = await self._run_single_test(test_case, environment)
            results.append(result)
        
        return results
    
    async def _run_tests_parallel(self, suite: TestSuite, environment: Optional[TestEnvironment]) -> List[TestResult]:
        """Run tests in parallel"""
        results = []
        
        with ThreadPoolExecutor(max_workers=suite.max_workers) as executor:
            # Submit all tests
            futures = {
                executor.submit(self._run_single_test_sync, test_case, environment): test_case
                for test_case in suite.test_cases
            }
            
            # Collect results
            for future in as_completed(futures):
                test_case = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    # Create error result
                    result = TestResult(
                        test_id=test_case.id,
                        test_name=test_case.name,
                        test_type=test_case.test_type,
                        status=TestStatus.ERROR,
                        error=str(e),
                        traceback=traceback.format_exc()
                    )
                    results.append(result)
        
        return results
    
    def _run_single_test_sync(self, test_case: TestCase, environment: Optional[TestEnvironment]) -> TestResult:
        """Run single test synchronously"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._run_single_test(test_case, environment))
        finally:
            loop.close()
    
    async def _run_single_test(self, test_case: TestCase, environment: Optional[TestEnvironment]) -> TestResult:
        """Run single test case"""
        result = TestResult(
            test_id=test_case.id,
            test_name=test_case.name,
            test_type=test_case.test_type
        )
        result.start_time = datetime.now()
        
        try:
            # Mark as running
            result.status = TestStatus.RUNNING
            
            # Load test module
            module = self._load_test_module(test_case.file_path)
            
            # Get test class and method
            test_class = getattr(module, test_case.class_name) if test_case.class_name else None
            test_method = getattr(module, test_case.method_name) if test_case.method_name else None
            
            # Create test instance if class exists
            test_instance = None
            if test_class:
                test_instance = test_class()
                # Run setup if exists
                if hasattr(test_instance, 'setUp'):
                    test_instance.setUp()
            
            # Determine the actual method to call (handle instance methods)
            method_to_call = None
            if test_instance and hasattr(test_instance, test_case.method_name):
                method_to_call = getattr(test_instance, test_case.method_name)
            elif test_method:
                method_to_call = test_method
            
            if method_to_call:
                if asyncio.iscoroutinefunction(method_to_call):
                    await method_to_call()
                else:
                    method_to_call()
            
            # Run teardown if exists
            if test_instance and hasattr(test_instance, 'tearDown'):
                test_instance.tearDown()
            
            # Mark as passed
            result.mark_passed()
            
        except AssertionError as e:
            result.mark_failed(str(e), traceback.format_exc())
        except Exception as e:
            result.mark_error(str(e), traceback.format_exc())
        
        return result
    
    def _load_test_module(self, file_path: str):
        """Load test module"""
        module_path = Path(file_path)
        spec = importlib.util.spec_from_file_location("test_module", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    
    async def _retry_failed_tests(self, suite: TestSuite, results: List[TestResult], environment: Optional[TestEnvironment]) -> List[TestResult]:
        """Retry failed tests"""
        retry_results = []
        
        for result in results:
            if result.status in [TestStatus.FAILED, TestStatus.ERROR]:
                test_case = next((tc for tc in suite.test_cases if tc.id == result.test_id), None)
                if test_case and test_case.can_retry():
                    # Retry test
                    test_case.retry_count += 1
                    retry_result = await self._run_single_test(test_case, environment)
                    retry_results.append(retry_result)
                else:
                    retry_results.append(result)
            else:
                retry_results.append(result)
        
        return retry_results
    
    def _update_test_metrics(self, results: List[TestResult]):
        """Update test metrics"""
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed_tests = sum(1 for r in results if r.status == TestStatus.FAILED)
        skipped_tests = sum(1 for r in results if r.status == TestStatus.SKIPPED)
        error_tests = sum(1 for r in results if r.status == TestStatus.ERROR)
        
        total_duration = sum(r.duration for r in results)
        
        self.test_metrics.update({
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "skipped_tests": skipped_tests,
            "error_tests": error_tests,
            "total_duration": total_duration,
            "average_duration": total_duration / total_tests if total_tests > 0 else 0.0,
            "last_run": datetime.now().isoformat()
        })
        
        # Update coverage percentage if available
        try:
            self.test_metrics["coverage_percentage"] = self.coverage_collector.report()
        except:
            pass
    
    async def run_performance_tests(self, test_suite_id: str) -> Dict[str, Any]:
        """Run performance tests"""
        if test_suite_id not in self.test_suites:
            raise ValueError(f"Test suite {test_suite_id} not found")
        
        suite = self.test_suites[test_suite_id]
        results = []
        
        for test_case in suite.test_cases:
            if test_case.test_type == TestType.PERFORMANCE:
                result = await self._run_performance_test(test_case)
                results.append(result)
        
        return {
            "suite_id": test_suite_id,
            "test_type": TestType.PERFORMANCE.value,
            "results": [self._serialize_result(r) for r in results],
            "summary": self._generate_performance_summary(results)
        }
    
    async def _run_performance_test(self, test_case: TestCase) -> TestResult:
        """Run performance test"""
        result = TestResult(
            test_id=test_case.id,
            test_name=test_case.name,
            test_type=test_case.test_type
        )
        result.start_time = datetime.now()
        
        try:
            # Run test multiple times for performance measurement
            iterations = test_case.parameters.get('iterations', 5)
            durations = []
            
            for i in range(iterations):
                start_time = time.time()
                
                # Run the actual test
                await self._run_single_test(test_case)
                
                duration = time.time() - start_time
                durations.append(duration)
            
            # Calculate performance metrics
            avg_duration = sum(durations) / len(durations)
            min_duration = min(durations)
            max_duration = max(durations)
            
            result.performance_data = {
                "iterations": iterations,
                "average_duration": avg_duration,
                "min_duration": min_duration,
                "max_duration": max_duration,
                "durations": durations
            }
            
            result.mark_passed()
            
        except Exception as e:
            result.mark_error(str(e), traceback.format_exc())
        
        return result
    
    def _generate_performance_summary(self, results: List[TestResult]) -> Dict[str, Any]:
        """Generate performance test summary"""
        if not results:
            return {}
        
        all_durations = []
        for result in results:
            if result.performance_data and 'durations' in result.performance_data:
                all_durations.extend(result.performance_data['durations'])
        
        if not all_durations:
            return {}
        
        return {
            "total_tests": len(results),
            "passed_tests": sum(1 for r in results if r.status == TestStatus.PASSED),
            "average_duration": sum(all_durations) / len(all_durations),
            "min_duration": min(all_durations),
            "max_duration": max(all_durations),
            "total_iterations": len(all_durations)
        }
    
    async def run_security_tests(self, test_suite_id: str) -> Dict[str, Any]:
        """Run security tests"""
        if test_suite_id not in self.test_suites:
            raise ValueError(f"Test suite {test_suite_id} not found")
        
        suite = self.test_suites[test_suite_id]
        results = []
        
        for test_case in suite.test_cases:
            if test_case.test_type == TestType.SECURITY:
                result = await self._run_security_test(test_case)
                results.append(result)
        
        return {
            "suite_id": test_suite_id,
            "test_type": TestType.SECURITY.value,
            "results": [self._serialize_result(r) for r in results],
            "summary": self._generate_security_summary(results)
        }
    
    async def _run_security_test(self, test_case: TestCase) -> TestResult:
        """Run security test"""
        result = TestResult(
            test_id=test_case.id,
            test_name=test_case.name,
            test_type=test_case.test_type
        )
        result.start_time = datetime.now()
        
        try:
            # Run security-specific test logic
            await self._run_single_test(test_case)
            
            # Additional security checks
            security_checks = test_case.parameters.get('security_checks', [])
            for check in security_checks:
                await self._perform_security_check(check, result)
            
            result.mark_passed()
            
        except Exception as e:
            result.mark_error(str(e), traceback.format_exc())
        
        return result
    
    async def _perform_security_check(self, check: str, result: TestResult):
        """Perform individual security check"""
        # Implementation would depend on check type
        logger.info(f"Performing security check: {check}")
    
    def _generate_security_summary(self, results: List[TestResult]) -> Dict[str, Any]:
        """Generate security test summary"""
        return {
            "total_tests": len(results),
            "passed_tests": sum(1 for r in results if r.status == TestStatus.PASSED),
            "failed_tests": sum(1 for r in results if r.status == TestStatus.FAILED),
            "security_issues": []
        }
    
    def _serialize_result(self, result: TestResult) -> Dict[str, Any]:
        """Serialize test result"""
        return {
            "test_id": result.test_id,
            "test_name": result.test_name,
            "test_type": result.test_type.value,
            "status": result.status.value,
            "duration": result.duration,
            "error": result.error,
            "assertions": result.assertions,
            "coverage_data": result.coverage_data,
            "performance_data": result.performance_data
        }
    
    def get_test_metrics(self) -> Dict[str, Any]:
        """Get test metrics"""
        return self.test_metrics
    
    def get_test_results(self, suite_id: str = None) -> List[Dict[str, Any]]:
        """Get test results"""
        if suite_id:
            if suite_id in self.test_suites:
                suite = self.test_suites[suite_id]
                return [self._serialize_result(r) for r in self.test_results.values() 
                       if any(tc.id == r.test_id for tc in suite.test_cases)]
            return []
        
        return [self._serialize_result(r) for r in self.test_results.values()]
    
    def generate_test_report(self, suite_id: str, format: str = "json") -> str:
        """Generate test report"""
        if suite_id not in self.test_suites:
            raise ValueError(f"Test suite {suite_id} not found")
        
        suite = self.test_suites[suite_id]
        results = [r for r in self.test_results.values() 
                 if any(tc.id == r.test_id for tc in suite.test_cases)]
        
        if format == "html":
            return self.report_generator.generate_html_report(suite, results)
        elif format == "json":
            return json.dumps({
                "suite": {
                    "id": suite.id,
                    "name": suite.name,
                    "test_type": suite.test_type.value,
                    "test_count": len(suite.test_cases)
                },
                "results": [self._serialize_result(r) for r in results],
                "metrics": self.test_metrics
            }, indent=2)
        else:
            raise ValueError(f"Unsupported format: {format}")


class TestDiscoverer:
    """Test discovery system"""
    
    async def discover_tests(self, test_path: Path) -> Dict[str, List[TestCase]]:
        """Discover tests in path"""
        discovered = {}
        
        # Find all test files
        test_files = list(test_path.rglob("test_*.py"))
        
        for test_file in test_files:
            try:
                test_cases = await self._parse_test_file(test_file)
                component_name = self._extract_component_name(test_file)
                
                if component_name not in discovered:
                    discovered[component_name] = []
                
                discovered[component_name].extend(test_cases)
                
            except Exception as e:
                logger.error(f"Failed to parse test file {test_file}: {e}")
        
        return discovered
    
    async def _parse_test_file(self, test_file: Path) -> List[TestCase]:
        """Parse test file and extract test cases"""
        test_cases = []
        
        # Read file content
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse AST to find test functions
        import ast
        tree = ast.parse(content)
        
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                test_cases.append(self._create_test_case(node, test_file, content))
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name.startswith('test_'):
                        tc = self._create_test_case(item, test_file, content)
                        tc.class_name = node.name
                        test_cases.append(tc)
        
        return test_cases
    
    def _create_test_case(self, node: ast.FunctionDef, test_file: Path, content: str) -> TestCase:
        """Helper to create test case object from AST node"""
        test_type = self._determine_test_type(node.name, content)
        test_case = TestCase(
            name=node.name,
            method_name=node.name,
            file_path=str(test_file),
            line_number=node.lineno,
            test_type=test_type
        )
        
        # Extract docstring
        if (node.body and isinstance(node.body[0], ast.Expr) and 
            isinstance(node.body[0].value, ast.Constant)):
            test_case.description = str(node.body[0].value.value)
        
        return test_case
    
    def _determine_test_type(self, function_name: str, content: str) -> TestType:
        """Determine test type from function name and content"""
        name_lower = function_name.lower()
        content_lower = content.lower()
        
        if "performance" in name_lower or "benchmark" in name_lower:
            return TestType.PERFORMANCE
        elif "security" in name_lower or "auth" in name_lower:
            return TestType.SECURITY
        elif "integration" in name_lower or "api" in name_lower:
            return TestType.INTEGRATION
        elif "system" in name_lower or "e2e" in name_lower:
            return TestType.SYSTEM
        elif "load" in name_lower or "stress" in name_lower:
            return TestType.LOAD
        elif "regression" in name_lower:
            return TestType.REGRESSION
        elif "smoke" in name_lower:
            return TestType.SMOKE
        elif "acceptance" in name_lower:
            return TestType.ACCEPTANCE
        else:
            return TestType.UNIT
    
    def _extract_component_name(self, test_file: Path) -> str:
        """Extract component name from test file path"""
        for part in test_file.parts:
            if part in ['core', 'api', 'web', 'mobile', 'dashboard']:
                return part
        return 'unknown'


class TestReportGenerator:
    """Test report generator"""
    
    def generate_html_report(self, suite: TestSuite, results: List[TestResult]) -> str:
        """Generate HTML test report"""
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed_tests = sum(1 for r in results if r.status == TestStatus.FAILED)
        error_tests = sum(1 for r in results if r.status == TestStatus.ERROR)
        skipped_tests = sum(1 for r in results if r.status == TestStatus.SKIPPED)
        
        total_duration = sum(r.duration for r in results)
        
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Report - {suite.name}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
                .summary {{ margin: 20px 0; }}
                .test-results {{ margin-top: 20px; }}
                .test-row {{ border-bottom: 1px solid #ddd; padding: 10px 0; }}
                .passed {{ color: green; }}
                .failed {{ color: red; }}
                .error {{ color: orange; }}
                .skipped {{ color: blue; }}
                .performance {{ background-color: #f9f9f9; padding: 5px; border-radius: 3px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Test Report: {suite.name}</h1>
                <p>Test Type: {suite.test_type.value}</p>
                <p>Generated: {datetime.now().isoformat()}</p>
            </div>
            
            <div class="summary">
                <h2>Summary</h2>
                <p>Total Tests: {total_tests}</p>
                <p>Passed: {passed_tests} ({passed_tests/total_tests*100:.1f}%)</p>
                <p>Failed: {failed_tests}</p>
                <p>Errors: {error_tests}</p>
                <p>Skipped: {skipped_tests}</p>
                <p>Total Duration: {total_duration:.2f}s</p>
                <p>Average Duration: {total_duration/total_tests:.2f}s</p>
            </div>
            
            <div class="test-results">
                <h2>Test Results</h2>
                {self._generate_test_rows(results)}
            </div>
        </body>
        </html>
        """
        
        return html_template
    
    def _generate_test_rows(self, results: List[TestResult]) -> str:
        """Generate test result rows"""
        rows = ""
        
        for result in results:
            status_class = result.status.value
            performance_info = ""
            
            if result.performance_data:
                performance_info = f"""
                <div class="performance">
                    Performance: {result.performance_data.get('average_duration', 0):.3f}s avg
                </div>
                """
            
            rows += f"""
            <div class="test-row">
                <span class="{status_class}">{result.test_name}</span>
                <span>Duration: {result.duration:.3f}s</span>
                <span>Type: {result.test_type.value}</span>
                {performance_info}
                {f'<span>Error: {result.error}</span>' if result.error else ''}
            </div>
            """
        
        return rows
    
    async def generate_suite_report(self, suite: TestSuite, results: List[TestResult]) -> Dict[str, Any]:
        """Generate suite report"""
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed_tests = sum(1 for r in results if r.status == TestStatus.FAILED)
        error_tests = sum(1 for r in results if r.status == TestStatus.ERROR)
        skipped_tests = sum(1 for r in results if r.status == TestStatus.SKIPPED)
        
        return {
            "suite_id": suite.id,
            "suite_name": suite.name,
            "test_type": suite.test_type.value,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "error_tests": error_tests,
                "skipped_tests": skipped_tests,
                "pass_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
                "total_duration": sum(r.duration for r in results),
                "average_duration": sum(r.duration for r in results) / total_tests if total_tests > 0 else 0
            },
            "results": [
                {
                    "test_id": r.test_id,
                    "test_name": r.test_name,
                    "status": r.status.value,
                    "duration": r.duration,
                    "error": r.error,
                    "performance_data": r.performance_data
                }
                for r in results
            ]
        }


# Global instance
_automated_testing = None


def get_automated_testing_system(project_root: str = str(Path(__file__).parent.parent)) -> AutomatedTestingSystem:
    """Get global automated testing system instance"""
    global _automated_testing
    if _automated_testing is None:
        _automated_testing = AutomatedTestingSystem(project_root)
    return _automated_testing


# Example usage
async def demo_automated_testing():
    """Demonstrate automated testing system"""
    print("=== JARVIS Automated Testing System Demo ===")
    
    # Get testing system
    testing = get_automated_testing_system()
    
    # Discover tests
    discovered = await testing.discover_tests()
    print(f"Discovered tests in {len(discovered)} components")
    
    # Create test suite
    all_test_cases = []
    for component, tests in discovered.items():
        all_test_cases.extend(tests)
    
    if all_test_cases:
        suite_id = await testing.create_test_suite(
            "All Tests",
            TestType.UNIT,
            all_test_cases
        )
        
        # Run tests
        report = await testing.run_test_suite(suite_id)
        
        print(f"Test Results:")
        print(f"Total Tests: {report['summary']['total_tests']}")
        print(f"Passed: {report['summary']['passed_tests']}")
        print(f"Failed: {report['summary']['failed_tests']}")
        print(f"Pass Rate: {report['summary']['pass_rate']:.1f}%")
    
    # Get metrics
    metrics = testing.get_test_metrics()
    print(f"\nTest Metrics: {metrics}")


if __name__ == "__main__":
    asyncio.run(demo_automated_testing())
