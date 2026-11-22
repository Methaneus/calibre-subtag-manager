import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'subtag_manager'))

import engine
from engine import Rules, compute_book_change, compute_tags, matches_parent, build_plan
import writer

GOTHIC = ('Gothic Fiction.Gothic Horror', 'Horror Fiction.Gothic Horror')


def run(tags, eq=(), co=()):
    return compute_book_change(1, 't', tags, Rules(eq, co))


def keys(seq):
    return sorted(engine.tag_key(t) for t in seq)


class TestMatching(unittest.TestCase):
    def test_exact_and_descendant(self):
        self.assertTrue(matches_parent('Romance Fiction', 'Romance Fiction'))
        self.assertTrue(matches_parent('Romance Fiction.Erotic Romance', 'Romance Fiction'))
        self.assertTrue(matches_parent('romance fiction . erotic romance', 'Romance Fiction'))

    def test_not_ancestor_or_prefix(self):
        self.assertFalse(matches_parent('Romance Fiction', 'Romance Fiction.Erotic Romance'))
        self.assertFalse(matches_parent('Romance Fictionalized', 'Romance Fiction'))
        self.assertFalse(matches_parent('Romance', 'Romance Fiction'))
        self.assertFalse(matches_parent('', 'Romance Fiction'))


class TestEquivalents(unittest.TestCase):
    def test_user_example_both_directions(self):
        c = run(['Gothic Fiction.Gothic Horror'], eq=[GOTHIC])
        self.assertEqual(c.added, ('Horror Fiction.Gothic Horror',))
        c = run(['Horror Fiction.Gothic Horror'], eq=[GOTHIC])
        self.assertEqual(c.added, ('Gothic Fiction.Gothic Horror',))
        self.assertEqual(c.removed, ())

    def test_already_present_no_change(self):
        c = run(list(GOTHIC), eq=[GOTHIC])
        self.assertFalse(c.changed)

    def test_case_insensitive_presence(self):
        c = run(['gothic fiction.gothic horror', 'HORROR FICTION.GOTHIC HORROR'], eq=[GOTHIC])
        self.assertFalse(c.changed)

    def test_exact_only_subtag_does_not_trigger(self):
        c = run(['Gothic Fiction.Gothic Horror.Victorian'], eq=[GOTHIC])
        self.assertFalse(c.changed)
        c = run(['Gothic Fiction'], eq=[GOTHIC])
        self.assertFalse(c.changed)

    def test_transitive_chain_and_cycle(self):
        eq = [('A', 'B'), ('B', 'C'), ('C', 'A')]
        c = run(['C'], eq=eq)
        self.assertEqual(keys(c.final), ['a', 'b', 'c'])
        self.assertTrue(c.converged)

    def test_unrelated_untouched(self):
        c = run(['X', 'Y'], eq=[GOTHIC])
        self.assertFalse(c.changed)


class TestCombinations(unittest.TestCase):
    RW = ('Romance Fiction', 'Western Fiction', 'Western Romance')

    def test_user_example_bare_parents_replaced(self):
        c = run(['Romance Fiction', 'Western Fiction'], co=[self.RW])
        self.assertEqual(set(c.final), {'Romance Fiction.Western Romance', 'Western Fiction.Western Romance'})
        self.assertEqual(set(c.removed), {'Romance Fiction', 'Western Fiction'})

    def test_descendant_parent_matches_and_is_kept(self):
        c = run(['Romance Fiction.Erotic Romance', 'Western Fiction'], co=[self.RW])
        self.assertIn('Romance Fiction.Erotic Romance', c.final)
        self.assertIn('Romance Fiction.Western Romance', c.final)
        self.assertIn('Western Fiction.Western Romance', c.final)
        self.assertEqual(c.removed, ('Western Fiction',))

    def test_fantasy_example(self):
        co = [('Fantasy Fiction', 'Political Fiction', 'Political Fantasy')]
        c = run(['Fantasy Fiction.High Fantasy', 'Political Fiction'], co=co)
        self.assertIn('Fantasy Fiction.High Fantasy', c.final)
        self.assertIn('Fantasy Fiction.Political Fantasy', c.final)
        self.assertNotIn('Fantasy Fiction.High Fantasy', c.removed)
        c = run(['Fantasy Fiction', 'Political Fiction'], co=co)
        self.assertIn('Fantasy Fiction.Political Fantasy', c.final)
        self.assertIn('Fantasy Fiction', c.removed)

    def test_bare_and_descendant_both_present(self):
        co = [('Fantasy Fiction', 'Political Fiction', 'Political Fantasy')]
        c = run(['Fantasy Fiction', 'Fantasy Fiction.High Fantasy', 'Political Fiction'], co=co)
        self.assertEqual(set(c.removed), {'Fantasy Fiction', 'Political Fiction'})
        self.assertIn('Fantasy Fiction.High Fantasy', c.final)

    def test_specific_parent_not_matched_by_general_tag(self):
        co = [('Romance Fiction.Erotic Romance', 'Western Fiction', 'Erotic Western')]
        c = run(['Romance Fiction', 'Western Fiction'], co=co)
        self.assertFalse(c.changed)
        c = run(['Romance Fiction.Erotic Romance', 'Western Fiction'], co=co)
        self.assertIn('Romance Fiction.Erotic Romance.Erotic Western', c.final)
        self.assertNotIn('Romance Fiction.Erotic Romance', c.final)  # bare (exact) parent replaced

    def test_needs_both_parents(self):
        c = run(['Romance Fiction'], co=[self.RW])
        self.assertFalse(c.changed)

    def test_prefix_without_dot_does_not_match(self):
        c = run(['Romance Fictionalized', 'Western Fiction'], co=[self.RW])
        self.assertFalse(c.changed)

    def test_all_combos_evaluated_before_removals(self):
        # Both rules share "Romance Fiction"; removal of bare parent by the
        # first rule must not prevent the second rule from matching.
        co = [self.RW, ('Romance Fiction', 'Historical Fiction', 'Historical Romance')]
        c = run(['Romance Fiction', 'Western Fiction', 'Historical Fiction'], co=co)
        self.assertEqual(set(c.final), {
            'Romance Fiction.Western Romance', 'Western Fiction.Western Romance',
            'Romance Fiction.Historical Romance', 'Historical Fiction.Historical Romance'})

    def test_existing_combo_tag_not_duplicated(self):
        c = run(['Romance Fiction.Western Romance', 'Western Fiction.Western Romance'], co=[self.RW])
        self.assertFalse(c.changed)


class TestInteractions(unittest.TestCase):
    def test_equivalent_feeds_combination(self):
        eq = [('Cowboy Fiction', 'Western Fiction')]
        co = [('Romance Fiction', 'Western Fiction', 'Western Romance')]
        c = run(['Cowboy Fiction', 'Romance Fiction'], eq=eq, co=co)
        self.assertEqual(set(c.final), {'Cowboy Fiction', 'Romance Fiction.Western Romance',
                                        'Western Fiction.Western Romance'})

    def test_combination_output_feeds_equivalent_and_next_combo(self):
        eq = [('Romance Fiction.Western Romance', 'Western Romance')]
        co = [('Romance Fiction', 'Western Fiction', 'Western Romance'),
              ('Western Romance', 'Historical Fiction', 'Historical Western Romance')]
        c = run(['Romance Fiction', 'Western Fiction', 'Historical Fiction'], eq=eq, co=co)
        self.assertIn('Western Romance.Historical Western Romance', c.final)
        self.assertIn('Historical Fiction.Historical Western Romance', c.final)
        self.assertTrue(c.converged)

    def test_equivalence_of_bare_parent_does_not_oscillate(self):
        eq = [('Romance Fiction', 'Love Stories')]
        co = [('Romance Fiction', 'Western Fiction', 'Western Romance')]
        c = run(['Love Stories', 'Western Fiction'], eq=eq, co=co)
        self.assertTrue(c.converged)
        self.assertNotIn('Romance Fiction', c.final)
        self.assertIn('Romance Fiction.Western Romance', c.final)

    def test_self_referential_combo_terminates(self):
        co = [('A', 'B', 'A'), ('A.A', 'B', 'A')]
        c = run(['A', 'B'], co=co)
        self.assertTrue(c.converged or not c.changed)

    def test_nonconvergence_guard(self):
        orig = engine._one_pass
        state = {'n': 0}

        def flip(tags, rules):  # pathological pass that alternates forever
            state['n'] += 1
            return engine._TagSet(['X'] if state['n'] % 2 else ['Y'])
        engine._one_pass = flip
        try:
            c = run(['Y'], eq=[('P', 'Q')])
        finally:
            engine._one_pass = orig
        self.assertFalse(c.converged)
        self.assertFalse(c.changed)
        self.assertEqual(c.final, ('Y',))


class TestIdempotence(unittest.TestCase):
    CASES = [
        (['Romance Fiction', 'Western Fiction', 'Gothic Fiction.Gothic Horror'],),
        (['Fantasy Fiction.High Fantasy', 'Political Fiction', 'Love Stories'],),
        (['Cowboy Fiction', 'Romance Fiction.Erotic Romance', 'Historical Fiction', 'Fantasy Fiction'],),
    ]
    EQ = [GOTHIC, ('Cowboy Fiction', 'Western Fiction'), ('Romance Fiction', 'Love Stories')]
    CO = [('Romance Fiction', 'Western Fiction', 'Western Romance'),
          ('Fantasy Fiction', 'Political Fiction', 'Political Fantasy'),
          ('Romance Fiction', 'Historical Fiction', 'Historical Romance')]

    def test_repeated_runs_stable(self):
        rules = Rules(self.EQ, self.CO)
        for (tags,) in self.CASES:
            first = compute_book_change(1, 't', tags, rules)
            self.assertTrue(first.converged)
            second = compute_book_change(1, 't', first.final, rules)
            self.assertFalse(second.changed, (tags, first.final, second))
            third = compute_book_change(1, 't', second.final, rules)
            self.assertEqual(second.final, third.final)

    def test_deterministic(self):
        rules = Rules(self.EQ, self.CO)
        a = [compute_book_change(1, 't', t, rules).final for (t,) in self.CASES]
        b = [compute_book_change(1, 't', t, Rules(self.EQ, self.CO)).final for (t,) in self.CASES]
        self.assertEqual(a, b)


class TestRulesValidation(unittest.TestCase):
    def test_blank_and_incomplete_rows(self):
        r = Rules([['', ''], ['A', ''], ['A', 'a']], [['', '', ''], ['P', 'Q', '']])
        self.assertEqual(r.equivalents, [])
        self.assertEqual(r.combinations, [])
        self.assertEqual(len(r.problems), 2)

    def test_whitespace_normalisation(self):
        r = Rules([[' Gothic Fiction . Gothic Horror ', 'Horror Fiction.Gothic Horror']])
        self.assertEqual(r.equivalents[0][0], 'Gothic Fiction.Gothic Horror')


# ---------------------------------------------------------------- write gate
class FakeAPI(object):
    def __init__(self, books, library_id='lib-1'):
        self.library_id = library_id
        self.books = {i: dict(title=t, tags=tuple(tags)) for i, t, tags in books}
        self.writes = []

    def all_book_ids(self):
        return set(self.books)

    def all_field_for(self, field, ids, default_value=None):
        return {i: self.books[i].get(field, default_value) for i in ids if i in self.books}

    def set_field(self, field, mapping, allow_case_change=True):
        self.writes.append((field, dict(mapping), allow_case_change))
        for i, v in mapping.items():
            self.books[i][field] = tuple(v)
        return set(mapping)


RULES = Rules([GOTHIC], [('Romance Fiction', 'Western Fiction', 'Western Romance')])
BOOKS = [(1, 'Gothic', ['Gothic Fiction.Gothic Horror']),
         (2, 'Cowboy love', ['Romance Fiction', 'Western Fiction']),
         (3, 'Plain', ['Science Fiction'])]


class TestWriteGate(unittest.TestCase):
    def test_scan_is_read_only(self):
        api = FakeAPI(BOOKS)
        plan = writer.scan(api, RULES)
        self.assertEqual(api.writes, [])
        self.assertEqual([c.book_id for c in plan.changes], [1, 2])
        self.assertEqual(plan.scanned, 3)

    def test_confirm_receives_per_book_plan(self):
        api = FakeAPI(BOOKS)
        seen = {}

        def confirm(plan):
            seen['plan'] = plan
            self.assertEqual(api.writes, [])  # nothing written while preview is open
            return False
        writer.run_flow(api, RULES, confirm)
        p = seen['plan']
        c2 = [c for c in p.changes if c.book_id == 2][0]
        self.assertEqual(c2.title, 'Cowboy love')
        self.assertEqual(set(c2.removed), {'Romance Fiction', 'Western Fiction'})

    def test_cancel_none_exception_write_nothing(self):
        for confirm in (lambda p: False, lambda p: None, lambda p: 1, lambda p: 1 / 0):
            api = FakeAPI(BOOKS)
            plan, res = writer.run_flow(api, RULES, confirm)
            self.assertIsNone(res)
            self.assertEqual(api.writes, [])

    def test_apply_writes_single_batch(self):
        api = FakeAPI(BOOKS)
        plan, res = writer.run_flow(api, RULES, lambda p: True)
        self.assertEqual(len(api.writes), 1)
        field, mapping, acc = api.writes[0]
        self.assertEqual(field, 'tags')
        self.assertFalse(acc)
        self.assertEqual(sorted(mapping), [1, 2])
        self.assertEqual(res.written, [1, 2])
        self.assertEqual(set(api.books[2]['tags']),
                         {'Romance Fiction.Western Romance', 'Western Fiction.Western Romance'})
        self.assertEqual(api.books[3]['tags'], ('Science Fiction',))
        # second run: nothing to do
        plan2, res2 = writer.run_flow(api, RULES, lambda p: self.fail('should not ask'))
        self.assertEqual(plan2.changes, [])
        self.assertIsNone(res2)

    def test_no_changes_does_not_prompt(self):
        api = FakeAPI([(1, 'x', ['Nothing'])])
        plan, res = writer.run_flow(api, RULES, lambda p: self.fail('prompted'))
        self.assertIsNone(res)

    def test_library_switch_aborts(self):
        api = FakeAPI(BOOKS)
        plan = writer.scan(api, RULES)
        other = FakeAPI(BOOKS, library_id='lib-2')
        res = writer.commit(other, plan)
        self.assertTrue(res.aborted_reason)
        self.assertEqual(other.writes, [])

    def test_stale_and_deleted_books_skipped(self):
        api = FakeAPI(BOOKS)
        plan = writer.scan(api, RULES)
        api.books[1]['tags'] = ('Edited meanwhile',)
        del api.books[2]
        res = writer.commit(api, plan)
        self.assertEqual(res.stale, [1])
        self.assertEqual(res.missing, [2])
        self.assertEqual(res.written, [])
        self.assertEqual(api.writes, [])

    def test_partial_stale_writes_rest(self):
        api = FakeAPI(BOOKS)
        plan = writer.scan(api, RULES)
        api.books[1]['tags'] = ('Edited meanwhile',)
        res = writer.commit(api, plan)
        self.assertEqual(res.written, [2])
        self.assertEqual(api.books[1]['tags'], ('Edited meanwhile',))


if __name__ == '__main__':
    unittest.main()
