"""Regression checks for common clocks, angular wrap and early terminal states."""
from fractions import Fraction
import math
import unittest

from run import WHEELBASE, score
from sampling import sample_30hz


def pose(x=0, angle=0, event=None):
    return dict(x=x, y=0, angle=angle, event=event)


class ClockTest(unittest.TestCase):
    def test_different_native_rates_same_motion(self):
        for rate in (50, 80, Fraction(4194304, 140448)):
            native = ((Fraction(i) / rate, pose(float(Fraction(i) / rate))) for i in range(90))
            rows = sample_30hz(native, 30)
            for i, row in enumerate(rows, 1):
                self.assertAlmostEqual(row['x'], i / 30)

    def test_wrap_and_terminal_boundary(self):
        native = [(0, pose(angle=math.radians(179))),
                  (Fraction(2, 30), pose(angle=math.radians(-179), event='dead'))]
        first, last, frozen = sample_30hz(native, 3)
        self.assertAlmostEqual(abs(first['angle']), math.pi)
        self.assertIsNone(first['event'])
        self.assertEqual(last['event'], 'dead')
        self.assertEqual(last, frozen)


class ScoringTest(unittest.TestCase):
    def test_cases_have_equal_weight_and_riding_is_not_a_timed_event(self):
        pc = {'short': [pose()], 'long': [pose()] * 9}
        port = {'short': [pose(WHEELBASE)], 'long': pc['long']}
        result = score(pc, port)
        self.assertEqual(result['mean_position_percent_wheelbase'], 50)
        self.assertEqual(result['same_outcome'], 2)
        self.assertEqual(result['same_terminal_within_one_tick'], 0)

    def test_early_terminal_pose_counts_until_pc_terminal(self):
        pc = {'run': [pose(), pose(WHEELBASE), pose(2 * WHEELBASE, event='dead')]}
        port = {'run': [pose(event='dead')] * 3}
        result = score(pc, port)
        self.assertEqual(result['mean_position_percent_wheelbase'], 100)
        self.assertEqual(result['same_outcome'], 1)
        self.assertEqual(result['same_terminal_within_one_tick'], 0)


if __name__ == '__main__':
    unittest.main()
