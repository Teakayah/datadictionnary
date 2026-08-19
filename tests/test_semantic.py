from unittest.mock import MagicMock, patch
from src.semantic import DatabricksEmbeddingEngine, MockEmbeddingEngine, get_embedding_engine, generate_table_embeddings, semantic_search
import os
import pandas as pd

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

@patch("src.semantic.DATABRICKS_EMBEDDING_ENDPOINT", "")
def test_get_embedding_engine_mock():
    engine = get_embedding_engine()
    assert isinstance(engine, MockEmbeddingEngine)

@patch("src.semantic.DATABRICKS_EMBEDDING_ENDPOINT", "my-endpoint")
def test_get_embedding_engine_databricks():
    with patch("src.semantic.DATABRICKS_EMBEDDING_ENDPOINT", "my-endpoint"):
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

@patch("src.semantic.ENABLE_SEMANTIC_SEARCH", False)
def test_semantic_search_disabled():
    assert semantic_search("query") == []

@patch("src.semantic.ENABLE_SEMANTIC_SEARCH", True)
def test_semantic_search_demo_mode():
    with patch("src.semantic.is_demo_mode", return_value=True):
        assert semantic_search("query") == []

@patch("src.semantic.ENABLE_SEMANTIC_SEARCH", True)
def test_semantic_search_duckdb_unavailable():
    with patch("src.semantic.is_demo_mode", return_value=False):
        with patch("src.semantic._duckdb_available", return_value=False):
            assert semantic_search("query") == []

@patch("src.semantic.ENABLE_SEMANTIC_SEARCH", True)
def test_semantic_search_exception():
    with patch("src.semantic.is_demo_mode", return_value=False):
        with patch("src.semantic._duckdb_available", return_value=True):
            with patch("src.semantic.run_query", side_effect=Exception("DB Error")):
                assert semantic_search("query") == []


def test_search_all_metadata_with_semantic_search():
    from src.db.queries import search_all_metadata
    
    # Clear Streamlit cache to ensure our patches are active
    search_all_metadata.clear()

    # 1. Test when ENABLE_SEMANTIC_SEARCH is false/disabled
    with patch.dict(os.environ, {"ENABLE_SEMANTIC_SEARCH": "false"}):
        with patch("src.db.queries._search_keywords") as mock_keywords:
            with patch("src.semantic.semantic_search") as mock_semantic:
                dummy_df = pd.DataFrame({"full_name": ["cat.sch.tab1"], "table_description": ["desc"]})
                mock_keywords.return_value = dummy_df
                
                res = search_all_metadata("some-query", ("group1",))
                
                assert isinstance(res, pd.DataFrame)
                assert res.iloc[0]["full_name"] == "cat.sch.tab1"
                mock_keywords.assert_called_once_with("some-query", ("group1",))
                mock_semantic.assert_not_called()

    # Clear Streamlit cache again
    search_all_metadata.clear()

    # 2. Test when ENABLE_SEMANTIC_SEARCH is true/enabled
    with patch.dict(os.environ, {"ENABLE_SEMANTIC_SEARCH": "true"}):
        with patch("src.db.queries._search_keywords") as mock_keywords:
            with patch("src.semantic.semantic_search") as mock_semantic:
                with patch("src.db.queries._fetch_metadata_for_fns") as mock_fetch:
                    dummy_keyword_df = pd.DataFrame({"full_name": ["cat.sch.tab1"], "table_description": ["desc"]})
                    mock_keywords.return_value = dummy_keyword_df
                    mock_semantic.return_value = ["cat.sch.tab1"]
                    
                    res = search_all_metadata("some-query", ("group1",))
                    
                    # RRF or fallback behavior: when keyword search returns a non-empty df,
                    # search_all_metadata currently returns keyword results (simple weighted fusion placeholder)
                    assert isinstance(res, pd.DataFrame)
                    assert res.iloc[0]["full_name"] == "cat.sch.tab1"
                    mock_keywords.assert_called_once_with("some-query", ("group1",))
                    mock_semantic.assert_called_once_with("some-query")
                    mock_fetch.assert_not_called()

    # Clear Streamlit cache again
    search_all_metadata.clear()

    # 3. Test when ENABLE_SEMANTIC_SEARCH is true/enabled and keyword search returns nothing
    with patch.dict(os.environ, {"ENABLE_SEMANTIC_SEARCH": "true"}):
        with patch("src.db.queries._search_keywords") as mock_keywords:
            with patch("src.semantic.semantic_search") as mock_semantic:
                with patch("src.db.queries._fetch_metadata_for_fns") as mock_fetch:
                    mock_keywords.return_value = pd.DataFrame()
                    mock_semantic.return_value = ["cat.sch.tab1"]
                    dummy_fetch_df = pd.DataFrame({"full_name": ["cat.sch.tab1"], "table_description": ["desc"]})
                    mock_fetch.return_value = dummy_fetch_df
                    
                    res = search_all_metadata("some-query", ("group1",))
                    
                    assert isinstance(res, pd.DataFrame)
                    assert res.iloc[0]["full_name"] == "cat.sch.tab1"
                    mock_keywords.assert_called_once_with("some-query", ("group1",))
                    mock_semantic.assert_called_once_with("some-query")
                    mock_fetch.assert_called_once_with(["cat.sch.tab1"], ("group1",))


def test_hybrid_fusion_semantic_results_influence_ranking():
    """A strong semantic hit must outrank a keyword hit with a higher BM25 score."""
    from src.db.queries import search_all_metadata

    search_all_metadata.clear()

    keyword_df = pd.DataFrame(
        {
            "full_name": ["cat.sch.kw_winner", "cat.sch.sem_winner"],
            "table_description": ["keyword favourite", "semantic favourite"],
            "_score": [3, 2],
        }
    )

    with patch.dict(os.environ, {"ENABLE_SEMANTIC_SEARCH": "true"}):
        with patch("src.db.queries._search_keywords", return_value=keyword_df.copy()):
            # BM25 alone (semantic disabled inside semantic_search → []) keeps kw_winner first
            with patch("src.semantic.semantic_search", return_value=[]):
                bm25_only = search_all_metadata("some-query", ("group1",))
            search_all_metadata.clear()

        with patch("src.db.queries._search_keywords", return_value=keyword_df.copy()):
            # Semantic ranks sem_winner first: 0.7*0.4 + 0.3*1.0 = 0.58 > 0.7*0.6 = 0.42
            with patch(
                "src.semantic.semantic_search", return_value=["cat.sch.sem_winner"]
            ):
                hybrid = search_all_metadata("some-query", ("group1",))
            search_all_metadata.clear()

    assert bm25_only["full_name"].tolist() == ["cat.sch.kw_winner", "cat.sch.sem_winner"]
    assert hybrid["full_name"].tolist() == ["cat.sch.sem_winner", "cat.sch.kw_winner"]
    assert "_score" not in hybrid.columns
    assert "_hybrid_score" not in hybrid.columns


def test_hybrid_fusion_appends_semantic_only_hits():
    """Semantic hits missing from keyword results are fetched and appended."""
    from src.db.queries import search_all_metadata

    search_all_metadata.clear()

    keyword_df = pd.DataFrame(
        {
            "full_name": ["cat.sch.kw_only"],
            "table_description": ["keyword hit"],
            "_score": [5],
        }
    )
    fetched_df = pd.DataFrame(
        {
            "full_name": ["cat.sch.sem_only"],
            "table_description": ["semantic hit"],
            "_score": [1],
        }
    )

    with patch.dict(os.environ, {"ENABLE_SEMANTIC_SEARCH": "true"}):
        with patch("src.db.queries._search_keywords", return_value=keyword_df):
            with patch(
                "src.semantic.semantic_search", return_value=["cat.sch.sem_only"]
            ):
                with patch(
                    "src.db.queries._fetch_metadata_for_fns", return_value=fetched_df
                ) as mock_fetch:
                    res = search_all_metadata("some-query", ("group1",))
        search_all_metadata.clear()

    mock_fetch.assert_called_once_with(["cat.sch.sem_only"], ("group1",))
    # Exact keyword match (0.7) still beats semantic-only hit (0.3), but both present
    assert res["full_name"].tolist() == ["cat.sch.kw_only", "cat.sch.sem_only"]


def test_databricks_embedding_engine_client_property():
    import sys
    from unittest.mock import MagicMock
    with patch.dict(sys.modules, {"databricks.sdk": MagicMock()}):
        engine = DatabricksEmbeddingEngine()
        client1 = engine.client
        client2 = engine.client
        assert client1 is client2

def test_databricks_embedding_engine_embed_text():
    with patch("src.semantic.DatabricksEmbeddingEngine.embed_batch") as mock_embed_batch:
        mock_embed_batch.return_value = [[0.1, 0.2, 0.3]]
        engine = DatabricksEmbeddingEngine()
        res = engine.embed_text("test")
        assert res == [0.1, 0.2, 0.3]
        mock_embed_batch.assert_called_once_with(["test"])

@patch("src.semantic.ENABLE_SEMANTIC_SEARCH", True)
def test_semantic_search_vss_install_fails():
    with patch("src.semantic.is_demo_mode", return_value=False):
        with patch("src.semantic._duckdb_available", return_value=True):
            with patch("src.semantic.run_query") as mock_run_query:
                def side_effect(*args, **kwargs):
                    import pandas as pd
                    if "LOAD vss" in args[0] or "INSTALL vss" in args[0]:
                        raise Exception("Failed")
                    return pd.DataFrame()

                mock_run_query.side_effect = side_effect

                with patch("src.semantic.get_embedding_engine") as mock_engine:
                    mock_engine.return_value.embed_text.return_value = [0.1, 0.2]

                    with patch("src.semantic.logging.warning") as mock_warning:
                        res = semantic_search("query")
                        assert res == []
                        mock_warning.assert_called_once()
                        assert "Could not load vss extension" in mock_warning.call_args[0][0]

@patch("src.semantic.ENABLE_SEMANTIC_SEARCH", True)
def test_semantic_search_empty_vector():
    with patch("src.semantic.is_demo_mode", return_value=False):
        with patch("src.semantic._duckdb_available", return_value=True):
            with patch("src.semantic.run_query"):
                with patch("src.semantic.get_embedding_engine") as mock_engine:
                    mock_engine.return_value.embed_text.return_value = []
                    res = semantic_search("query")
                    assert res == []

@patch("src.semantic.ENABLE_SEMANTIC_SEARCH", True)
def test_semantic_search_success():
    with patch("src.semantic.is_demo_mode", return_value=False):
        with patch("src.semantic._duckdb_available", return_value=True):
            with patch("src.semantic.get_embedding_engine") as mock_engine:
                mock_engine.return_value.embed_text.return_value = [0.1, 0.2]
                with patch("src.semantic.run_query") as mock_run_query:
                    def side_effect(*args, **kwargs):
                        import pandas as pd
                        if args and args[0].startswith("SELECT table_full_name"):
                            return pd.DataFrame({"table_full_name": ["cat.sch.tab1", "cat.sch.tab2"]})
                        return None
                    mock_run_query.side_effect = side_effect

                    res = semantic_search("query")
                    assert res == ["cat.sch.tab1", "cat.sch.tab2"]

@patch("src.semantic.ENABLE_SEMANTIC_SEARCH", True)
def test_semantic_search_load_vss_fails_but_install_succeeds():
    with patch("src.semantic.is_demo_mode", return_value=False):
        with patch("src.semantic._duckdb_available", return_value=True):
            with patch("src.semantic.run_query") as mock_run_query:
                def side_effect(*args, **kwargs):
                    import pandas as pd
                    if args[0] == "LOAD vss" and mock_run_query.call_count == 1:
                        raise Exception("Failed load 1")
                    if args and args[0].startswith("SELECT table_full_name"):
                        return pd.DataFrame({"table_full_name": ["cat.sch.tab1"]})
                    return None

                mock_run_query.side_effect = side_effect

                with patch("src.semantic.get_embedding_engine") as mock_engine:
                    mock_engine.return_value.embed_text.return_value = [0.1, 0.2]

                    res = semantic_search("query")
                    assert res == ["cat.sch.tab1"]
                    # Called with LOAD vss (fails), INSTALL vss, LOAD vss, SELECT ...
                    assert mock_run_query.call_count == 4
