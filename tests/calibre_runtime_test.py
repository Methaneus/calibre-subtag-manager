"""Run with: CALIBRE_CONFIG_DIRECTORY=/tmp/tm-cfg QT_QPA_PLATFORM=offscreen \
   calibre-debug tests/calibre_runtime_test.py -- /tmp/tm-lib
Requires the plugin installed (calibre-customize -a Subtag_Manager.zip) into that
throwaway config dir.  Uses a throwaway library only."""
import sys, types
lib = sys.argv[-1]
from calibre.customize.ui import find_plugin
from calibre.library import db as open_db
from calibre.gui2 import Application
app = Application([])
base = find_plugin('Subtag Manager')
assert base is not None, 'plugin not loaded'
base.load_actual_plugin  # exists
from calibre_plugins.subtag_manager.prefs import prefs
from calibre_plugins.subtag_manager import writer, engine, config, preview, ui
from qt.core import QDialog, QDialogButtonBox

# --- config widget -------------------------------------------------------
prefs['equivalents'] = []; prefs['combinations'] = []
w = base.config_widget()
assert [w.tabs.tabText(i) for i in range(w.tabs.count())] == ['Equivalents', 'Combinations']
eqt = w.equivalents.table; cot = w.combinations.table
assert [eqt.horizontalHeaderItem(i).text() for i in range(2)] == ['First', 'Second']
assert [cot.horizontalHeaderItem(i).text() for i in range(3)] == ['Parent 1', 'Parent 2', 'Combo']
w.equivalents.add_row(values=['Gothic Fiction.Gothic Horror', 'Horror Fiction.Gothic Horror'], edit=False)
w.equivalents.add_row(values=['junk', 'row'], edit=False)
eqt.selectRow(1); w.equivalents.remove_rows()
assert eqt.rowCount() == 1
for r in (['Romance Fiction', 'Western Fiction', 'Western Romance'],
          ['Fantasy Fiction', 'Political Fiction', 'Political Fantasy']):
    w.combinations.add_row(values=r, edit=False)
w.combinations.add_row(values=['Only one', '', ''], edit=False)
import calibre.gui2 as g2
g2.error_dialog = lambda *a, **k: None
assert w.validate() is False, 'incomplete row must fail validation'
cot.selectRow(2); w.combinations.remove_rows()
assert w.validate() is True
base.save_settings(w)
print('saved prefs:', prefs['equivalents'], prefs['combinations'])

# --- scan real (throwaway) library --------------------------------------
db = open_db(lib)
api = db.new_api
before = api.all_field_for('tags', api.all_book_ids())
rules = engine.Rules.from_prefs(prefs)
plan = writer.scan(api, rules)
assert api.all_field_for('tags', api.all_book_ids()) == before, 'scan wrote!'
for c in plan.changes:
    print('PLAN', c.book_id, c.title, c.original, '+', c.added, '-', c.removed)

# --- preview dialog: default Cancel, reject => nothing written ----------
d = preview.PreviewDialog(None, plan)
assert d.table.rowCount() == len(plan.changes)
assert d.cancel_button.isDefault() and not d.apply_button.isDefault()
d.reject(); assert d.result() == QDialog.DialogCode.Rejected

# --- drive the real toolbar action code with a fake gui -------------------
from qt.core import QWidget
class FakeGui(QWidget):
    def __init__(self, db):
        QWidget.__init__(self)
        self.current_db = db
        self.refreshed = None
        self.iactions = {'Edit Metadata': types.SimpleNamespace(
            refresh_gui=lambda ids, **k: setattr(self, 'refreshed', list(ids)))}
ui.info_dialog = lambda *a, **k: print('INFO:', a[2], k.get('det_msg', ''))
ui.error_dialog = lambda *a, **k: print('ERROR:', a[2])
gui = FakeGui(db)
fake_self = types.SimpleNamespace(gui=gui)
fake_self.refresh_gui = lambda ids: ui.SubtagManagerAction.refresh_gui(fake_self, ids)

preview.PreviewDialog.exec = lambda self: QDialog.DialogCode.Rejected
ui.SubtagManagerAction.apply_to_library(fake_self)
assert api.all_field_for('tags', api.all_book_ids()) == before, 'cancel wrote!'
print('cancel: no writes OK')

preview.PreviewDialog.exec = lambda self: QDialog.DialogCode.Accepted
ui.SubtagManagerAction.apply_to_library(fake_self)
after = api.all_field_for('tags', api.all_book_ids())
print('AFTER', after)
print('refreshed ids', gui.refreshed)
assert after != before and gui.refreshed
plan2 = writer.scan(api, rules)
assert not plan2.changes, 'not idempotent'
print('second scan: no changes OK')
db.close()
print('RUNTIME TEST PASSED')
