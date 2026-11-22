# -*- coding: utf-8 -*-
"""Persistent settings (calibre JSONConfig) - no Qt imports.

Rules are stored in plugins/subtag_manager.json. On first load, if that file
does not yet exist and the older Tag Manager file plugins/tag_manager.json
exists, its rules are copied once.
"""
import os

from calibre.utils.config import JSONConfig, config_dir

from calibre_plugins.subtag_manager.rules_io import copy_legacy_rules

# Migrate before JSONConfig loads, so the first read sees the copied rules.
copy_legacy_rules(os.path.join(config_dir, 'plugins', 'subtag_manager.json'),
                  os.path.join(config_dir, 'plugins', 'tag_manager.json'))

prefs = JSONConfig('plugins/subtag_manager')
prefs.defaults['schema_version'] = 1
prefs.defaults['equivalents'] = []    # list of [first, second]
prefs.defaults['combinations'] = []   # list of [parent1, parent2, combo]
