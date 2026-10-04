"""Optional background is an as-of grouping variable, never a day correction."""
import json

from app.core.research_policy import BACKGROUND_FIELDS, BACKGROUND_FLAGS
from app.features.lifestyle_features import utc_instant


def background_as_of(events, user_id, as_of):
    rows = [row for row in events if int(row['user_id']) == user_id and utc_instant(row['known_at']) < as_of]
    if not rows:
        return dict.fromkeys(BACKGROUND_FIELDS)
    row = max(rows, key=lambda item: (utc_instant(item['known_at']), int(item['revision_id'])))
    payload = json.loads(row['payload']) if isinstance(row['payload'], str) else row['payload']
    return {key: payload.get(key) for key in BACKGROUND_FIELDS}


def background_group(fields):
    if fields.get('age_band') == 'under18':
        return 'under18'
    if any(fields.get(key) is True for key in BACKGROUND_FLAGS):
        return 'reported_context'
    if all(fields.get(key) is False for key in BACKGROUND_FLAGS):
        return 'explicit_none'
    return 'unknown'
