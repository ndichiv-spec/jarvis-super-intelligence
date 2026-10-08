#!/usr/bin/env python3
"""Quick summary of capability census."""
import json

with open('F:/AI/capability_census.json') as f:
    data = json.load(f)

print("=== CAPABILITY STATUS ===")
for cap_id, info in sorted(data['capabilities'].items()):
    name = info['name']
    files = info['files_found']
    routes = len(info['routes'])
    status = info['status']
    print(f"  {name:<30} files={files:<5} routes={routes:<5} {status}")

print("\n=== ROUTERS ===")
for r in data['routers']:
    print(f"  /{r['module']}: {r['route_count']} routes")

print(f"\nTotal simulations in production: {len(data['simulations'])}")
