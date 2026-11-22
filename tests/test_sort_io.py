import json, os, random, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'subtag_manager'))

import engine
import rules_io
from engine import natural_key, Rules, compute_book_change

EQ = [['Gothic Fiction.Gothic Horror', 'Horror Fiction.Gothic Horror'],
      ['Cowboy Fiction', 'Western Fiction']]
CO = [['Romance Fiction', 'Western Fiction', 'Western Romance'],
      ['Fantasy Fiction', 'Political Fiction', 'Political Fantasy']]


class TestNaturalKey(unittest.TestCase):
    def test_case_insensitive_and_numbers(self):
        vals = ['book 10', 'Book 2', 'apple', 'Banana', 'book 1']
        self.assertEqual(sorted(vals, key=natural_key),
                         ['apple', 'Banana', 'book 1', 'Book 2', 'book 10'])

    def test_accents_and_ints(self):
        self.assertLess(natural_key('Émile'), natural_key('Fred'))
        self.assertEqual(sorted([10, 2, 33], key=natural_key), [2, 10, 33])
        self.assertEqual(natural_key(''), ())


class TestRuleOrderIrrelevant(unittest.TestCase):
    def test_shuffled_rules_same_result(self):
        tags = ['Cowboy Fiction', 'Romance Fiction', 'Fantasy Fiction.High Fantasy',
                'Political Fiction', 'Gothic Fiction.Gothic Horror']
        base = set(compute_book_change(1, 't', tags, Rules(EQ, CO)).final)
        rnd = random.Random(7)
        for _ in range(20):
            eq = [list(r) for r in EQ]; co = [list(r) for r in CO]
            rnd.shuffle(eq); rnd.shuffle(co)
            for r in eq:
                rnd.shuffle(r)  # equivalents are symmetric
            self.assertEqual(set(compute_book_change(1, 't', tags, Rules(eq, co)).final), base)


class TestRulesIO(unittest.TestCase):
    def test_round_trip(self):
        raw = rules_io.export_bytes(EQ, CO)
        d = json.loads(raw.decode('utf-8'))
        self.assertEqual(d['format'], rules_io.FORMAT)
        self.assertEqual(d['schema_version'], 1)
        self.assertEqual(d['equivalents'][0], {'first': EQ[0][0], 'second': EQ[0][1]})
        self.assertEqual(rules_io.parse_bytes(raw), (EQ, CO))

    def test_unicode_round_trip(self):
        eq = [['Fiction ÉTRANGÈRE.Roman noir', 'Ficción.Novela negra'], ['日本文学', 'Japanese Literature']]
        co = [['Fantasy Fiction', 'Литература', 'Ünïcödé Combo 🐉']]
        raw = rules_io.export_bytes(eq, co)
        self.assertIn('日本文学'.encode('utf-8'), raw)  # real UTF-8, not \\u escapes
        self.assertEqual(rules_io.parse_bytes(raw), (eq, co))
        self.assertEqual(rules_io.parse_bytes(b'\xef\xbb\xbf' + raw), (eq, co))  # BOM ok

    def test_export_skips_incomplete_and_blank(self):
        d = rules_io.export_dict([['a', 'b'], ['', ''], ['c', '']], [['p', 'q', ''], ['p', 'q', 'r']])
        self.assertEqual(d['equivalents'], [{'first': 'a', 'second': 'b'}])
        self.assertEqual(d['combinations'], [{'parent1': 'p', 'parent2': 'q', 'combo': 'r'}])

    def test_list_rows_accepted(self):
        raw = json.dumps({'format': rules_io.FORMAT, 'schema_version': 1,
                          'equivalents': [['a', 'b']], 'combinations': [['p', 'q', 'r']]})
        self.assertEqual(rules_io.parse_bytes(raw), ([['a', 'b']], [['p', 'q', 'r']]))

    def assertRejected(self, raw, fragment):
        with self.assertRaises(rules_io.RulesFileError) as cm:
            rules_io.parse_bytes(raw)
        self.assertIn(fragment, str(cm.exception))
        return cm.exception

    def test_validation(self):
        F = rules_io.FORMAT
        self.assertRejected(b'not json', 'not valid JSON')
        self.assertRejected(b'\xff\xfe\x00', 'not valid UTF-8')
        self.assertRejected('[]', 'JSON object')
        self.assertRejected(json.dumps({'schema_version': 1}), 'Not a Subtag Manager rules file')
        self.assertRejected(json.dumps({'format': F}), 'schema_version')
        self.assertRejected(json.dumps({'format': F, 'schema_version': 99}), 'update the plugin')
        self.assertRejected(json.dumps({'format': F, 'schema_version': 1, 'equivalents': {}}), 'must be a list')
        e = self.assertRejected(json.dumps({
            'format': F, 'schema_version': 1,
            'equivalents': [{'first': 'a', 'second': 'b'}, {'first': 'a', 'second': '  '},
                            ['only one'], {'first': 'a', 'second': 'b', 'third': 'x'}, 5],
            'combinations': [{'parent1': 'p', 'parent2': 'q'}, ['p', 'q', 3]]}),
            'Equivalents row 2: missing or empty second')
        txt = str(e)
        for frag in ('Equivalents row 3: expected 2 values', 'Equivalents row 4: unknown field(s) third',
                     'Equivalents row 5: must be an object', 'Combinations row 1: missing or empty combo',
                     'Combinations row 2: missing or empty combo'):
            self.assertIn(frag, txt)
        self.assertEqual(len(e.problems), 6)

    def test_merge_dedupes_case_insensitively(self):
        cur = [['Gothic Fiction.Gothic Horror', 'Horror Fiction.Gothic Horror']]
        inc = [['horror fiction . gothic horror', 'GOTHIC FICTION.GOTHIC HORROR'],  # same pair, swapped
               ['New A', 'New B'], ['new a', 'new b']]
        self.assertEqual(rules_io.merge(cur, inc, rules_io.eq_key), cur + [['New A', 'New B']])
        cur_co = [['Romance Fiction', 'Western Fiction', 'Western Romance']]
        inc_co = [['western fiction', 'ROMANCE FICTION', 'western romance'],
                  ['Romance Fiction', 'Western Fiction', 'Cowboy Romance']]
        self.assertEqual(rules_io.merge(cur_co, inc_co, rules_io.co_key),
                         cur_co + [['Romance Fiction', 'Western Fiction', 'Cowboy Romance']])

    def test_replace_dedupe(self):
        self.assertEqual(rules_io.dedupe([['a', 'b'], ['B', 'A'], ['a', 'c']], rules_io.eq_key),
                         [['a', 'b'], ['a', 'c']])


    def test_legacy_tag_manager_format_accepted(self):
        raw = json.dumps({
            'format': 'calibre-tag-manager-rules',
            'schema_version': 1,
            'equivalents': [{'first': 'A', 'second': 'B'}],
            'combinations': [{'parent1': 'P', 'parent2': 'Q', 'combo': 'C'}],
        })
        self.assertEqual(rules_io.parse_bytes(raw), ([['A', 'B']], [['P', 'Q', 'C']]))
        # newly exported files use the Subtag Manager identifier
        exported = json.loads(rules_io.export_bytes([['A', 'B']], []).decode('utf-8'))
        self.assertEqual(exported['format'], 'calibre-subtag-manager-rules')

    def test_copy_legacy_rules(self):
        import tempfile
        tmp = tempfile.mkdtemp(prefix='stm-migrate-')
        old = os.path.join(tmp, 'tag_manager.json')
        new = os.path.join(tmp, 'subtag_manager.json')
        payload = {'schema_version': 1, 'equivalents': EQ, 'combinations': CO}
        with open(old, 'w', encoding='utf-8') as f:
            json.dump(payload, f)
        self.assertTrue(rules_io.copy_legacy_rules(new, old))
        with open(new, encoding='utf-8') as f:
            got = json.load(f)
        self.assertEqual(got['equivalents'], EQ)
        self.assertEqual(got['combinations'], CO)
        self.assertEqual(got['schema_version'], 1)
        # once only: a later change to the old file is not copied over
        with open(old, 'w', encoding='utf-8') as f:
            json.dump({'schema_version': 1, 'equivalents': [['X', 'Y']], 'combinations': []}, f)
        self.assertFalse(rules_io.copy_legacy_rules(new, old))
        with open(new, encoding='utf-8') as f:
            self.assertEqual(json.load(f)['equivalents'], EQ)
        # existing empty new file is not overwritten
        tmp2 = tempfile.mkdtemp(prefix='stm-migrate-empty-')
        old2 = os.path.join(tmp2, 'tag_manager.json')
        new2 = os.path.join(tmp2, 'subtag_manager.json')
        with open(old2, 'w', encoding='utf-8') as f:
            json.dump(payload, f)
        with open(new2, 'w', encoding='utf-8') as f:
            json.dump({'schema_version': 1, 'equivalents': [], 'combinations': []}, f)
        self.assertFalse(rules_io.copy_legacy_rules(new2, old2))
        # missing old file: nothing is created
        new3 = os.path.join(tmp2, 'missing-new.json')
        self.assertFalse(rules_io.copy_legacy_rules(new3, os.path.join(tmp2, 'nope.json')))
        self.assertFalse(os.path.exists(new3))
        # empty old rules: nothing is created
        with open(old2, 'w', encoding='utf-8') as f:
            json.dump({'schema_version': 1, 'equivalents': [], 'combinations': []}, f)
        new4 = os.path.join(tmp2, 'from-empty-old.json')
        self.assertFalse(rules_io.copy_legacy_rules(new4, old2))
        self.assertFalse(os.path.exists(new4))



if __name__ == '__main__':
    unittest.main()
