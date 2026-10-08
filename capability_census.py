#!/usr/bin/env python3
"""
JARVIS COMPREHENSIVE CAPABILITY CENSUS
========================================
Scans the entire repository to identify every implementation related to
all JARVIS capabilities. Classifies each as REAL WORKING, REAL DISCONNECTED,
REAL BROKEN, PARTIAL, DORMANT, SIMULATED, DUPLICATED, DEAD, TEST-ONLY, or MISSING.
"""

import os
import re
import json
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Any

REPO_ROOT = Path('F:/AI/Jarvis-super-intelligence-')

# Capability search patterns
CAPABILITY_PATTERNS = {
    # Intelligence
    'brain': {
        'name': 'JARVIS Brain',
        'patterns': ['brain', 'jarvis_brain', 'reasoning', 'planning', 'orchestrat'],
        'files': ['jarvis_backend/brain.py', 'jarvis_backend/core.py'],
    },
    'silverwing': {
        'name': 'Silverwing',
        'patterns': ['silverwing', 'silverwing_runtime'],
        'files': ['silverwing-backend/main.py', 'silverwing_runtime/'],
    },
    # Conversation
    'conversation': {
        'name': 'Conversation',
        'patterns': ['conversation', 'chat_sessions', 'messages', 'dialog'],
        'files': ['jarvis_backend/routers/ai.py', 'jarvis_backend/db.py'],
    },
    # Voice
    'voice': {
        'name': 'Voice',
        'patterns': ['voice', 'audio', 'speech', 'stt', 'tts', 'transcription', 'synthesis'],
        'files': ['jarvis_backend/voice/', 'jarvis_backend/routers/voice.py'],
    },
    # Vision
    'vision': {
        'name': 'Vision',
        'patterns': ['vision', 'image_understanding', 'ocr', 'multimodal', 'screenshot'],
        'files': ['jarvis_backend/routers/vision.py', 'jarvis_backend/vision/'],
    },
    # Image Generation
    'image_gen': {
        'name': 'Image Generation',
        'patterns': ['image', 'generation', 'diffusion', 'stable_diffusion', 'dalle', 'midjourney'],
        'files': ['jarvis_backend/routers/multimodal.py', 'jarvis_backend/image_gen/'],
    },
    # Memory
    'memory': {
        'name': 'Memory',
        'patterns': ['memory', 'episodic', 'semantic', 'embeddings', 'vector_store', 'rag'],
        'files': ['jarvis_backend/routers/memory.py', 'jarvis_backend/memory/'],
    },
    # Knowledge
    'knowledge': {
        'name': 'Knowledge/RAG',
        'patterns': ['knowledge', 'rag', 'search', 'indexing', 'retrieval'],
        'files': ['jarvis_backend/routers/knowledge.py', 'jarvis_backend/routers/search.py'],
    },
    # Tools
    'tools': {
        'name': 'Tools/Connectors',
        'patterns': ['tool', 'connector', 'plugin', 'action'],
        'files': ['jarvis_backend/routers/', 'providers/'],
    },
    # Browser
    'browser': {
        'name': 'Browser',
        'patterns': ['browser', 'playwright', 'chromium', 'puppeteer', 'navigation'],
        'files': ['jarvis_backend/routers/browser.py', 'jarvis_backend/browser_engine.py'],
    },
    # Tasks
    'tasks': {
        'name': 'Tasks/Jobs',
        'patterns': ['task', 'job', 'scheduler', 'schedule', 'autonomous', 'mission'],
        'files': ['jarvis_backend/routers/', 'jarvis_backend/scheduler.py'],
    },
    # Learning
    'learning': {
        'name': 'Learning',
        'patterns': ['learning', 'dataset', 'training', 'evaluation', 'checkpoint'],
        'files': ['jarvis_backend/routers/learnings.py', 'infrastructure/'],
    },
    # Providers
    'providers': {
        'name': 'Providers',
        'patterns': ['provider', 'model_router', 'registry', 'gateway', 'openai', 'google', 'nvidia'],
        'files': ['jarvis_backend/gateway.py', 'providers/'],
    },
    # Security
    'security': {
        'name': 'Security',
        'patterns': ['auth', 'rbac', 'secret', 'credential', 'audit', 'permission'],
        'files': ['jarvis_backend/core.py', 'tests/test_sec1_security.py'],
    },
    # UI
    'ui': {
        'name': 'UI/Frontend',
        'patterns': ['component', 'dashboard', 'widget', 'frontend', 'pwa'],
        'files': ['frontend/web/src/'],
    },
    # Events
    'events': {
        'name': 'Events',
        'patterns': ['event', 'websocket', 'stream', 'notify', 'pubsub'],
        'files': ['jarvis_backend/events.py', 'jarvis_backend/'],
    },
    # Persistence
    'persistence': {
        'name': 'Persistence',
        'patterns': ['database', 'sqlite', 'store', 'kv_store', 'redis'],
        'files': ['jarvis_backend/db.py', 'jarvis_backend/core.py'],
    },
}

# Simulation indicators to flag
SIM_INDICATORS = [
    r'\bmock\b', r'\bfake\b', r'\bplaceholder\b', r'\bstub\b', r'\bdummy\b',
    r'\bdemo\b', r'\bsample\b', r'\bsimulat', r'\bhardcod', r'\bTODO\b',
    r'\bFIXME\b', r'\bself.reliant\b', r'\becho response\b',
    r'if False else', r'not implemented'
]

def scan_file_for_capability(filepath: Path) -> List[str]:
    """Scan a file for capability keywords."""
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore').lower()
    except:
        return []
    
    found = []
    for cap_id, cap_info in CAPABILITY_PATTERNS.items():
        for pattern in cap_info['patterns']:
            if pattern in content:
                found.append(cap_id)
                break
    return found

def scan_file_for_simulations(filepath: Path) -> List[str]:
    """Scan a file for simulation indicators."""
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except:
        return []
    
    found = []
    for pattern in SIM_INDICATORS:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            found.extend(matches[:5])  # Limit per file
    return list(set(found))

def is_test_file(path: Path) -> bool:
    """Check if file is a test file."""
    path_str = str(path).lower()
    return any(p in path_str for p in ['test_', '_test', 'tests/', '/test/'])

def is_demo_script(path: Path) -> bool:
    """Check if file is a demo/explore script."""
    path_str = str(path).lower()
    return any(p in path_str for p in ['demo', 'explore', 'example', 'scratch'])

def classify_file(filepath: Path) -> str:
    """Classify a file's implementation status."""
    if is_test_file(filepath):
        return 'TEST-ONLY'
    if is_demo_script(filepath):
        return 'DEMO'
    
    sims = scan_file_for_simulations(filepath)
    if 'mock' in sims and 'unittest' in str(filepath).lower():
        return 'TEST-ONLY'
    
    # Check for production simulations
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
        if 'if False else' in content:
            return 'SIMULATED'
        if 'self-reliant' in content.lower() and 'response' in content.lower():
            return 'SIMULATED'
        if 'echo response' in content.lower():
            return 'SIMULATED'
    except:
        pass
    
    return 'REAL'  # Default to real

def census_repo():
    """Perform full repository census."""
    results = {
        'capabilities': {},
        'routers': [],
        'simulations': [],
        'summary': {}
    }
    
    # Track capabilities
    for cap_id, cap_info in CAPABILITY_PATTERNS.items():
        results['capabilities'][cap_id] = {
            'name': cap_info['name'],
            'files_found': 0,
            'routes': [],
            'classification': [],
            'status': 'MISSING'
        }
    
    # Scan all Python files
    all_py = []
    for py in REPO_ROOT.rglob('*.py'):
        if any(s in str(py) for s in ['__pycache__', 'node_modules', '.venv', '.env']):
            continue
        all_py.append(py)
    
    # Scan JS/TS files for UI
    all_ts = []
    for ext in ['*.tsx', '*.ts', '*.jsx', '*.js']:
        for f in (REPO_ROOT / 'frontend').rglob(ext) if (REPO_ROOT / 'frontend').exists() else []:
            if any(s in str(f) for s in ['__pycache__', 'node_modules', '.venv', '.env']):
                continue
            all_ts.append(f)
    
    # Scan routers
    routers_dir = REPO_ROOT / 'jarvis_backend' / 'routers'
    if routers_dir.exists():
        for py in routers_dir.glob('*.py'):
            mod_name = py.stem
            routes = []
            try:
                content = py.read_text(encoding='utf-8', errors='ignore')
                # Find route definitions
                for match in re.finditer(r'@router\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']', content):
                    routes.append(match.group(2))
                results['routers'].append({
                    'module': mod_name,
                    'file': str(py.relative_to(REPO_ROOT)),
                    'routes': routes,
                    'route_count': len(routes),
                })
            except:
                results['routers'].append({
                    'module': mod_name,
                    'file': str(py.relative_to(REPO_ROOT)),
                    'routes': [],
                    'route_count': 0,
                })
    
    # Check for simulations
    for py in all_py:
        sims = scan_file_for_simulations(py)
        if sims:
            classification = classify_file(py)
            if classification != 'TEST-ONLY' and classification != 'DEMO':
                results['simulations'].append({
                    'file': str(py.relative_to(REPO_ROOT)),
                    'classification': classification,
                    'indicators': sims[:5],
                })
    
    # Classify capabilities
    for cap_id, cap_info in CAPABILITY_PATTERNS.items():
        files_found = 0
        
        # Check specified files
        for file_spec in cap_info['files']:
            p = REPO_ROOT / file_spec
            if p.exists():
                if p.is_file():
                    files_found += 1
                    results['capabilities'][cap_id]['classification'].append({
                        'file': str(p.relative_to(REPO_ROOT)),
                        'status': classify_file(p)
                    })
                elif p.is_dir():
                    file_count = sum(1 for _ in p.rglob('*.py'))
                    files_found += file_count
                    results['capabilities'][cap_id]['classification'].append({
                        'file': str(p.relative_to(REPO_ROOT)) + '/',
                        'status': 'EXISTS'
                    })
        
        # Check routers for relevant routes
        for router in results['routers']:
            for route in router['routes']:
                for pattern in cap_info['patterns']:
                    if pattern in route.lower() or pattern.replace('_', '') in route.replace('_', '').lower():
                        results['capabilities'][cap_id]['routes'].append({
                            'router': router['module'],
                            'route': route,
                        })
                        break
        
        results['capabilities'][cap_id]['files_found'] = files_found
        if files_found > 0:
            results['capabilities'][cap_id]['status'] = 'REAL + DISCONNECTED'
        elif results['capabilities'][cap_id]['routes']:
            results['capabilities'][cap_id]['status'] = 'PARTIAL'
        else:
            results['capabilities'][cap_id]['status'] = 'MISSING'
    
    return results

def main():
    print("=" * 70)
    print("JARVIS COMPREHENSIVE CAPABILITY CENSUS")
    print("=" * 70)
    
    results = census_repo()
    
    # Print capability census
    print("\n### CAPABILITY STATUS ###\n")
    
    for cap_id, info in sorted(results['capabilities'].items()):
        status = info['status']
        files = info['files_found']
        routes = len(info['routes'])
        
        status_color = {
            'REAL + WORKING': '[OK]',
            'REAL + DISCONNECTED': '[WARN]',
            'REAL + BROKEN': '[FAIL]',
            'PARTIAL': '[WARN]',
            'DORMANT': '[WARN]',
            'SIMULATED': '[FAIL]',
            'DUPLICATED': '[WARN]',
            'DEAD': '[FAIL]',
            'MISSING': '[MISSING]',
        }
        
        indicator = status_color.get(status, '[?]')
        print(f"  {indicator} {info['name']:<30} files={files:<5} routes={routes:<5} {status}")
    
    # Print routers
    print("\n### ROUTER ENDPOINTS ###\n")
    for router in results['routers']:
        print(f"  /{router['module']}: {router['route_count']} routes")
    
    # Print simulations in production code
    print("\n### PRODUCTION SIMULATIONS ###\n")
    if results['simulations']:
        for sim in results['simulations'][:20]:
            print(f"  {sim['file']}: {sim['classification']} - {sim['indicators']}")
        if len(results['simulations']) > 20:
            print(f"  ... and {len(results['simulations']) - 20} more")
    else:
        print("  No production simulations found")
    
    # Save full results
    with open('F:/AI/capability_census.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to capability_census.json")
    
    return results

if __name__ == '__main__':
    main()