"""
Orion — Mémoire long terme vectorielle.

Composants :
  - embedder.Embedder        : sentence-transformers (multilingue FR par défaut)
  - vector_store.VectorStore : index numpy + JSON, recherche cosinus
  - rag_tools.HANDLERS       : tools exposés au LLM (memory_remember, memory_recall, …)
"""
