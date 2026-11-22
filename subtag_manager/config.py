# -*- coding: utf-8 -*-
"""Configuration widget: tabs "Equivalents" and "Combinations", each an
editable, sortable table with a compact "+" button at the top right and "-"
button at the bottom right, plus Export.../Import... buttons.

Sorting: clicking a column header sorts the rows (click again to reverse);
the header shows a sort indicator.  Sorting is a one-shot re-ordering of the
rows (not a live sort), so rows never jump around while being edited and a
newly added row stays at the bottom, ready for editing, until the next
header click.  When rows are added or edited the indicator is cleared,
because the table may no longer be in sorted order.
"""

from qt.core import (QAbstractItemDelegate, QAbstractItemView, QApplication, QHBoxLayout, QHeaderView, QIcon,
                     QLabel, QMessageBox, QPushButton, Qt, QTableWidget,
                     QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout,
                     QWidget)

from calibre_plugins.subtag_manager.prefs import prefs
from calibre_plugins.subtag_manager.engine import Rules, natural_key
from calibre_plugins.subtag_manager import rules_io


class NaturalItem(QTableWidgetItem):
    """Table item sorting case-insensitively with natural number order."""

    def __lt__(self, other):
        return natural_key(self.text()) < natural_key(other.text())


class RuleTable(QWidget):

    def __init__(self, headers, rows, parent=None):
        QWidget.__init__(self, parent)
        self.headers = headers
        self.sort_column, self.sort_order = -1, Qt.SortOrder.AscendingOrder
        l = QHBoxLayout(self)
        l.setContentsMargins(4, 4, 4, 4)
        self.table = t = QTableWidget(0, len(headers), self)
        t.setHorizontalHeaderLabels(headers)
        h = t.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        h.setSectionsClickable(True)
        h.setSortIndicatorShown(False)
        h.sectionClicked.connect(self.header_clicked)
        t.setSortingEnabled(False)  # manual, one-shot sorting (see module doc)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(True)
        l.addWidget(t)
        bl = QVBoxLayout()
        self.add_button = b = QToolButton(self)
        b.setIcon(QIcon.ic('plus.png'))
        b.setText('+')
        b.setToolTip('Add a rule')
        b.clicked.connect(self.add_row)
        bl.addWidget(b)
        bl.addStretch(1)
        self.remove_button = b = QToolButton(self)
        b.setIcon(QIcon.ic('minus.png'))
        b.setText('-')
        b.setToolTip('Remove the selected rule(s)')
        b.clicked.connect(self.remove_rows)
        bl.addWidget(b)
        l.addLayout(bl)
        self.set_rows(rows)
        t.itemChanged.connect(self.item_changed)

    # ---- sorting ---------------------------------------------------------
    def header_clicked(self, col):
        if col == self.sort_column:
            order = (Qt.SortOrder.DescendingOrder if self.sort_order == Qt.SortOrder.AscendingOrder
                     else Qt.SortOrder.AscendingOrder)
        else:
            order = Qt.SortOrder.AscendingOrder
        self.sort_by(col, order)

    def sort_by(self, col, order=Qt.SortOrder.AscendingOrder):
        t = self.table
        self.commit_editor()  # an open editor is committed before reordering
        self.sort_column, self.sort_order = col, order
        t.sortItems(col, order)
        h = t.horizontalHeader()
        h.setSortIndicator(col, order)
        h.setSortIndicatorShown(True)

    def commit_editor(self):
        t = self.table
        if t.state() != QAbstractItemView.State.EditingState:
            return
        ed = QApplication.focusWidget()
        if ed is None or not t.viewport().isAncestorOf(ed):
            eds = [w for w in t.viewport().findChildren(QWidget) if w.isVisible()]
            ed = eds[0] if eds else None
        if ed is not None:
            t.commitData(ed)
            t.closeEditor(ed, QAbstractItemDelegate.EndEditHint.NoHint)

    def clear_sort_indicator(self):
        self.sort_column = -1
        self.table.horizontalHeader().setSortIndicatorShown(False)

    def item_changed(self, item):
        if self.sort_column > -1:
            self.clear_sort_indicator()

    # ---- rows ------------------------------------------------------------
    def set_rows(self, rows):
        t = self.table
        t.blockSignals(True)
        try:
            t.setRowCount(0)
            for row in rows:
                self._append(row)
        finally:
            t.blockSignals(False)
        self.clear_sort_indicator()

    def _append(self, values):
        t = self.table
        r = t.rowCount()
        t.insertRow(r)
        values = list(values or []) + [''] * len(self.headers)
        for c in range(len(self.headers)):
            t.setItem(r, c, NaturalItem(str(values[c] or '')))
        return r

    def add_row(self, checked=False, values=None, edit=True):
        t = self.table
        t.setSortingEnabled(False)  # never let Qt move the row while inserting
        t.blockSignals(True)
        try:
            r = self._append(values)
        finally:
            t.blockSignals(False)
        self.clear_sort_indicator()
        if edit:
            t.scrollToItem(t.item(r, 0))
            t.setCurrentCell(r, 0)
            t.editItem(t.item(r, 0))
        return r

    def remove_rows(self):
        t = self.table
        self.commit_editor()
        rows = {i.row() for i in t.selectedIndexes()}
        if not rows and t.currentRow() > -1:
            rows = {t.currentRow()}
        for r in sorted(rows, reverse=True):
            t.removeRow(r)

    def values(self):
        """Rows in the order currently displayed."""
        t = self.table
        self.commit_editor()
        out = []
        for r in range(t.rowCount()):
            row = []
            for c in range(t.columnCount()):
                it = t.item(r, c)
                row.append(it.text().strip() if it is not None else '')
            out.append(row)
        return out


class ConfigWidget(QWidget):

    def __init__(self):
        QWidget.__init__(self)
        l = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.equivalents = RuleTable(['First', 'Second'], prefs['equivalents'], self)
        self.combinations = RuleTable(['Parent 1', 'Parent 2', 'Combo'], prefs['combinations'], self)
        self.tabs.addTab(self.equivalents, 'Equivalents')
        self.tabs.addTab(self.combinations, 'Combinations')
        l.addWidget(self.tabs)
        bl = QHBoxLayout()
        self.export_button = QPushButton('&Export...', self)
        self.export_button.setToolTip('Save the rules of both tabs (as currently shown, including '
                                      'unsaved edits) to a JSON file')
        self.export_button.clicked.connect(self.export_rules)
        self.import_button = QPushButton('&Import...', self)
        self.import_button.setToolTip('Load rules from a JSON file exported by Subtag Manager. '
                                      'Nothing is saved until you click OK.')
        self.import_button.clicked.connect(self.import_rules)
        bl.addWidget(self.export_button)
        bl.addWidget(self.import_button)
        bl.addStretch(1)
        l.addLayout(bl)
        hint = QLabel(
            'Equivalents: if a book has either tag, the other is added.<br>'
            'Combinations: if a book has both parents (or subtags of them), '
            '"Parent.Combo" is added for each parent; a bare parent tag is replaced, '
            'existing subtags are kept.<br>Click a column header to sort.', self)
        hint.setWordWrap(True)
        l.addWidget(hint)
        self.resize(640, 440)

    def _rows(self):
        def nonblank(rows):
            return [r for r in rows if any(x.strip() for x in r)]
        return nonblank(self.equivalents.values()), nonblank(self.combinations.values())

    def validate(self):
        eq, co = self._rows()
        problems = Rules(eq, co).problems
        if problems:
            from calibre.gui2 import error_dialog
            error_dialog(self, 'Incomplete rules', 'Please complete or remove these rows:',
                         det_msg='\n'.join(problems), show=True, show_copy_button=False)
            return False
        return True

    def save_settings(self):
        eq, co = self._rows()
        prefs['equivalents'] = eq
        prefs['combinations'] = co

    # ---- export / import (hooks below are overridable for tests) -----------
    def choose_export_path(self):
        from calibre.gui2 import choose_save_file
        return choose_save_file(self, 'subtag-manager-export-rules', 'Export Subtag Manager rules',
                                filters=[('Subtag Manager rules (JSON)', ['json'])],
                                all_files=False, initial_filename='subtag_manager_rules.json')

    def choose_import_path(self):
        from calibre.gui2 import choose_files
        paths = choose_files(self, 'subtag-manager-import-rules', 'Import Subtag Manager rules',
                             filters=[('Subtag Manager rules (JSON)', ['json'])],
                             all_files=True, select_only_single_file=True)
        return paths[0] if paths else None

    def confirm_skip_incomplete(self, problems):
        from calibre.gui2 import question_dialog
        return question_dialog(self, 'Incomplete rules',
                               '%d incomplete row(s) will NOT be exported. Continue?' % len(problems),
                               det_msg='\n'.join(problems), show_copy_button=False)

    def ask_import_mode(self, neq, nco):
        """Return 'replace', 'merge' or None (cancel)."""
        mb = QMessageBox(QMessageBox.Icon.Question, 'Import rules',
                         'The file contains %d equivalent(s) and %d combination(s).\n\n'
                         'Replace the rules shown in this dialog, or merge the imported rules '
                         'into them (duplicates are skipped)?\n\n'
                         'Nothing is saved until you click OK.' % (neq, nco),
                         QMessageBox.StandardButton.Cancel, self)
        rb = mb.addButton('&Replace', QMessageBox.ButtonRole.DestructiveRole)
        mbt = mb.addButton('&Merge', QMessageBox.ButtonRole.AcceptRole)
        mb.setDefaultButton(mbt)
        mb.exec()
        c = mb.clickedButton()
        return 'replace' if c is rb else 'merge' if c is mbt else None

    def show_error(self, title, msg, det=''):
        from calibre.gui2 import error_dialog
        error_dialog(self, title, msg, det_msg=det, show=True)

    def show_info(self, title, msg):
        from calibre.gui2 import info_dialog
        info_dialog(self, title, msg, show=True)

    def export_rules(self, *args):
        eq, co = self._rows()
        problems = Rules(eq, co).problems
        if problems and not self.confirm_skip_incomplete(problems):
            return None
        path = self.choose_export_path()
        if not path:
            return None
        if not path.lower().endswith('.json'):
            path += '.json'
        try:
            with open(path, 'wb') as f:
                f.write(rules_io.export_bytes(eq, co))
        except EnvironmentError as e:
            self.show_error('Export failed', 'Could not write %s' % path, str(e))
            return None
        return path

    def import_rules(self, *args):
        path = self.choose_import_path()
        if not path:
            return None
        try:
            with open(path, 'rb') as f:
                raw = f.read()
            eq, co = rules_io.parse_bytes(raw)
        except rules_io.RulesFileError as e:
            self.show_error('Import failed', 'The file was not imported because it contains '
                            'invalid rules. Nothing was changed.', '\n'.join(e.problems))
            return None
        except EnvironmentError as e:
            self.show_error('Import failed', 'Could not read %s' % path, str(e))
            return None
        mode = self.ask_import_mode(len(eq), len(co))
        if mode == 'replace':
            new_eq = rules_io.dedupe(eq, rules_io.eq_key)
            new_co = rules_io.dedupe(co, rules_io.co_key)
        elif mode == 'merge':
            cur_eq, cur_co = self._rows()
            new_eq = rules_io.merge(cur_eq, eq, rules_io.eq_key)
            new_co = rules_io.merge(cur_co, co, rules_io.co_key)
        else:
            return None
        self.equivalents.set_rows(new_eq)
        self.combinations.set_rows(new_co)
        return mode
