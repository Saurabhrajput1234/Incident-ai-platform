"""
Round-robin engineer selector.

Tracks the last assigned engineer per assignment group
so each triage picks the next engineer in rotation.

State is in-memory per process. Resets on server restart.
Replace with a DB-backed counter for persistence across restarts.
"""
import threading

# {assignment_group: last_index_used}
_state: dict[str, int] = {}
_lock = threading.Lock()


def pick_round_robin(candidates: list, assignment_group: str):
    """
    Pick the next candidate in round-robin order for the given assignment group.
    candidates: list of EngineerRecommendation, already filtered to available only.
    Returns the selected candidate.
    """
    if not candidates:
        return None

    with _lock:
        last = _state.get(assignment_group, -1)
        next_idx = (last + 1) % len(candidates)
        _state[assignment_group] = next_idx

    return candidates[next_idx]
