"""How development_updates rows become notifications. No database write here.

This sprint defines the consumer interface and the rendering only. Wiring a
consumer to the notifications table is the next step, so that a change event and
its delivery can be reviewed separately.
"""
SEVERITY = {'STAGE': 'HIGH', 'STATUS': 'HIGH', 'SOURCE_MISSING': 'REVIEW',
            'DETAIL': 'LOW', 'REVERIFICATION': 'LOW', 'INITIAL': 'INFO', 'GEOMETRY': 'LOW'}
TITLES = {'STAGE': '정비사업 단계 변경', 'STATUS': '정비사업 상태 변경',
          'SOURCE_MISSING': '공식 목록에서 확인되지 않음', 'DETAIL': '정비사업 정보 변경',
          'REVERIFICATION': '공식 자료 재확인', 'INITIAL': '신규 정비사업 후보',
          'GEOMETRY': '정비사업 경계 변경'}


def render_event(update):
    """Turn one development_updates row into a deliverable event.

    Absence is reported as absence. A missing listing row never becomes a
    cancellation message, and an unreviewed change says so.
    """
    kind = update.get('update_kind') or 'REVERIFICATION'
    change = ((update.get('new_snapshot') or {}).get('change')) or {}
    master = ((update.get('new_snapshot') or {}).get('master')) or {}
    name = master.get('project_name') or update.get('project_id')
    fields = update.get('changed_fields') or []
    if kind == 'STAGE':
        detail = f"{update.get('previous_stage') or '미확인'} → {update.get('new_stage') or '미확인'}"
    elif kind == 'STATUS':
        detail = f"{update.get('previous_status') or 'UNKNOWN'} → {update.get('new_status') or 'UNKNOWN'}"
    elif kind == 'SOURCE_MISSING':
        detail = '공식 목록에 나타나지 않음 · 사업 취소나 종료를 의미하지 않음'
    else:
        detail = '변경 필드: ' + (', '.join(fields) if fields else '없음')
    review = bool(change.get('review_required'))
    return {'event_key': f"zipon-dev:{update.get('project_id')}:{update.get('to_revision')}",
            'event_hash': update.get('event_hash'),
            'category': 'development',
            'update_kind': kind,
            'pipeline_kind': change.get('pipeline_kind') or kind,
            'severity': 'REVIEW' if review else SEVERITY.get(kind, 'LOW'),
            'title': TITLES.get(kind, '정비사업 변경'),
            'message': f'{name} · {detail}' + (' · 검토 필요' if review else ''),
            'project_id': update.get('project_id'),
            'to_revision': update.get('to_revision'),
            'changed_fields': fields,
            'review_required': review,
            'review_reasons': change.get('review_reasons') or [],
            'requires_human_review': review or kind == 'SOURCE_MISSING'}


class DevelopmentUpdateConsumer:
    """Interface. handle() receives one rendered event and returns it or None."""

    def handle(self, event):  # pragma: no cover - interface
        raise NotImplementedError


class CollectingConsumer(DevelopmentUpdateConsumer):
    """Keeps events in memory. Used by the pipeline dry run and by tests."""

    def __init__(self):
        self.events = []

    def handle(self, event):
        self.events.append(event)
        return event


class NotificationDraftConsumer(DevelopmentUpdateConsumer):
    """Shapes rows for the existing notifications table but writes nothing.

    Connecting this to a database is a separate, reviewed step.
    """

    def __init__(self):
        self.drafts = []

    def handle(self, event):
        draft = {'event_key': event['event_key'], 'category': event['category'],
                 'title': event['title'], 'message': event['message'], 'is_read': False,
                 'requires_human_review': event['requires_human_review']}
        self.drafts.append(draft)
        return draft


def consume(updates, consumer, *, seen=None):
    """Render and dispatch, skipping anything already delivered.

    Deduplication uses the append-only event_hash, so a repeated run cannot send
    the same change twice.
    """
    seen = set() if seen is None else set(seen)
    delivered, skipped = [], []
    for update in updates:
        event = render_event(update)
        marker = event['event_hash'] or event['event_key']
        if marker in seen:
            skipped.append(event['event_key'])
            continue
        seen.add(marker)
        consumer.handle(event)
        delivered.append(event)
    return {'delivered': len(delivered), 'skipped_duplicates': len(skipped),
            'events': delivered, 'seen': sorted(seen), 'db_write': False}
