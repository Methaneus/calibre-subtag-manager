"""Offscreen Qt tests for sorting, add/remove while sorted, save integrity,
export/import and preview sorting.  Run with a THROWAWAY config dir:

  CALIBRE_CONFIG_DIRECTORY=/tmp/tm-cfg QT_QPA_PLATFORM=offscreen \
    calibre-debug tests/calibre_ui_test.py
"""
import json, os, tempfile, types
from calibre.gui2 import Application
app = Application([])
from qt.core import (QAbstractItemView, QApplication, QEvent, QMouseEvent, QPoint,
                     QPointF, Qt)
from calibre.customize.ui import find_plugin
base = find_plugin('Subtag Manager')
assert base is not None and base.version == (1, 2, 0), base and base.version
from calibre_plugins.subtag_manager.prefs import prefs
from calibre_plugins.subtag_manager import config, preview, writer, engine, rules_io

failures = []
def check(cond, msg):
    print(('PASS ' if cond else 'FAIL ') + msg)
    if not cond:
        failures.append(msg)

def click_header(rt, col):
    """Real mouse click on a header section (falls back to the signal)."""
    h = rt.table.horizontalHeader()
    x = h.sectionViewportPosition(col) + h.sectionSize(col) // 2
    pos = QPointF(x, h.height() / 2)
    gpos = QPointF(h.viewport().mapToGlobal(QPoint(int(pos.x()), int(pos.y()))))
    for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(et, pos, gpos, Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton if et == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(h.viewport(), ev)
    app.processEvents()

def col(rt, c):
    return [r[c] for r in rt.values()]

EQ = [['b tag 10', 'Zeta'], ['B tag 2', 'alpha'], ['a tag', 'Mid'], ['Émile', 'x']]
CO = [['Romance Fiction', 'Western Fiction', 'Western Romance'],
      ['fantasy fiction', 'Political Fiction', 'Political Fantasy'],
      ['Horror', 'Comedy', 'Comedic Horror']]
prefs['equivalents'] = EQ; prefs['combinations'] = CO
w = base.config_widget(); w.show(); app.processEvents()
eqt, cot = w.equivalents, w.combinations
h = eqt.table.horizontalHeader()

# --- sorting -------------------------------------------------------------
check(not h.isSortIndicatorShown(), 'no sort indicator initially')
click_header(eqt, 0)
check(col(eqt, 0) == ['a tag', 'B tag 2', 'b tag 10', 'Émile'], 'First asc natural/case-insensitive: %s' % col(eqt, 0))
check(h.isSortIndicatorShown() and h.sortIndicatorSection() == 0 and
      h.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder, 'indicator asc on First')
click_header(eqt, 0)
check(col(eqt, 0) == ['Émile', 'b tag 10', 'B tag 2', 'a tag'], 'First desc')
check(h.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder, 'indicator desc')
click_header(eqt, 1)
check(col(eqt, 1) == ['alpha', 'Mid', 'x', 'Zeta'], 'Second asc')
check(all(dict(map(tuple, [r])) for r in eqt.values()) and
      sorted(map(tuple, eqt.values())) == sorted(map(tuple, EQ)), 'rows kept intact (pairs not scrambled)')
click_header(cot, 2)
check(col(cot, 2) == ['Comedic Horror', 'Political Fantasy', 'Western Romance'], 'Combo asc')
click_header(cot, 0)
check(col(cot, 0) == ['fantasy fiction', 'Horror', 'Romance Fiction'], 'Parent 1 asc case-insensitive')
click_header(cot, 1); click_header(cot, 1)
check(col(cot, 1) == ['Western Fiction', 'Political Fiction', 'Comedy'], 'Parent 2 desc')

# --- add while sorted ------------------------------------------------------
click_header(eqt, 0)  # sorted asc
r = eqt.add_row()
app.processEvents()
t = eqt.table
check(r == t.rowCount() - 1 and t.currentRow() == r, 'new row appended at bottom and current')
check(t.state() == QAbstractItemView.State.EditingState, 'new row opened for editing')
check(not h.isSortIndicatorShown(), 'indicator cleared after add')
from qt.core import QLineEdit
eds = [e for e in t.viewport().findChildren(QLineEdit) if e.isVisible()]
check(len(eds) == 1, 'inline editor present for new row')
eds[0].setText('AAA first')            # simulate typing into the open editor
t.item(r, 1).setText('new second')
app.processEvents()
eqt.commit_editor()
check(t.item(r, 0).text() == 'AAA first' and t.rowCount() == 5, 'edited row did not jump/duplicate')
click_header(eqt, 0)
check(col(eqt, 0) == ['a tag', 'AAA first', 'B tag 2', 'b tag 10', 'Émile'], 'new row sorted in on next header click: %s %s' % (col(eqt, 0), eqt.sort_column))
# editing a cell while sorted clears indicator, no jump
er = col(eqt, 0).index('a tag')
t.item(er, 1).setText('zzz edited'); app.processEvents()
check(t.item(er, 1).text() == 'zzz edited' and not h.isSortIndicatorShown(), 'edit in sorted table stays put')

# --- remove while sorted ---------------------------------------------------
click_header(eqt, 1); click_header(eqt, 1)  # Second desc
target = ['Émile', 'x']
row = [i for i, v in enumerate(eqt.values()) if v == target][0]
t.clearSelection(); t.selectRow(row); eqt.remove_rows()
check(target not in eqt.values() and len(eqt.values()) == 4, 'removed exactly the selected rule')
# multi-select removal on combinations, sorted by Combo desc
click_header(cot, 2); click_header(cot, 2)
ct = cot.table
ct.clearSelection()
ct.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
rows_vals = cot.values()
for i, v in enumerate(rows_vals):
    if v[2] in ('Western Romance', 'Comedic Horror'):
        ct.selectRow(i)
cot.remove_rows()
check(cot.values() == [['fantasy fiction', 'Political Fiction', 'Political Fantasy']], 'multi-remove while sorted: %s' % cot.values())

# --- save integrity ---------------------------------------------------------
cot.add_row(values=['P1', 'P2', 'C'], edit=False)
check(w.validate(), 'validate ok')
w.save_settings()
exp_eq = sorted(map(tuple, eqt.values()))
check(sorted(map(tuple, prefs['equivalents'])) == exp_eq and len(prefs['equivalents']) == 4,
      'saved equivalents exactly match table: %s' % prefs['equivalents'])
check(prefs['equivalents'] == eqt.values(), 'saved in displayed (sorted) order')
check(sorted(map(tuple, prefs['combinations'])) == sorted([('fantasy fiction', 'Political Fiction', 'Political Fantasy'), ('P1', 'P2', 'C')]), 'saved combinations exact')

# --- export / import -------------------------------------------------------
tmp = tempfile.mkdtemp(prefix='tm-io-')
errors = []
w.show_error = lambda title, msg, det='': errors.append((msg, det))
saved_prefs = (json.dumps(prefs['equivalents']), json.dumps(prefs['combinations']))
eqt.add_row(values=['Unsaved Ünïcode 日本', 'edit'], edit=False)   # unsaved edit
eqt.add_row(values=['incomplete', ''], edit=False)
asked = []
w.confirm_skip_incomplete = lambda p: asked.append(p) or False
w.choose_export_path = lambda: os.path.join(tmp, 'never')
check(w.export_rules() is None and not os.listdir(tmp), 'export cancelled at incomplete-row warning writes nothing')
check(asked and 'Equivalents row' in asked[0][0], 'incomplete-row warning shown')
w.confirm_skip_incomplete = lambda p: True
w.choose_export_path = lambda: os.path.join(tmp, 'rules')
path = w.export_rules()
check(path and path.endswith('rules.json') and os.path.exists(path), 'export wrote .json')
data = json.loads(open(path, encoding='utf-8').read())
check({'first': 'Unsaved Ünïcode 日本', 'second': 'edit'} in data['equivalents'], 'export includes unsaved edits (unicode)')
check(all(r['first'] != 'incomplete' for r in data['equivalents']), 'incomplete row not exported')
check(json.dumps(prefs['equivalents']) == saved_prefs[0], 'export did not save prefs')

# replace
other = os.path.join(tmp, 'other.json')
open(other, 'wb').write(rules_io.export_bytes([['X', 'Y'], ['y', 'x']], [['A', 'B', 'C']]))
w.choose_import_path = lambda: other
w.ask_import_mode = lambda a, b: 'replace'
check(w.import_rules() == 'replace', 'import replace')
check(eqt.values() == [['X', 'Y']] and cot.values() == [['A', 'B', 'C']], 'replace deduped: %s' % eqt.values())
check(json.dumps(prefs['equivalents']) == saved_prefs[0], 'import does not touch prefs before OK')
# merge back the earlier export: dedupe case-insensitive
open(other, 'wb').write(rules_io.export_bytes([['x', 'y'], ['New', 'Rule']], [['b', 'a', 'c'], ['A', 'B', 'D']]))
w.ask_import_mode = lambda a, b: 'merge'
check(w.import_rules() == 'merge', 'import merge')
check(eqt.values() == [['X', 'Y'], ['New', 'Rule']], 'merge dedupe eq: %s' % eqt.values())
check(cot.values() == [['A', 'B', 'C'], ['A', 'B', 'D']], 'merge dedupe combos: %s' % cot.values())
# cancel
w.ask_import_mode = lambda a, b: None
check(w.import_rules() is None and eqt.values() == [['X', 'Y'], ['New', 'Rule']], 'import cancel changes nothing')
# invalid
open(other, 'w').write(json.dumps({'format': rules_io.FORMAT, 'schema_version': 1,
                                   'equivalents': [{'first': 'only'}]}))
w.ask_import_mode = lambda a, b: 'replace'
check(w.import_rules() is None and eqt.values() == [['X', 'Y'], ['New', 'Rule']], 'invalid file rejected, dialog unchanged')
check(errors and 'missing or empty second' in errors[-1][1], 'clear error shown: %s' % (errors[-1:],))
w.save_settings()
check(prefs['equivalents'] == [['X', 'Y'], ['New', 'Rule']], 'OK/save persists imported rules')

# --- preview sorting does not affect writes -------------------------------
class FakeAPI:
    library_id = 'L'
    def __init__(s):
        s.books = {1: ('zebra', ('A',)), 2: ('Apple 10', ('A',)), 3: ('apple 2', ('A',)), 4: ('none', ('Q',))}
        s.writes = []
    def all_book_ids(s): return set(s.books)
    def all_field_for(s, f, ids, default_value=None):
        return {i: s.books[i][0 if f == 'title' else 1] for i in ids if i in s.books}
    def set_field(s, f, m, allow_case_change=True):
        s.writes.append(dict(m))
        for i, v in m.items(): s.books[i] = (s.books[i][0], tuple(v))
api = FakeAPI()
plan = writer.scan(api, engine.Rules([['A', 'B']], []))
order_before = [c.book_id for c in plan.changes]
d = preview.PreviewDialog(None, plan)
check(d.displayed_book_ids() == [1, 2, 3], 'preview initially sorted by ID')
d.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
check(d.displayed_book_ids() == [3, 2, 1], 'preview Title asc natural: %s' % d.displayed_book_ids())
d.table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
check(d.displayed_book_ids() == [3, 2, 1], 'preview ID desc numeric')
for c in (2, 3, 4, 5):
    d.table.sortByColumn(c, Qt.SortOrder.DescendingOrder)
check(sorted(d.displayed_book_ids()) == [1, 2, 3] and d.table.rowCount() == 3, 'tag columns sortable, rows intact')
check([c.book_id for c in plan.changes] == order_before, 'plan unaffected by preview sort')
res = writer.commit(api, plan)
check(api.writes == [{1: ('A', 'B'), 2: ('A', 'B'), 3: ('A', 'B')}] and 4 not in api.writes[0],
      'written books identical regardless of sort')
# id sort numeric with >9 ids
api2 = FakeAPI(); api2.books = {i: ('t%d' % i, ('A',)) for i in (2, 10, 9, 100)}
d2 = preview.PreviewDialog(None, writer.scan(api2, engine.Rules([['A', 'B']], [])))
d2.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
check(d2.displayed_book_ids() == [2, 9, 10, 100], 'ID numeric (not lexical) sort')

print('\n%d FAILURE(S)' % len(failures) if failures else '\nALL UI TESTS PASSED')
raise SystemExit(1 if failures else 0)
