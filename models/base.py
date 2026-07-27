from datetime import datetime, timezone

from database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)
