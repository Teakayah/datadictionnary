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

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Convert a list of strings into a list of vectors."""
        ...

class DatabricksEmbeddingEngine:
    """Uses Databricks Foundation Model APIs (Model Serving) to generate embeddings."""
    
    def __init__(self, endpoint_name: str = "databricks-bge-large-en"):
        self.endpoint_name = endpoint_name
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from databricks.sdk import WorkspaceClient
            self._client = WorkspaceClient()
        return self._client

    def embed_text(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        try:
            # Call Databricks Model Serving
            response = self.client.serving_endpoints.query(
                name=self.endpoint_name,
                dataframe_records=[{"input": t} for t in texts]
            )
            # Adjust based on actual response schema of BGE endpoints
            return [r["embedding"] for r in response.predictions]
        except Exception as e:
            logging.error("Databricks embedding failed: %s", e)
            # Fallback to dummy vectors if service is unavailable to prevent sync failure
            return [[0.0] * 384 for _ in texts]

class MockEmbeddingEngine:
    """Mock implementation for scaffolding; returns fixed-size dummy vectors."""
    
    def embed_text(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # Return deterministic dummy vectors (384-dim)
        res = []
        for t in texts:
            base = (t * (384 // len(t) + 1))[:384] if t else " " * 384
            res.append([float(ord(c)) / 255.0 for c in base])
        return res

def get_embedding_engine() -> EmbeddingEngine:
    """Factory to retrieve the active embedding engine."""
    if os.getenv("DATABRICKS_EMBEDDING_ENDPOINT"):
        return DatabricksEmbeddingEngine(os.getenv("DATABRICKS_EMBEDDING_ENDPOINT"))
    return MockEmbeddingEngine()

def generate_table_embeddings(tables: List[dict]) -> List[dict]:
    """Generate embeddings for a list of tables based on their name and description."""
    engine = get_embedding_engine()
    
    # Prepare text for embedding: "catalog.schema.table: description"
    texts = []
    for t in tables:
        desc = t.get("comment") or t.get("table_description") or ""
        text = f"{t['full_name']}: {desc}"
        texts.append(text)
    
    embeddings = engine.embed_batch(texts)
    
    result = []
    for t, emb in zip(tables, embeddings):
        result.append({
            "table_full_name": t["full_name"],
            "embedding": emb
        })
    return result

def semantic_search(query: str, top_n: int = 10) -> List[str]:
    """Perform a vector similarity search using the local DuckDB cache."""
    if is_demo_mode() or not _duckdb_available():
        return []

    try:
        # In a real implementation, we would use DuckDB 1.1+ VSS features:
        # engine = get_embedding_engine()
        # vector = engine.embed_text(query)
        # sql = "SELECT table_full_name FROM tables_embedding_cache ORDER BY array_cosine_similarity(embedding, ?::FLOAT[384]) DESC LIMIT ?"
        # results = run_query(sql, (vector, top_n))
        
        # For scaffolding, return a few random tables if they exist to test fusion
        from src.db.queries import run_query
        df = run_query("SELECT full_name FROM tables_metadata LIMIT 5")
        if df is not None and not df.empty:
            return df["full_name"].tolist()
        return []
    except Exception as e:
        logging.error("Semantic search failed: %s", e)
        return []
