from __future__ import annotations
from typing import Protocol, List
import logging

from src.config import DATABRICKS_EMBEDDING_ENDPOINT, ENABLE_SEMANTIC_SEARCH, is_demo_mode
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
    if DATABRICKS_EMBEDDING_ENDPOINT:
        return DatabricksEmbeddingEngine(DATABRICKS_EMBEDDING_ENDPOINT)
    return MockEmbeddingEngine()

def generate_table_embeddings(tables: List[dict]) -> List[dict]:
    """Generate embeddings for a list of tables based on their name and description.

    Args:
        tables (List[dict]): A list of table metadata dictionaries containing 'full_name'
                             and optionally 'comment' or 'table_description'.

    Returns:
        List[dict]: A list of dictionaries containing 'table_full_name' and its vector 'embedding'.
    """
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
    """Perform a vector similarity search using the local DuckDB cache.

    Args:
        query (str): The text query to search for.
        top_n (int, optional): The maximum number of results to return. Defaults to 10.

    Returns:
        List[str]: A list of table full names (catalog.schema.table) sorted by semantic similarity.
    """
    # 1. Environment variable gate
    if not ENABLE_SEMANTIC_SEARCH:
        return []

    if is_demo_mode() or not _duckdb_available():
        return []

    try:
        # 2. Try to load VSS extension
        try:
            run_query("LOAD vss")
        except Exception:
            try:
                run_query("INSTALL vss")
                run_query("LOAD vss")
            except Exception as ex:
                logging.warning("Could not load vss extension: %s", ex)
                # We can still proceed, some DuckDB versions/setups might have cosine similarity built-in

        # 3. Retrieve embedding using get_embedding_engine()
        engine = get_embedding_engine()
        vector = engine.embed_text(query)
        if not vector:
            return []

        # 4. Perform vector similarity search using dynamic type-casting for the vector length!
        sql = f"SELECT table_full_name FROM tables_embedding_cache ORDER BY array_cosine_similarity(embedding, ?::FLOAT[{len(vector)}]) DESC LIMIT ?"
        df = run_query(sql, (vector, top_n))
        
        if df is not None and not df.empty:
            return df["table_full_name"].to_numpy().tolist()  # ⚡ Bolt: Use .to_numpy().tolist() for faster conversion instead of .tolist()
        return []
    except Exception as e:
        logging.error("Semantic search failed: %s", e)
        return []
