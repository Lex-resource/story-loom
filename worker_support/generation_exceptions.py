class JobPausedException(Exception):
    """Job was paused by user; abort current chapter gracefully."""


class JobAbortedException(Exception):
    """Job status changed to a non-paused terminal state; abort cleanly."""
