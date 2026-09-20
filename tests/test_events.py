import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('events', Path(__file__).parents[1] / 'scripts/verify-events.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def event(number, kind, **values):
    return dict(schema_version=1, match_id='test-match', event_id=str(number),
                type=kind, practice_demo=True, real_money=False, **values)


class EventVerification(unittest.TestCase):
    def setUp(self):
        self.stream = [event(1, 'match_start'), event(2, 'kill', eligible_enemy_frag=True,
            suicide=False, world_death=False, teamkill=False, practice_points_awarded=3),
            event(3, 'match_end', scoreboard=[
                dict(participant_id='p1', vanilla_score=3, rank=1),
                dict(participant_id='p2', vanilla_score=3, rank=1),
                dict(participant_id='p3', vanilla_score=1, rank=3)])]

    def test_complete_match_with_ties(self):
        self.assertTrue(module.verify(self.stream)['complete'])

    def test_duplicate_kill(self):
        with self.assertRaisesRegex(ValueError, 'event ID'):
            module.verify(self.stream[:2] + [copy.deepcopy(self.stream[1])] + self.stream[2:])

    def test_kill_after_final_ranking(self):
        with self.assertRaisesRegex(ValueError, 'after match_end'):
            module.verify(self.stream + [event(4, 'kill')])

    def test_live_money_is_rejected(self):
        self.stream[1]['real_money'] = True
        with self.assertRaisesRegex(ValueError, 'boundary'):
            module.verify(self.stream)

    def test_ineligible_kill_points(self):
        self.stream[1]['eligible_enemy_frag'] = False
        with self.assertRaisesRegex(ValueError, 'ineligible'):
            module.verify(self.stream)

    def test_incomplete_requires_explicit_option(self):
        with self.assertRaisesRegex(ValueError, 'did not finish'):
            module.verify(self.stream[:2])
        self.assertFalse(module.verify(self.stream[:2], require_complete=False)['complete'])

    def test_wrong_tied_rank(self):
        self.stream[2]['scoreboard'][1]['rank'] = 2
        with self.assertRaisesRegex(ValueError, 'rank'):
            module.verify(self.stream)

    def test_mixed_matches(self):
        self.stream[1]['match_id'] = 'other-match'
        with self.assertRaisesRegex(ValueError, 'mixed'):
            module.verify(self.stream)


if __name__ == '__main__':
    unittest.main()
