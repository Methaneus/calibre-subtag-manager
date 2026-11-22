# -*- coding: utf-8 -*-
"""Scan / confirm / commit flow for Subtag Manager.

No Qt imports, so it can be unit tested with a fake object that mimics the
parts of calibre's ``db.new_api`` (calibre.db.cache.Cache) used here:

    library_id, all_book_ids(), all_field_for(field, ids, default_value=None),
    set_field(field, {book_id: value})

Write gate: ``run_flow`` scans read-only, calls ``confirm(plan)`` and only
writes when it returns exactly ``True``.  Before writing it verifies the
library is still the one that was scanned and that each book's tags are
unchanged since the scan; stale or deleted books are skipped and reported.
All writes happen in a single batched ``set_field('tags', ...)`` call.
"""

try:
    from calibre_plugins.subtag_manager.engine import build_plan, tag_key
except ImportError:  # running outside calibre (tests)
    from engine import build_plan, tag_key


class CommitResult(object):
    def __init__(self, written=(), stale=(), missing=(), aborted_reason=None):
        self.written = list(written)
        self.stale = list(stale)
        self.missing = list(missing)
        self.aborted_reason = aborted_reason

    def __repr__(self):
        return 'CommitResult(written=%r, stale=%r, missing=%r, aborted=%r)' % (
            self.written, self.stale, self.missing, self.aborted_reason)


def _tags_signature(tags):
    return tuple(sorted(tag_key(t) for t in (tags or ())))


def scan(api, rules):
    """Read-only scan of the whole library. Returns an engine.Plan."""
    ids = list(api.all_book_ids())
    ids.sort()
    titles = api.all_field_for('title', ids, default_value='')
    tags = api.all_field_for('tags', ids, default_value=())
    books = ((i, titles.get(i, ''), tags.get(i, ()) or ()) for i in ids)
    return build_plan(getattr(api, 'library_id', None), books, rules)


def commit(api, plan):
    """Write the plan, guarding against a switched library and stale tags."""
    if not plan.changes:
        return CommitResult()
    current_lib = getattr(api, 'library_id', None)
    if current_lib != plan.library_id:
        return CommitResult(aborted_reason='The active library changed since the scan; nothing was written. Please run the scan again.')
    ids = [c.book_id for c in plan.changes]
    existing = set(api.all_book_ids())
    now = api.all_field_for('tags', [i for i in ids if i in existing], default_value=())
    updates, stale, missing = {}, [], []
    for c in plan.changes:
        if c.book_id not in existing:
            missing.append(c.book_id)
        elif _tags_signature(now.get(c.book_id, ())) != _tags_signature(c.original):
            stale.append(c.book_id)
        else:
            updates[c.book_id] = tuple(c.final)
    if updates:
        api.set_field('tags', updates, allow_case_change=False)
    return CommitResult(sorted(updates), stale, missing)


def run_flow(api, rules, confirm):
    """scan -> confirm(plan) -> commit. Returns (plan, CommitResult or None).

    ``confirm`` must return True to allow writing; anything else (False,
    None, an exception) means nothing is written.
    """
    plan = scan(api, rules)
    if not plan.changes:
        return plan, None
    try:
        ok = confirm(plan)
    except Exception:
        ok = False
    if ok is not True:
        return plan, None
    return plan, commit(api, plan)
