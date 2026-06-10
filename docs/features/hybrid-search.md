# Feature: Hybrid Semantic Search

## Description
Hybrid Search combines traditional keyword-based matching (BM25) with modern vector-based semantic similarity. This allows users to find data using business concepts and natural language, even when the exact column or table names don't match (e.g., searching for "revenue" to find a table named `fct_gross_sales`).

## How it Works
The search pipeline executes two parallel paths and then fuses the results for optimal relevance.

### 1. Keyword Path (Syntactic)
Uses standard SQL `LIKE` patterns (and eventually full-text indices) to find exact or substring matches in table names, column names, and descriptions. This remains the primary way to find specific identifiers.

### 2. Semantic Path (Conceptual)
Converts the user's query into a high-dimensional vector (embedding) and performs a "Nearest Neighbor" search against pre-calculated metadata embeddings stored in the local cache.

### 3. Fused Ranking
Results from both paths are combined as a weighted sum: the normalized keyword score contributes 0.7 and a rank-decayed semantic score contributes 0.3. Semantic hits missing from the keyword results are fetched permission-filtered and appended, so vector matches never bypass the access model.

## Technical Architecture
- **Embedding Store:** A new `tables_embedding_cache` table in the catalog cache stores the vectors.
- **VSS Engine:** Uses DuckDB's built-in vector similarity features (e.g., `array_cosine_similarity`).
- **Sync Integration:** The nightly sync job is responsible for generating embeddings for any new or updated metadata.

## Implementation Status
- `tables_embedding_cache` populated by `scripts/sync_metadata.py` during the nightly crawl.
- `EmbeddingEngine` Protocol with `DatabricksEmbeddingEngine` (Model Serving) and `MockEmbeddingEngine` fallback in `src/semantic.py`.
- Weighted fusion implemented in `src/db/queries.py::search_all_metadata` (2026-06, TODO OE-2); gated behind `ENABLE_SEMANTIC_SEARCH` (default off).
