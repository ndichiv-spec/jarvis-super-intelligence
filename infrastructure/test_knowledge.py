"""Verify all knowledge management subsystems."""
import asyncio
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, '.')
from infrastructure.knowledge import *

print("=== Knowledge Management System Verification ===\n")

# 1. Types
doc = Document(id="d1", content="Hello world", metadata=DocumentMetadata(title="Test"))
assert doc.id == "d1"
assert doc.metadata.title == "Test"
assert doc.status == KnowledgeStatus.PENDING
assert not doc.is_expired
doc.expires_at = time.time() - 10
assert doc.is_expired
print("1. Document types: OK")

# 2. KnowledgeStore CRUD
store = KnowledgeStore()
d = store.create_document("Test content", user_id="user1")
assert d.id
assert store.get_document(d.id) is not None
store.update_document(d.id, confidence=0.95)
assert store.get_document(d.id).confidence == 0.95
assert len(store.list_documents()) == 1
store.delete_document(d.id)
assert store.get_document(d.id) is None
print("2. KnowledgeStore CRUD: OK")

# 3. Chunking + Ingestor
CHUNK_CONFIG = ChunkConfig(chunk_size=50, chunk_overlap=10, min_chunk_size=10, strategy=ChunkingStrategy.FIXED_SIZE)
ingestor = KnowledgeIngestor(CHUNK_CONFIG)
long_text = "Hello world. " * 50
doc = ingestor.ingest(long_text, metadata=DocumentMetadata(title="Chunk Test"))
assert len(doc.chunks) > 1
for c in doc.chunks:
    assert c.document_id == doc.id
    assert len(c.content) <= 50
    assert c.index >= 0
print(f"3. Ingestor: {len(doc.chunks)} chunks OK")

# 4. IndexManager (mock embedding)
indexer = IndexManager()
indexed = indexer.index_document(doc)
assert indexed == doc
for c in doc.chunks:
    assert c.embedding is not None
    assert len(c.embedding) == 384
assert indexer.stats.indexed_chunks == len(doc.chunks)
print("4. IndexManager (mock embeddings): OK")

# 5. Store chunks and search
store = KnowledgeStore()
d2 = store.create_document("The quick brown fox jumps over the lazy dog")
for i, c in enumerate(ingestor.ingest(d2.content).chunks):
    c.document_id = d2.id
    store.add_chunk(c)

query = SearchQuery(text="fox dog", top_k=5)
results = store.search(query)
assert len(results) > 0
assert results[0].score > 0
print(f"5. Text search: {len(results)} results OK")

# 6. Embedding search
results_emb = store.search_by_embedding(query)
print(f"6. Embedding search: {len(results_emb)} results (no embeddings on chunks)")

# Add embeddings for search
for chunk in store._chunks.values():
    chunk.embedding = indexer.embed_single(chunk.content)
results_emb = store.search_by_embedding(query)
assert len(results_emb) > 0
print(f"   After indexing: {len(results_emb)} results OK")

# Hybrid search
results_hybrid = store.hybrid_search(query)
assert len(results_hybrid) > 0
print(f"7. Hybrid search: {len(results_hybrid)} results OK")

# 8. Retriever
retriever = KnowledgeRetriever(store)
results = retriever.retrieve(query)
assert len(results) > 0
assert results[0].rank > 0
context = retriever.retrieve_context(query, max_tokens=500)
assert len(context) > 0
print(f"8. KnowledgeRetriever: {len(results)} results, {len(context)} ctx chars OK")

# 9. ContextManager
ctx_mgr = ContextManager(ContextWindowConfig(max_tokens=1000, max_turns=10))
ctx_mgr.add_system("You are a helpful assistant.")
ctx_mgr.add_user("Hello")
ctx_mgr.add_assistant("Hi there!")
ctx_mgr.add_user("What is AI?")
ctx_mgr.add_assistant("Artificial Intelligence...")
history = ctx_mgr.get_history()
assert len(history) >= 4  # system + user + assistant + user + assistant
assert ctx_mgr.get_turn_count() == 4
assert ctx_mgr.get_token_count() > 0
print(f"9. ContextManager: {len(history)} entries, {ctx_mgr.get_turn_count()} turns OK")

# 10. RAG Pipeline
rag = RAGPipeline(retriever, ctx_mgr)
result = asyncio.run(rag.generate("Tell me about the quick brown fox"))
assert result.answer
assert len(result.context.chunks) > 0
assert result.latency_ms >= 0
print(f"10. RAGPipeline: {len(result.answer)} chars, {result.latency_ms:.0f}ms OK")

# 11. LearningController
lc = LearningController(store, LearningConfig(require_approval=True))
request = lc.propose("Important knowledge to learn", KnowledgeSource.CONVERSATION, user_id="u1")
assert request.id
assert request.requires_approval
assert lc.get_pending_count() == 1

# Approve
doc = lc.approve(request.id, user_id="admin")
assert doc is not None
assert doc.status == KnowledgeStatus.ACTIVE
assert lc.get_pending_count() == 0
print("11. LearningController: propose/approve OK")

# Reject
request2 = lc.propose("Bad content", KnowledgeSource.WEB_SCRAPE, user_id="u1")
lc.reject(request2.id, reason="Low quality")
assert lc.get_pending_count() == 0
print("    Reject OK")

# Rollback
lc.rollback(doc.id, user_id="admin")
rolled = store.get_document(doc.id)
assert rolled.status == KnowledgeStatus.REJECTED
print("    Rollback OK")

# Learning disabled
lc.set_learning_enabled(False)
try:
    lc.propose("Test", KnowledgeSource.DOCUMENT)
    assert False, "Should raise"
except RuntimeError:
    pass
lc.set_learning_enabled(True)
print("    Learning disable/enable OK")

# 12. Validator
validator = KnowledgeValidator()
result = validator.validate(request)
assert 0 <= result.score <= 1
assert len(result.checks) >= 3
print(f"12. KnowledgeValidator: score={result.score:.2f}, {len(result.checks)} checks OK")

# 13. Retention
retention = RetentionManager(store)
stats = retention.estimate_storage()
assert stats["document_count"] >= 0
print(f"13. RetentionManager: {stats['document_count']} docs, {stats['estimated_mb']}MB OK")

# 14. MemoryBridge
bridge = MemoryBridge(store)
record = bridge.document_to_memory(doc)
assert record.key == f"knowledge:{doc.id}"
assert record.namespace == doc.metadata.source.value

doc_back = bridge.memory_to_document(record)
assert doc_back.id == doc.id
assert doc_back.content == doc.content
print("14. MemoryBridge: document<->memory OK")

# 15. Observability
obs = KnowledgeObservability()
obs.record("test", "store", duration_ms=5.5)
obs.record("search", "retrieval", duration_ms=12.3)
events = obs.get_events()
assert len(events) >= 2
metrics = obs.get_metrics()
assert metrics["total_events"] >= 2
assert "store:test" in metrics["counters"]
print(f"15. KnowledgeObservability: {metrics['total_events']} events, {len(metrics['latencies'])} latency keys OK")

# 16. Full pipeline integration
async def test_pipeline():
    # Ingest → Index → Store → Retrieve → RAG
    full_store = KnowledgeStore()
    full_ingestor = KnowledgeIngestor()
    full_indexer = IndexManager()
    full_retriever = KnowledgeRetriever(full_store)

    # Ingest multiple documents
    content1 = "Machine learning is a subset of artificial intelligence."
    content2 = "Deep learning uses neural networks with many layers."
    content3 = "Natural language processing enables computers to understand text."

    for i, c in enumerate([content1, content2, content3]):
        doc = full_ingestor.ingest(c, metadata=DocumentMetadata(title=f"Doc {i+1}"))
        full_indexer.index_document(doc)
        stored = full_store.create_document(
            doc.content, metadata=doc.metadata, status=KnowledgeStatus.ACTIVE,
        )
        for chunk in doc.chunks:
            stored.chunks.append(chunk)
            full_store.add_chunk(chunk)

    assert full_store.count(KnowledgeStatus.ACTIVE) == 3

    # Search
    q = SearchQuery(text="neural networks deep learning", top_k=5)
    results = full_retriever.retrieve(q)
    assert len(results) > 0

    # RAG
    rag_pipeline = RAGPipeline(full_retriever)
    result = await rag_pipeline.generate("Explain neural networks")
    assert result.answer
    assert len(result.context.chunks) > 0

    print(f"16. Full pipeline: {full_store.count()} docs, {len(results)} search results, {len(result.answer)} chars answer OK")

asyncio.run(test_pipeline())

print("\n=== All 16 knowledge subsystem tests passed ===")
