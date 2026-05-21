from __future__ import annotations
from typing import Protocol, List
import logging
import os

from src.config import is_demo_mode
from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import run_query

class EmbeddingEngine(Protocol):
    """Protocol for generating semantic embeddings from text."""
    
    def embed_text(self, text: str) -> List[float]:
        """Convert a string into a vector of floats."""
        ...

class MockEmbeddingEngine:
    """Mock implementation for scaffolding; returns fixed-size dummy vectors."""
    
    def embed_text(self, text: str) -> List[float]:
        # Return a deterministic dummy vector (384-dim)
        return [float(ord(c)) / 255.0 for c in (text * 10)[:384]]

def get_embedding_engine() -> EmbeddingEngine:
    """Factory to retrieve the active embedding engine."""
    # For now, always use mock. Real implementation would use databricks-embeddings-v2.
    return MockEmbeddingEngine()

def semantic_search(query: str, top_n: int = 10) -> List[str]:
    """Perform a vector similarity search using the local DuckDB cache."""
    if is_demo_mode() or not _duckdb_available():
        return []

    try:
        engine = get_embedding_engine()
        vector = engine.embed_text(query)
        
        # Placeholder for DuckDB vss call
        # In a real implementation, we would use:
        # SELECT table_full_name FROM tables_embedding_cache 
        # ORDER BY array_cosine_similarity(embedding, ?) DESC LIMIT ?
        
        logging.info("Semantic search scaffolded: query='%s', vector_len=%d", query, len(vector))
        return []
    except Exception as e:
        logging.error("Semantic search failed: %s", e)
        return []
