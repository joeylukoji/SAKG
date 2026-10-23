import pytest
from pydantic import ValidationError

from sakg.domain import Evidence, EvidenceType, Provenance


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_confidence_must_be_between_zero_and_one(confidence: float) -> None:
    with pytest.raises(ValidationError):
        Provenance(evidence_type=EvidenceType.INFERRED, confidence=confidence, detected_by="HEURISTIC")


def test_detected_by_is_required() -> None:
    with pytest.raises(ValidationError):
        Provenance(evidence_type=EvidenceType.OBSERVED, confidence=1.0, detected_by="")


@pytest.mark.parametrize(
    ("evidence_type", "expected"),
    [
        (EvidenceType.OBSERVED, True),
        (EvidenceType.USER_DEFINED, True),
        (EvidenceType.INFERRED, False),
        (EvidenceType.GENERATED, False),
        (EvidenceType.RECOMMENDED, False),
    ],
)
def test_is_fact(evidence_type: EvidenceType, expected: bool) -> None:
    provenance = Provenance(evidence_type=evidence_type, confidence=0.5, detected_by="TEST")
    assert provenance.is_fact() is expected


def test_provenance_is_immutable(observed: Provenance) -> None:
    with pytest.raises(ValidationError):
        observed.confidence = 0.2  # type: ignore[misc]


def test_created_at_is_timezone_aware(observed: Provenance) -> None:
    assert observed.created_at.tzinfo is not None


def test_evidence_line_range() -> None:
    assert Evidence(file="src/app.py", line=3, end_line=10).end_line == 10
    with pytest.raises(ValidationError):
        Evidence(file="src/app.py", line=10, end_line=3)
    with pytest.raises(ValidationError):
        Evidence(file="src/app.py", end_line=3)
