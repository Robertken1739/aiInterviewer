import vector_store


def test_split_into_chunks_splits_on_blank_lines():
    text = "First paragraph.\n\nSecond paragraph.\n\n\n  Third, with padding.  \n\n"
    assert vector_store.split_into_chunks(text) == [
        "First paragraph.",
        "Second paragraph.",
        "Third, with padding.",
    ]


def test_search_with_no_indexed_chunks_returns_empty():
    assert vector_store.search(sequence_id=90001, query="anything", k=3) == []


def test_search_returns_most_relevant_chunk_first():
    sequence_id = 90002
    welding_chunk = "Argon shielding gas produces a smoother, more stable arc for welding carbon steel."
    adhesive_chunk = "Adhesive bonding avoids damaging the galvanized coating on automotive door panels."
    vector_store.index_chunks(sequence_id, [welding_chunk, adhesive_chunk])

    results = vector_store.search(sequence_id, "which shielding gas is best for welding carbon steel?", k=1)

    assert results == [welding_chunk]


def test_search_is_scoped_to_sequence_id():
    sequence_a, sequence_b = 90003, 90004
    chunk_a = "Sequence A content about shielding gas and carbon steel welding."
    chunk_b = "Sequence B content about shielding gas and carbon steel welding."
    vector_store.index_chunks(sequence_a, [chunk_a])
    vector_store.index_chunks(sequence_b, [chunk_b])

    results = vector_store.search(sequence_a, "shielding gas carbon steel", k=5)

    assert results == [chunk_a]
    assert chunk_b not in results


def test_index_chunks_replaces_previous_chunks_for_same_sequence():
    sequence_id = 90005
    vector_store.index_chunks(sequence_id, ["old chunk about titanium cutting"])
    vector_store.index_chunks(sequence_id, ["new chunk about aluminum cutting"])

    results = vector_store.search(sequence_id, "cutting", k=5)

    assert results == ["new chunk about aluminum cutting"]
