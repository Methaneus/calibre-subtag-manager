# -*- coding: utf-8 -*-
"""Toolbar action: scan whole library (read-only) -> per-book preview ->
write only after explicit Apply."""

from qt.core import QApplication, QCursor, QDialog, QMenu, QToolButton, Qt

from calibre.gui2 import error_dialog, info_dialog
from calibre.gui2.actions import InterfaceAction

from calibre_plugins.subtag_manager.engine import Rules
from calibre_plugins.subtag_manager.prefs import prefs
from calibre_plugins.subtag_manager import writer


class SubtagManagerAction(InterfaceAction):

    name = 'Subtag Manager'
    action_spec = ('Subtag Manager', None,
                   'Apply Subtag Manager rules to all books (shows a preview first)', None)
    popup_type = QToolButton.ToolButtonPopupMode.MenuButtonPopup
    action_type = 'current'
    dont_add_to = frozenset(['context-menu-device'])

    def genesis(self):
        icon = get_icons('images/icon.png', 'Subtag Manager')  # noqa: F821 (calibre builtin)
        self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.apply_to_library)
        self.menu = QMenu(self.gui)
        self.create_menu_action(self.menu, 'subtag-manager-apply', 'Apply rules to library...',
                                icon=icon, triggered=self.apply_to_library)
        self.menu.addSeparator()
        self.create_menu_action(self.menu, 'subtag-manager-configure', 'Configure rules...',
                                icon='config.png', triggered=self.show_configuration)
        self.qaction.setMenu(self.menu)

    def apply_settings(self):
        pass

    def show_configuration(self):
        self.interface_action_base_plugin.do_user_config(self.gui)

    def apply_to_library(self, *args):
        rules = Rules.from_prefs(prefs)
        if rules.is_empty():
            return info_dialog(self.gui, 'Subtag Manager',
                               'No rules are configured. Use "Configure rules..." from the '
                               'Subtag Manager toolbar menu first.', show=True)
        api = self.gui.current_db.new_api
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            plan = writer.scan(api, rules)          # read-only
        except Exception:
            QApplication.restoreOverrideCursor()
            import traceback
            return error_dialog(self.gui, 'Subtag Manager', 'Scanning the library failed.',
                                det_msg=traceback.format_exc(), show=True)
        QApplication.restoreOverrideCursor()

        if not plan.changes:
            msg = 'Scanned %d book(s). No tag changes are needed.' % plan.scanned
            if plan.warnings:
                msg += ' %d book(s) were skipped because the rules did not converge.' % len(plan.warnings)
            return info_dialog(self.gui, 'Subtag Manager', msg, show=True)

        from calibre_plugins.subtag_manager.preview import PreviewDialog
        d = PreviewDialog(self.gui, plan)
        if d.exec() != QDialog.DialogCode.Accepted:
            return  # cancelled / closed: nothing written

        # Re-fetch the current db: the user may have switched libraries.
        current_api = self.gui.current_db.new_api
        try:
            result = writer.commit(current_api, plan)
        except Exception:
            import traceback
            return error_dialog(self.gui, 'Subtag Manager', 'Writing tags failed.',
                                det_msg=traceback.format_exc(), show=True)
        if result.aborted_reason:
            return error_dialog(self.gui, 'Subtag Manager', result.aborted_reason, show=True)
        if result.written:
            self.refresh_gui(result.written)
        msg = 'Updated tags on %d book(s).' % len(result.written)
        det = []
        if result.stale:
            det.append('Skipped because their tags changed after the scan (run again): ' +
                       ', '.join(map(str, result.stale)))
        if result.missing:
            det.append('Skipped because they no longer exist: ' + ', '.join(map(str, result.missing)))
        if det:
            msg += ' Some books were skipped; see details.'
        info_dialog(self.gui, 'Subtag Manager', msg, det_msg='\n'.join(det), show=True)

    def refresh_gui(self, book_ids):
        em = self.gui.iactions.get('Edit Metadata')
        if em is not None and hasattr(em, 'refresh_gui'):
            em.refresh_gui(book_ids, covers_changed=False, tag_browser_changed=True)
            return
        m = self.gui.library_view.model()
        m.refresh_ids(list(book_ids), current_row=self.gui.library_view.currentIndex().row())
        self.gui.tags_view.recount()

    def library_changed(self, db):
        pass
