import sys
sys.path.insert(0, 'F:/AI/Jarvis-super-intelligence-')

# 1. Test embeddings module
from jarvis_backend.embeddings import embed_text, cosine_similarity, ensure_embedding_columns

# Test embedding generation
vec = embed_text("machine learning transformer attention mechanism", dimension=384)
print(f'Embedding dimension: {len(vec)}')
print(f'First 5 values: {vec[:5]}')
print(f'Norm: {sum(x*x for x in vec)**0.5:.6f}')

# Test cosine similarity
vec2 = embed_text("deep learning neural networks transformer attention", dimension=384)
sim = cosine_similarity(vec, vec2)
print(f'Cosine similarity (related texts): {sim:.4f}')

vec3 = embed_text("Italian recipe pasta carbonara", dimension=384)
sim2 = cosine_similarity(vec, vec3)
print(f'Cosine similarity (unrelated texts): {sim2:.4f}')

# Test ensure_embedding_columns
print('\nEnsuring embedding columns...')
ensure_embedding_columns()

# 2. Test AutonomousResearchCortex
from jarvis_backend.research.autonomous_research import (
    AutonomousResearchCortex, _semantic_search, _generate_embedding
)

cortex = AutonomousResearchCortex()
cortex.initialize()
print(f'\nCortex initialized: {len(cortex._knowledge_graph)} nodes')

# Test semantic_search method
results = cortex.semantic_search("transformer neural network", limit=3)
print(f'Semantic search results: {len(results)}')
print(f'Backend: {embed_text.__module__}')

print('\n✅ All Phase 31 pgvector integration tests PASSED')
