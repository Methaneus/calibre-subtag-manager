# -*- coding: utf-8 -*-
"""Per-book confirmation dialog shown after the read-only scan."""

from qt.core import (QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView,
                     QLabel, QPlainTextEdit, QTableWidget, QTableWidgetItem,
                     QVBoxLayout, Qt)

from calibre_plugins.subtag_manager.engine import natural_key


class NaturalItem(QTableWidgetItem):
    def __lt__(self, other):
        return natural_key(self.text()) < natural_key(other.text())


class IdItem(QTableWidgetItem):
    def __lt__(self, other):
        return int(self.data(Qt.ItemDataRole.DisplayRole)) < int(other.data(Qt.ItemDataRole.DisplayRole))


class PreviewDialog(QDialog):
    """Columns are sortable by clicking their headers (ID numerically, the
    others case-insensitively in natural order).
    exec() returns Accepted ONLY if the user clicked "Apply changes".
    Cancel, Escape and closing the window all reject (no writes)."""

    COLUMNS = ['ID', 'Title', 'Current tags', 'Tags to add', 'Tags to remove', 'Resulting tags']

    def __init__(self, parent, plan):
        QDialog.__init__(self, parent)
        self.setWindowTitle('Subtag Manager - confirm changes')
        self.plan = plan
        l = QVBoxLayout(self)
        n = len(plan.changes)
        summary = QLabel(
            '<b>%d of %d book(s) would be changed</b> (%d tag addition(s), %d removal(s)).<br>'
            'Nothing has been written yet. Review the changes for each book below, then click '
            '<i>Apply changes</i> to write them, or <i>Cancel</i> to leave the library untouched.'
            % (n, plan.scanned, plan.total_added, plan.total_removed), self)
        summary.setWordWrap(True)
        l.addWidget(summary)

        self.table = t = QTableWidget(n, len(self.COLUMNS), self)
        t.setHorizontalHeaderLabels(self.COLUMNS)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setWordWrap(True)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        for r, c in enumerate(plan.changes):
            vals = [c.book_id, c.title, ', '.join(c.original),
                    '\n'.join('+ ' + x for x in c.added),
                    '\n'.join('- ' + x for x in c.removed),
                    ', '.join(c.final)]
            for col, v in enumerate(vals):
                if col == 0:
                    it = IdItem()
                    it.setData(Qt.ItemDataRole.DisplayRole, int(v))
                    it.setData(Qt.ItemDataRole.UserRole, int(v))
                else:
                    it = NaturalItem(str(v))
                    it.setToolTip(str(v))
                t.setItem(r, col, it)
        h = t.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setStretchLastSection(True)
        t.resizeColumnsToContents()
        for col, w in ((1, 220), (2, 260), (3, 220), (4, 180)):
            t.setColumnWidth(col, min(max(t.columnWidth(col), 80), w))
        t.resizeRowsToContents()
        # Sorting only reorders the on-screen rows. What is written is
        # decided by self.plan, which sorting never touches.
        t.setSortingEnabled(True)
        t.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        l.addWidget(t, 1)

        if plan.warnings:
            w = QPlainTextEdit(self)
            w.setReadOnly(True)
            w.setMaximumHeight(90)
            w.setPlainText('Skipped (rules did not converge, book left unchanged):\n' + '\n'.join(
                '#%s %s' % (c.book_id, c.title) for c in plan.warnings))
            l.addWidget(w)

        bb = QDialogButtonBox(self)
        self.apply_button = bb.addButton('Apply changes to %d book(s)' % n,
                                         QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_button = bb.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.apply_button.setAutoDefault(False)
        self.apply_button.setDefault(False)
        self.cancel_button.setDefault(True)
        self.cancel_button.setFocus(Qt.FocusReason.OtherFocusReason)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        l.addWidget(bb)
        self.resize(1100, 600)

    def displayed_book_ids(self):
        t = self.table
        return [int(t.item(r, 0).data(Qt.ItemDataRole.UserRole)) for r in range(t.rowCount())]
