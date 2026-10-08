#!/usr/bin/env python3
"""Initialize JARVIS persistence layer and verify connection."""

import sys
sys.path.insert(0, 'F:/AI/Jarvis-super-intelligence-')

try:
    from jarvis_backend.persistence import initialize_persistence
    tables = initialize_persistence()
    print(f"[OK] Initialized {len(tables)} persistence tables")
    for t in tables:
        print(f"  - {t}")
except ImportError as e:
    print(f"Import error: {e}")
    # Try direct import
    sys.path.insert(0, 'F:/AI/Jarvis-super-intelligence-/jarvis_backend')
    from persistence import initialize_persistence
    tables = initialize_persistence()
    print(f"[OK] Initialized {len(tables)} persistence tables")
    for t in tables:
        print(f"  - {t}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
