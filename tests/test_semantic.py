from unittest.mock import MagicMock, patch
from src.semantic import DatabricksEmbeddingEngine, MockEmbeddingEngine, get_embedding_engine, generate_table_embeddings, semantic_search
import os

def test_mock_embedding_engine():
    engine = MockEmbeddingEngine()

    # Test embed_text
    vec = engine.embed_text("hello")
    assert len(vec) == 384
    assert isinstance(vec[0], float)

    # Test embed_batch
    vecs = engine.embed_batch(["hello", "world", ""])
    assert len(vecs) == 3
    assert len(vecs[0]) == 384
    assert len(vecs[1]) == 384
    assert len(vecs[2]) == 384

def test_databricks_embedding_engine():
    # To test DatabricksEmbeddingEngine without actual credentials, mock the client
    with patch("src.semantic.DatabricksEmbeddingEngine.client", new_callable=MagicMock) as mock_client:
        engine = DatabricksEmbeddingEngine()

        # Mock successful response
        mock_response = MagicMock()
        mock_response.predictions = [{"embedding": [0.1] * 384}, {"embedding": [0.2] * 384}]
        mock_client.serving_endpoints.query.return_value = mock_response

        vecs = engine.embed_batch(["hello", "world"])
        assert len(vecs) == 2
        assert vecs[0] == [0.1] * 384

        # Mock empty batch
        vecs = engine.embed_batch([])
        assert vecs == []

        # Mock failure/fallback
        mock_client.serving_endpoints.query.side_effect = Exception("API error")
        vecs = engine.embed_batch(["hello", "world"])
        assert len(vecs) == 2
        assert vecs[0] == [0.0] * 384

@patch.dict(os.environ, {}, clear=True)
def test_get_embedding_engine_mock():
    engine = get_embedding_engine()
    assert isinstance(engine, MockEmbeddingEngine)

@patch.dict(os.environ, {"DATABRICKS_EMBEDDING_ENDPOINT": "my-endpoint"}, clear=True)
def test_get_embedding_engine_databricks():
    engine = get_embedding_engine()
    assert isinstance(engine, DatabricksEmbeddingEngine)
    assert engine.endpoint_name == "my-endpoint"

def test_generate_table_embeddings():
    tables = [
        {"full_name": "cat.schema.t1", "comment": "test table"},
        {"full_name": "cat.schema.t2", "table_description": "another test"}
    ]
    with patch("src.semantic.get_embedding_engine") as mock_get_engine:
        mock_engine = MagicMock()
        mock_engine.embed_batch.return_value = [[0.1] * 384, [0.2] * 384]
        mock_get_engine.return_value = mock_engine

        results = generate_table_embeddings(tables)

        assert len(results) == 2
        assert results[0]["table_full_name"] == "cat.schema.t1"
        assert results[0]["embedding"] == [0.1] * 384
        assert results[1]["table_full_name"] == "cat.schema.t2"

        # Verify texts sent to embed_batch
        expected_texts = ["cat.schema.t1: test table", "cat.schema.t2: another test"]
        mock_engine.embed_batch.assert_called_once_with(expected_texts)

def test_semantic_search_demo_mode():
    with patch("src.semantic.is_demo_mode", return_value=True):
        assert semantic_search("query") == []

def test_semantic_search_duckdb_unavailable():
    with patch("src.semantic.is_demo_mode", return_value=False):
        with patch("src.semantic._duckdb_available", return_value=False):
            assert semantic_search("query") == []

def test_semantic_search_exception():
    with patch("src.semantic.is_demo_mode", return_value=False):
        with patch("src.semantic._duckdb_available", return_value=True):
            with patch("src.semantic.run_query", side_effect=Exception("DB Error")):
                assert semantic_search("query") == []
