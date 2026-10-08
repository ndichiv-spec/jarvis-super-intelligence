#!/usr/bin/env python3
"""
PRODUCTION SIMULATION AUDIT
============================
Focuses on actual production code, not test/demos.
"""

import os
import re
from pathlib import Path
from collections import defaultdict

repo_root = Path('F:/AI/Jarvis-super-intelligence-')

# Exclude test files, demos, scripts, analysis tools
EXCLUDE_PATTERNS = [
    'tests/', 'test_', '_test.py', 
    'demo', 'demo', 
    'analyze', 'audit', 'census', 
    'verify', 'check_', 'complete_', 
    'evaluate', 'final_', 'migration_',
    'investigate', 'debug_', 'fix_',
    'create_remaining', 'retry_',
    'sample', 'sandbox', 
    '__pycache__', 'node_modules',
    '.venv', 'venv',
]

# Simulate indicators to find
SIMS = [
    'if False else',
    'placeholder',
    'fake response',
    'simulated',
    'demo_mode',
    'test_mode',
    'self.reliant',
    'TODO.*implement',
    'return \[\]',  # Empty list returns
    'return {}',   # Empty dict returns
]

def is_production_file(path):
    """Check if file is production code."""
    for pattern in EXCLUDE_PATTERNS:
        if pattern.lower() in str(path).lower():
            return False
    return True

def check_production_file(filepath):
    """Check production file for simulation issues."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except:
        return []
    
    issues = []
    
    # Check for placeholder patterns
    if 'if False else' in content:
        issues.append('Placeholder: "if False else" found')
    
    if 'placeholder' in content.lower() and '"""' not in content[:500]:
        # Comment-only placeholder is OK
        if '""".*placeholder' not in content:
            issues.append('Placeholder comment found')
    
    # Check for fake/hardcoded responses
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        if 'return []' in line and 'search' in content.lower():
            # Check if it's search returning empty list
            if 'def _search' in content:
                issues.append(f'Line {i}: Potential empty search return')
    
    return issues

def main():
    print("=" * 70)
    print("PRODUCTION SIMULATION AUDIT")
    print("=" * 70)
    
    production_issues = []
    
    # Check jarvis_backend/routers specifically
    routers_dir = repo_root / 'jarvis_backend' / 'routers'
    if routers_dir.exists():
        for py_file in routers_dir.glob('*.py'):
            issues = check_production_file(py_file)
            if issues:
                production_issues.append((str(py_file.relative_to(repo_root)), issues))
    
    # Check browser_engine.py
    browser_file = repo_root / 'jarvis_backend' / 'browser_engine.py'
    if browser_file.exists():
        issues = check_production_file(browser_file)
        if issues:
            production_issues.append(('browser_engine.py', issues))
    
    # Check core.py
    core_file = repo_root / 'jarvis_backend' / 'core.py'
    if core_file.exists():
        issues = check_production_file(core_file)
        if issues:
            production_issues.append(('core.py', issues))
    
    # Check gateway.py
    gateway_file = repo_root / 'jarvis_backend' / 'gateway.py'
    if gateway_file.exists():
        issues = check_production_file(gateway_file)
        if issues:
            production_issues.append(('gateway.py', issues))
    
    # Check providers directory
    providers_dir = repo_root / 'providers'
    if providers_dir.exists():
        for py_file in providers_dir.glob('**/*.py'):
            if py_file.is_file():
                issues = check_production_file(py_file)
                if issues:
                    rel = str(py_file.relative_to(repo_root))
                    production_issues.append((rel, issues))
    
    # Print results
    if production_issues:
        print("\n### PRODUCTION SIMULATION ISSUES ###\n")
        for filepath, issues in production_issues:
            print(f"\n{filepath}:")
            for issue in issues:
                print(f"  - {issue}")
    else:
        print("\nNo production simulation issues found!")
    
    print(f"\nTotal files checked: {len(list(routers_dir.glob('*.py'))) + 5 + len(list(providers_dir.rglob('*.py'))) if routers_dir.exists() and providers_dir.exists() else 'N/A'}")
    
    return production_issues

if __name__ == '__main__':
    issues = main()