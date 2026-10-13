import pytest

from infrastructure.knowledge import ChunkConfig, KnowledgeIngestor
from infrastructure.knowledge.types import ChunkingStrategy


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap", "min_chunk_size"),
    [
        (0, 0, 0),
        (10, -1, 0),
        (10, 10, 0),
        (10, 0, -1),
        (10, 0, 11),
    ],
)
def test_chunk_config_rejects_invalid_sizes(chunk_size, chunk_overlap, min_chunk_size):
    with pytest.raises(ValueError):
        ChunkConfig(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            min_chunk_size=min_chunk_size,
        )


def test_fixed_size_ingestion_advances_with_valid_overlap():
    content = "Python is a versatile programming language."
    ingestor = KnowledgeIngestor(
        ChunkConfig(
            chunk_size=20,
            chunk_overlap=5,
            min_chunk_size=1,
            strategy=ChunkingStrategy.FIXED_SIZE,
        )
    )

    chunks = ingestor.ingest(content).chunks

    assert [chunk.content for chunk in chunks] == [
        content[0:20],
        content[15:35],
        content[30:],
    ]
