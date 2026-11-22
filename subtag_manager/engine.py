# -*- coding: utf-8 -*-
"""Pure tag-rule engine for the Subtag Manager calibre plugin.

This module has NO calibre or Qt dependencies so that it can be unit tested
outside calibre.

Semantics (see README.md for the user-facing description)
---------------------------------------------------------
* Tag comparison is case-insensitive and ignores whitespace around the
  hierarchy separator "." (calibre itself treats tags case-insensitively).
  Existing tags keep their original spelling; new tags use the spelling
  configured in the rule.
* Equivalents: a rule (First, Second) is bidirectional.  Rules are joined into
  connected groups (transitive closure), so A<->B plus B<->C means that a book
  with any of A, B, C ends up with all of A, B, C (an exact-tag match only;
  subtags do not trigger equivalents).
* Combinations: a rule (Parent 1, Parent 2, Combo) fires when the book has a
  tag matching Parent 1 AND a tag matching Parent 2.  A tag matches a parent
  when it is exactly the parent or a dot-boundary descendant of it
  ("Romance Fiction.Erotic Romance" matches "Romance Fiction"; "Romance
  Fictionalized" and plain "Romance Fiction" do NOT match a parent of
  "Romance Fiction.Erotic Romance").  When it fires, "Parent.Combo" is added
  for BOTH parents.  If the bare parent tag itself is on the book it is
  replaced by (removed in favour of) "Parent.Combo"; existing descendant tags
  are kept and "Parent.Combo" is added alongside.
* Each pass = (1) equivalence closure, (2) evaluate ALL combination rules
  against the same snapshot, (3) add every new combo tag, (4) only then remove
  the bare parents that were specialised.  Passes repeat until the tag set
  stops changing (fixed point).  Because removals only ever drop a bare tag T
  after T.Combo (which matches everything T matched) was added, the set of
  matches is monotonic and the process terminates; nevertheless a hard
  pass limit and repeated-state detection guard against non-termination.  A
  book that does not converge is reported and left untouched.
* The result is idempotent: running the rules on the output again produces
  no further change.
"""

from collections import OrderedDict

SEP = '.'
MAX_PASSES = 50


def normalize_tag(tag):
    """Canonical display form: components stripped, empty components dropped."""
    if tag is None:
        return ''
    parts = [p.strip() for p in str(tag).split(SEP)]
    parts = [' '.join(p.split()) for p in parts if p.strip()]
    return SEP.join(parts)


def tag_key(tag):
    """Comparison key (case-insensitive, normalised)."""
    return normalize_tag(tag).casefold()


def natural_key(value):
    """Case-insensitive "natural" sort key: digit runs compare numerically,
    so "Book 2" < "Book 10".  Works for ints and strings."""
    import re
    if isinstance(value, (int, float)):
        return ((0, value, ''),)
    import unicodedata
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    parts = re.split(r'(\d+)', text)
    return tuple((0, int(p), '') if p.isdigit() else (1, 0, p) for p in parts if p != '')


def matches_parent(tag, parent):
    """True if tag is parent or a dot-boundary descendant of parent."""
    t, p = tag_key(tag), tag_key(parent)
    if not t or not p:
        return False
    return t == p or t.startswith(p + SEP)


class RuleError(ValueError):
    pass


class Rules(object):
    """Validated, normalised rule set."""

    def __init__(self, equivalents=(), combinations=()):
        self.equivalents = []
        self.combinations = []
        self.problems = []
        seen = set()
        for i, row in enumerate(equivalents or ()):
            row = list(row or ()) + ['', '']
            a, b = normalize_tag(row[0]), normalize_tag(row[1])
            if not a and not b:
                continue
            if not a or not b:
                self.problems.append('Equivalents row %d: both First and Second are required' % (i + 1))
                continue
            if tag_key(a) == tag_key(b):
                continue
            k = tuple(sorted((tag_key(a), tag_key(b))))
            if k in seen:
                continue
            seen.add(k)
            self.equivalents.append((a, b))
        seen = set()
        for i, row in enumerate(combinations or ()):
            row = list(row or ()) + ['', '', '']
            p1, p2, c = normalize_tag(row[0]), normalize_tag(row[1]), normalize_tag(row[2])
            if not (p1 or p2 or c):
                continue
            if not (p1 and p2 and c):
                self.problems.append('Combinations row %d: Parent 1, Parent 2 and Combo are all required' % (i + 1))
                continue
            k = (tag_key(p1), tag_key(p2), tag_key(c))
            if k in seen:
                continue
            seen.add(k)
            self.combinations.append((p1, p2, c))
        self._groups = self._build_groups()

    @classmethod
    def from_prefs(cls, prefs):
        return cls(prefs.get('equivalents', []), prefs.get('combinations', []))

    def _build_groups(self):
        # Union-find over tag keys, deterministic member order (first seen).
        parent = {}
        display = OrderedDict()

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a, b in self.equivalents:
            for t in (a, b):
                k = tag_key(t)
                if k not in parent:
                    parent[k] = k
                    display[k] = t
            ra, rb = find(tag_key(a)), find(tag_key(b))
            if ra != rb:
                parent[rb] = ra
        groups = OrderedDict()
        for k in display:
            groups.setdefault(find(k), []).append(k)
        key_to_group = {}
        for members in groups.values():
            g = [display[m] for m in members]
            for m in members:
                key_to_group[m] = g
        return key_to_group

    def equivalence_group(self, tag):
        return list(self._groups.get(tag_key(tag), ()))

    def is_empty(self):
        return not self.equivalents and not self.combinations


class BookChange(object):
    __slots__ = ('book_id', 'title', 'original', 'final', 'added', 'removed', 'converged', 'error')

    def __init__(self, book_id, title, original, final, added, removed, converged=True, error=None):
        self.book_id = book_id
        self.title = title
        self.original = tuple(original)
        self.final = tuple(final)
        self.added = tuple(added)
        self.removed = tuple(removed)
        self.converged = converged
        self.error = error

    @property
    def changed(self):
        return self.converged and (bool(self.added) or bool(self.removed))

    def __repr__(self):
        return 'BookChange(%r, +%r, -%r)' % (self.book_id, self.added, self.removed)


class _TagSet(object):
    """Ordered, case-insensitive tag set preserving first spelling."""

    def __init__(self, tags=()):
        self._d = OrderedDict()
        for t in tags:
            self.add(t)

    def add(self, t):
        n = normalize_tag(t)
        k = n.casefold()
        if k and k not in self._d:
            self._d[k] = t if isinstance(t, str) and normalize_tag(t) == n else n
            return True
        return False

    def discard(self, t):
        self._d.pop(tag_key(t), None)

    def __contains__(self, t):
        return tag_key(t) in self._d

    def __iter__(self):
        return iter(list(self._d.values()))

    def keys(self):
        return frozenset(self._d)

    def copy(self):
        n = _TagSet()
        n._d = OrderedDict(self._d)
        return n


def _one_pass(tags, rules):
    cur = tags.copy()
    # 1. Equivalence closure (exact tags only).
    for t in list(cur):
        for member in rules.equivalence_group(t):
            cur.add(member)
    # 2. Evaluate every combination against the same snapshot.
    snapshot = list(cur)
    to_add, to_remove = [], []
    for p1, p2, combo in rules.combinations:
        if any(matches_parent(t, p1) for t in snapshot) and any(matches_parent(t, p2) for t in snapshot):
            for p in (p1, p2):
                to_add.append(p + SEP + combo)
                if p in cur:
                    to_remove.append(p)
    # 3. Additions first, 4. then bare-parent removals.
    for t in to_add:
        cur.add(t)
    for t in to_remove:
        cur.discard(t)
    return cur


def compute_tags(original, rules, max_passes=MAX_PASSES):
    """Return (final_tags_list, converged)."""
    cur = _TagSet(original)
    seen = {cur.keys()}
    for _ in range(max_passes):
        nxt = _one_pass(cur, rules)
        if nxt.keys() == cur.keys():
            return list(cur), True
        if nxt.keys() in seen:
            return list(original), False   # oscillation detected
        seen.add(nxt.keys())
        cur = nxt
    return list(original), False


def compute_book_change(book_id, title, original, rules):
    original = tuple(t for t in (original or ()) if normalize_tag(t))
    final, ok = compute_tags(original, rules)
    if not ok:
        return BookChange(book_id, title, original, original, (), (), converged=False,
                          error='Rules did not converge for this book; it will not be changed.')
    okeys = {tag_key(t) for t in original}
    fkeys = {tag_key(t) for t in final}
    added = [t for t in final if tag_key(t) not in okeys]
    removed = [t for t in original if tag_key(t) not in fkeys]
    # Final order: original order (minus removals) followed by additions.
    final_ordered = [t for t in original if tag_key(t) in fkeys] + added
    return BookChange(book_id, title, original, final_ordered, added, removed)


class Plan(object):
    """Result of a read-only scan."""

    def __init__(self, library_id, scanned, changes, warnings):
        self.library_id = library_id
        self.scanned = scanned
        self.changes = changes          # list[BookChange], only changed books
        self.warnings = warnings        # list[BookChange], non-converged books

    @property
    def total_added(self):
        return sum(len(c.added) for c in self.changes)

    @property
    def total_removed(self):
        return sum(len(c.removed) for c in self.changes)


def build_plan(library_id, books, rules):
    """books: iterable of (book_id, title, tags). Never writes anything."""
    changes, warnings, n = [], [], 0
    for book_id, title, tags in books:
        n += 1
        ch = compute_book_change(book_id, title, tags, rules)
        if not ch.converged:
            warnings.append(ch)
        elif ch.changed:
            changes.append(ch)
    return Plan(library_id, n, changes, warnings)
