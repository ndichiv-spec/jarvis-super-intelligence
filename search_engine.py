with open('jarvis_backend/self_improvement_engine.py', 'r') as f:
    lines = f.readlines()

# Check for run_cycle and evaluate_improvement
for i, line in enumerate(lines):
    s = line.strip()
    if 'run_cycle' in s.lower() or 'evaluate_improvement' in s.lower() or '_short_uuid' in s.lower() or 'def generate_lesson' in s or 'def evaluate_improvement' in s:
        print(f'L{i+1}: {line.rstrip()}')
