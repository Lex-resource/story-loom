from __future__ import annotations

import json
from typing import Any, Optional

from services.pipeline_types import JobStatus
import logging
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical storage contract for Job.error
# ---------------------------------------------------------------------------
#
# ``job.error`` is a Text column that historically stored two incompatible
# shapes:
#   1. A raw error string (e.g. ``job.error = "something broke"``).
#   2. A JSON-encoded dict (e.g. ``job.error = '{"error": "...", "chapter": 3}'``).
#
# Readers therefore had to ``try: json.loads(...)`` and fall back to treating
# the value as a raw string, which leaked into every call site. The contract
# below is the canonical shape going forward:
#
#   * ``job.error`` is ``None`` when there is no error.
#   * ``job.error`` is ALWAYS a JSON-encoded ``dict`` when non-null. The dict
#     MUST contain an ``"error"`` key holding the latest human-readable
#     message. Legacy raw strings are normalized to ``{"error": <raw>}`` on
#     read by ``_read_error_dict``.
#   * Optional structured fields (``chapter``, ``step``, ``raw_error`` for
#     unstructured legacy context, ``previous_errors`` for history) may be
#     attached.
#
# ``job.params`` is a SEPARATE JSON column for job input/progress metadata
# (target chapters, retry counts, issue_id, etc.) and MUST NOT be used to
# store error state. The previous ``get_job_params`` fallback that parsed
# ``job.error`` as params is retained for backwards compatibility with old
# rows but should not be written to by new code.
# ---------------------------------------------------------------------------


def _read_error_dict(job) -> dict[str, Any]:
    """Return the error dict stored on ``job.error``, or ``{}`` if none.

    Normalizes legacy raw-string values to ``{"error": <raw>}`` so callers
    never have to guess the shape.
    """
    raw = getattr(job, "error", None)
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:

            logger.debug("degraded:job_payload.params_not_json", exc_info=True)
        return {"error": raw}
    return {"error": str(raw)}


def get_job_error_message(job) -> Optional[str]:
    """Extract the human-readable error message from ``job.error``.

    Returns ``None`` if there is no error. Handles both the canonical JSON
    dict shape and legacy raw strings.
    """
    err_dict = _read_error_dict(job)
    if not err_dict:
        return None
    return err_dict.get("error") or err_dict.get("raw_error")


def get_blocking_job_error_message(job) -> Optional[str]:
    """Return only errors that should put the UI in a blocking/error state."""
    status = getattr(job, "status", None)
    if status != JobStatus.FAILED:
        return None
    return get_job_error_message(job)


def set_job_error(job, error_msg: str, **extra_fields: Any) -> None:
    """OVERWRITE ``job.error`` with a fresh error entry.

    Use this when a new error supersedes the previous one (e.g. status
    reset, fresh failure on a retry). To accumulate history instead, use
    :func:`append_job_error`.
    """
    payload: dict[str, Any] = {"error": error_msg}
    for k, v in extra_fields.items():
        payload[k] = v
    job.error = json.dumps(payload, ensure_ascii=False)


def append_job_error(job, error_msg: str, **extra_fields: Any) -> None:
    """Append a new error to ``job.error``, preserving prior context.

    The previous ``error`` value is pushed onto a ``previous_errors`` list
    so the failure history is retained without losing the latest message.
    Optional ``extra_fields`` are merged in (overriding prior values of the
    same key).
    """
    existing = _read_error_dict(job)
    previous_errors: list[Any] = []
    if isinstance(existing.get("previous_errors"), list):
        previous_errors = list(existing["previous_errors"])
    if existing.get("error"):
        previous_errors.append(existing["error"])
    merged: dict[str, Any] = dict(existing)
    merged["error"] = error_msg
    merged["previous_errors"] = previous_errors
    for k, v in extra_fields.items():
        merged[k] = v
    job.error = json.dumps(merged, ensure_ascii=False)


def clear_job_error(job) -> None:
    """Clear ``job.error``.

    Note: this only touches ``job.error``. It does NOT modify ``job.params``,
    which is a separate column for job input/progress metadata. (An earlier
    version of this function removed ``error``/``raw_error`` keys from
    ``job.params``, which conflated the two columns.)
    """
    job.error = None


# ---------------------------------------------------------------------------
# Job params helpers (params is a SEPARATE column from error)
# ---------------------------------------------------------------------------


def get_job_params(job) -> dict[str, Any]:
    """Return the job's input/progress params as a dict.

    Falls back to parsing ``job.error`` ONLY for backwards compatibility with
    old rows where error context was mistakenly stored as params. New code
    should write to ``job.params`` via :func:`set_job_params` and never store
    params in ``job.error``.
    """
    params = getattr(job, "params", None)
    if isinstance(params, dict):
        return dict(params)
    if isinstance(params, str):
        try:
            parsed = json.loads(params)
            if isinstance(parsed, dict):
                return parsed
        except Exception:

            logger.debug("degraded:job_payload.legacy_params_not_json", exc_info=True)
    # Legacy fallback: some old rows stored structured context in job.error.
    # Do not rely on this for new writes.
    error_dict = _read_error_dict(job)
    if error_dict:
        # Strip the canonical error keys so they don't leak into params view.
        legacy = {k: v for k, v in error_dict.items() if k not in ("error", "raw_error", "previous_errors")}
        if legacy:
            return legacy
    return {}


def find_experiment_params(jobs) -> Optional[dict[str, Any]]:
    """Return the newest valid experiment payload found in ``jobs``.

    Rewrite and resume flows can create intermediate jobs whose params only
    contain UI or chapter-control fields.  Research metadata must therefore
    be recovered from the newest job that still carries it, rather than being
    lost when the latest job is rewritten.
    """
    for job in jobs or []:
        params = get_job_params(job)
        experiment = params.get("experiment")
        if isinstance(experiment, dict):
            return dict(experiment)
    return None


def set_job_params(job, params: dict[str, Any]) -> None:
    job.params = dict(params)


def update_job_params(job, **updates: Any) -> dict[str, Any]:
    params = get_job_params(job)
    params.update(updates)
    set_job_params(job, params)
    return params
