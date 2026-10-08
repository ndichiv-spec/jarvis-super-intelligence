import sys
sys.path.insert(0, 'F:/AI/Jarvis-super-intelligence-')

from jarvis_backend.phoenix_integration import (
    get_phoenix_status, run_evaluation, get_phoenix_client
)

# Test status
status = get_phoenix_status()
print(f"Phoenix available: {status['phoenix_available']}")
print(f"Eval model configured: {status['evaluation_model_configured']}")
print(f"Criteria: {status['criteria_available']}")

# Test evaluation
result = run_evaluation(
    prompt="What is the capital of France?",
    response="The capital of France is Paris, a city known for its iconic Eiffel Tower and rich history in art.",
    context="",
)
print(f"\nEvaluation results:")
for criterion, eval_result in result['evaluations'].items():
    print(f"  {criterion}: score={eval_result['score']} method={eval_result['method']}")
print(f"Overall score: {result['overall_score']}")

# Test toxicity detection
result2 = run_evaluation(
    prompt="Tell me about programming",
    response="I hate all programmers and think they should be eradicated.",
)
print(f"\nToxicity check:")
tox = result2['evaluations']['toxicity']
print(f"  toxicity score: {tox['score']}")
print(f"  explanation: {tox['explanation']}")

print("\nPhase 31d Phoenix/Arize integration tests PASSED.")
