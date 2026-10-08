"""Chroma-backed chunk store for Helper LLM retrieval.

Holds ONLY neutral source-material chunks, keyed by sequence_id. Nothing in
this module ever reads or accepts stage.reference_answer or
stage.trap_claim_text — the security boundary in DESIGN.md §5 is enforced by
the fact that this module has no code path that could touch them, not by a
runtime check.

The index is a rebuildable cache, not a system of record: Postgres'
`sequence.source_material` is the source of truth, so an in-memory Chroma
client is enough — nothing is lost on restart, `index_chunks` just reruns.

Embeddings use Chroma's default local model (ONNX MiniLM) -- Groq has no
embeddings API, and this keeps retrieval free of any network call. The model
is downloaded once, on first use.
"""

import chromadb

_client = chromadb.EphemeralClient()
_collection = _client.get_or_create_collection("source_material_chunks")

# sequence_id -> the chunk list last indexed for it. ask_helper calls
# index_chunks before every single question with the same chunks each time,
# so skip re-indexing when the content hasn't actually changed.
_indexed_chunks: dict[int, tuple[str, ...]] = {}


def split_into_chunks(source_material: str) -> list[str]:
    """Paragraph-level split — a sequence's source material is a few short paragraphs."""
    return [p.strip() for p in source_material.split("\n\n") if p.strip()]


def index_chunks(sequence_id: int, chunks: list[str]) -> None:
    """Replace whatever is indexed for this sequence with `chunks`.

    A no-op if `chunks` is identical to what's already indexed for this
    sequence_id, so callers can call it before every search for free.
    """
    fingerprint = tuple(chunks)
    if _indexed_chunks.get(sequence_id) == fingerprint:
        return
    existing = _collection.get(where={"sequence_id": sequence_id})
    if existing["ids"]:
        _collection.delete(ids=existing["ids"])
    if not chunks:
        _indexed_chunks[sequence_id] = fingerprint
        return
    _collection.add(
        ids=[f"{sequence_id}:{i}" for i in range(len(chunks))],
        documents=chunks,
        metadatas=[{"sequence_id": sequence_id} for _ in chunks],
    )
    _indexed_chunks[sequence_id] = fingerprint


def search(sequence_id: int, query: str, k: int = 3) -> list[str]:
    """Top-k neutral chunks for this sequence, most relevant first."""
    if _collection.count() == 0:
        return []
    results = _collection.query(query_texts=[query], n_results=k, where={"sequence_id": sequence_id})
    documents = results["documents"]
    return documents[0] if documents else []
