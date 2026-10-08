import vector_store
from db.models import Sequence, Stage
from seed.seed_materials_joining import SEQUENCES, seed


def test_seed_creates_five_sequences_with_five_stages_each(db_session):
    created = seed(db_session)

    assert len(created) == 5
    for sequence in created:
        stages = db_session.query(Stage).filter(Stage.sequence_id == sequence.id).all()
        assert len(stages) == 5
        assert sorted(s.order_index for s in stages) == [1, 2, 3, 4, 5]


def test_seed_stage_types_are_in_the_fixed_order(db_session):
    created = seed(db_session)

    stages = (
        db_session.query(Stage)
        .filter(Stage.sequence_id == created[0].id)
        .order_by(Stage.order_index)
        .all()
    )
    assert [s.stage_type for s in stages] == ["anchor", "constraint", "contradiction", "ai_trap", "synthesis"]
    assert stages[3].trap_claim_text  # the ai_trap stage has a trap claim
    assert all(s.trap_claim_text is None for s in stages if s.stage_type != "ai_trap")
    assert all(s.reference_answer for s in stages)  # every stage has grading notes


def test_seed_is_idempotent(db_session):
    first_run = seed(db_session)
    second_run = seed(db_session)

    assert len(first_run) == 5
    assert second_run == []  # nothing new the second time
    assert db_session.query(Sequence).count() == 5  # no duplicates


def test_seed_indexes_the_vector_store(db_session):
    created = seed(db_session)
    sequence = next(s for s in created if s.title == SEQUENCES[0]["title"])

    results = vector_store.search(sequence.id, "shielding gas cost trade-off", k=1)

    assert results  # the vector store actually has something for this sequence now
    assert results[0] in vector_store.split_into_chunks(sequence.source_material)
