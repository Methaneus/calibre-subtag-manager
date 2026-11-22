# -*- coding: utf-8 -*-
from calibre.customize import InterfaceActionBase


class SubtagManagerBase(InterfaceActionBase):
    name = 'Subtag Manager'
    description = ('Apply tag Equivalents and Combinations rules to every book in the '
                   'library, with a per-book confirmation preview before writing.')
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'Meth'
    version = (1, 2, 0)
    minimum_calibre_version = (6, 0, 0)

    actual_plugin = 'calibre_plugins.subtag_manager.ui:SubtagManagerAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.subtag_manager.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
        ac = self.actual_plugin_
        if ac is not None:
            ac.apply_settings()
