## 2025-05-21 - Mocking dimension bug in Embeddings
**Learning:** Found a bug in MockEmbeddingEngine where small strings generated vectors < 384 dimensions. This can lead to flaky tests if other components implicitly expect fixed sizes for embeddings.
**Action:** Always ensure mocks for vector databases or embedding engines strictly conform to the expected dimensional constraints of the real service.
