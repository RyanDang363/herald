"""Presentation-only id → friendly name map for chat and dashboard."""

DISPLAY_NAMES: dict[str, str] = {
    "nurse1": "Nurse Maya", "nurse2": "Nurse Chen",
    "doc1": "Dr. Smith", "doc2": "Dr. Patel",
    "bed1": "bed-1", "bed2": "bed-2", "bed3": "bed-3", "bed4": "bed-4",
    "o2_1": "oxygen unit o2-1", "o2_2": "replacement unit o2-2",
}


def display(entity_id: str | None) -> str:
    return DISPLAY_NAMES.get(entity_id, entity_id) if entity_id else ""
