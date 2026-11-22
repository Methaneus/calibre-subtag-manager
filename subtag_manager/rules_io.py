# -*- coding: utf-8 -*-
"""Export / import of Subtag Manager rules (pure Python, no Qt/calibre).

File format (UTF-8 JSON, versioned)::

    {
      "format": "calibre-subtag-manager-rules",
      "schema_version": 1,
      "equivalents":  [{"first": "...", "second": "..."}, ...],
      "combinations": [{"parent1": "...", "parent2": "...", "combo": "..."}, ...]
    }

Import also accepts rows written as lists (["a", "b"] / ["p1", "p2", "c"]).
Files exported by the older Tag Manager plugin
("format": "calibre-tag-manager-rules") are accepted as well.
A file with ANY invalid or partial row is rejected as a whole, so a file is
never half-imported.
"""

import json

try:
    from calibre_plugins.subtag_manager.engine import normalize_tag, tag_key
except ImportError:  # tests outside calibre
    from engine import normalize_tag, tag_key

FORMAT = 'calibre-subtag-manager-rules'
LEGACY_FORMATS = ('calibre-tag-manager-rules',)
SCHEMA_VERSION = 1
EQ_FIELDS = ('first', 'second')
CO_FIELDS = ('parent1', 'parent2', 'combo')


class RulesFileError(ValueError):
    def __init__(self, problems):
        self.problems = list(problems)
        ValueError.__init__(self, '\n'.join(self.problems))


def split_complete(rows, width):
    """-> (complete_rows, incomplete_row_numbers). Fully blank rows are dropped."""
    good, bad = [], []
    for i, r in enumerate(rows):
        r = [str(x if x is not None else '').strip() for x in list(r)[:width]]
        r += [''] * (width - len(r))
        if not any(r):
            continue
        if all(normalize_tag(x) for x in r):
            good.append(r)
        else:
            bad.append(i + 1)
    return good, bad


def export_dict(equivalents, combinations):
    eq, _ = split_complete(equivalents, 2)
    co, _ = split_complete(combinations, 3)
    return {
        'format': FORMAT,
        'schema_version': SCHEMA_VERSION,
        'equivalents': [dict(zip(EQ_FIELDS, r)) for r in eq],
        'combinations': [dict(zip(CO_FIELDS, r)) for r in co],
    }


def export_bytes(equivalents, combinations):
    return (json.dumps(export_dict(equivalents, combinations), ensure_ascii=False,
                       indent=2, sort_keys=False) + '\n').encode('utf-8')


def _parse_rows(data, key, fields, problems):
    rows = data.get(key, [])
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        problems.append('"%s" must be a list' % key)
        return []
    label = {'equivalents': 'Equivalents', 'combinations': 'Combinations'}[key]
    out = []
    for i, row in enumerate(rows, 1):
        if isinstance(row, dict):
            unknown = set(row) - set(fields)
            if unknown:
                problems.append('%s row %d: unknown field(s) %s' % (label, i, ', '.join(sorted(unknown))))
                continue
            vals = [row.get(f) for f in fields]
        elif isinstance(row, (list, tuple)):
            if len(row) != len(fields):
                problems.append('%s row %d: expected %d values, got %d' % (label, i, len(fields), len(row)))
                continue
            vals = list(row)
        else:
            problems.append('%s row %d: must be an object or a list' % (label, i))
            continue
        missing = [f for f, v in zip(fields, vals) if not isinstance(v, str) or not normalize_tag(v)]
        if missing:
            problems.append('%s row %d: missing or empty %s' % (label, i, ', '.join(missing)))
            continue
        out.append([v.strip() for v in vals])
    return out


def parse_bytes(raw):
    """Parse and validate a rules file. Returns (equivalents, combinations)
    as lists of row lists; raises RulesFileError listing every problem."""
    if isinstance(raw, bytes):
        try:
            raw = raw.decode('utf-8-sig')
        except UnicodeDecodeError as e:
            raise RulesFileError(['File is not valid UTF-8: %s' % e])
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise RulesFileError(['File is not valid JSON: %s' % e])
    if not isinstance(data, dict):
        raise RulesFileError(['Top level of the file must be a JSON object'])
    problems = []
    kind = data.get('format')
    if kind != FORMAT and kind not in LEGACY_FORMATS:
        problems.append('Not a Subtag Manager rules file (expected "format": "%s")' % FORMAT)
    ver = data.get('schema_version')
    if not isinstance(ver, int) or isinstance(ver, bool) or ver < 1:
        problems.append('Missing or invalid "schema_version"')
    elif ver > SCHEMA_VERSION:
        problems.append('File uses schema_version %d; this plugin understands up to %d. '
                        'Please update the plugin.' % (ver, SCHEMA_VERSION))
    if problems:
        raise RulesFileError(problems)
    eq = _parse_rows(data, 'equivalents', EQ_FIELDS, problems)
    co = _parse_rows(data, 'combinations', CO_FIELDS, problems)
    if problems:
        raise RulesFileError(problems)
    return eq, co


def eq_key(row):
    return frozenset((tag_key(row[0]), tag_key(row[1])))


def co_key(row):
    return (frozenset((tag_key(row[0]), tag_key(row[1]))), tag_key(row[2]))


def dedupe(rows, keyfunc):
    seen, out = set(), []
    for r in rows:
        k = keyfunc(r)
        if k not in seen:
            seen.add(k)
            out.append(list(r))
    return out


def merge(existing, incoming, keyfunc):
    """Existing rows first (kept as-is), then incoming rows not already
    present.  Duplicate detection is case-insensitive, ignores whitespace
    around dots, and treats (A, B) == (B, A) for the symmetric columns."""
    return dedupe(list(existing) + list(incoming), keyfunc)


def copy_legacy_rules(new_path, old_path):
    """If new_path does not exist and old_path does, copy equivalents,
    combinations and schema_version into a new JSON file at new_path.

    A missing new file is treated as empty. An existing new file is left
    alone even if it has no rules, so a later empty save is not overwritten.
    Returns True if a file was written.
    """
    import os
    if os.path.exists(new_path) or not os.path.exists(old_path):
        return False
    try:
        with open(old_path, 'r', encoding='utf-8') as f:
            data = json.load(f) or {}
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    eq = data.get('equivalents') or []
    co = data.get('combinations') or []
    if not eq and not co:
        return False
    out = {
        'schema_version': data.get('schema_version', 1),
        'equivalents': eq,
        'combinations': co,
    }
    os.makedirs(os.path.dirname(new_path) or '.', exist_ok=True)
    tmp = new_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp, new_path)
    return True
