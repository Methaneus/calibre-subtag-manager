"""Run with a throwaway config dir that already contains plugins/tag_manager.json
BEFORE this script (and before calibre-customize) so the first prefs import
migrates the rules.

  CALIBRE_CONFIG_DIRECTORY=/tmp/stm-cfg-migrate QT_QPA_PLATFORM=offscreen \
    calibre-debug tests/calibre_migrate_test.py
"""
import json, os
from calibre.customize.ui import find_plugin
from calibre.utils.config import config_dir
from calibre_plugins.subtag_manager.prefs import prefs

base = find_plugin('Subtag Manager')
assert base is not None and base.version == (1, 2, 0), base and getattr(base, 'version', None)
assert base.name == 'Subtag Manager'
new = os.path.join(config_dir, 'plugins', 'subtag_manager.json')
old = os.path.join(config_dir, 'plugins', 'tag_manager.json')
assert os.path.exists(old), 'expected pre-seeded old config %s' % old
assert os.path.exists(new), 'old rules were not migrated to %s' % new
with open(new, encoding='utf-8') as f:
    data = json.load(f)
assert data['equivalents'] == [['Gothic Fiction.Gothic Horror', 'Horror Fiction.Gothic Horror']]
assert data['combinations'] == [['Romance Fiction', 'Western Fiction', 'Western Romance']]
assert prefs['equivalents'] == data['equivalents']
assert prefs['combinations'] == data['combinations']
print('MIGRATE TEST PASSED')
