"""Contrast is a build-time invariant, not a review opinion.

The ui-ux-pro-max guidance that applies here: normal text needs >= 4.5:1, and the
dashboard must clear that in both themes on the surface each role actually sits on.
"""
from pathlib import Path
import re
import unittest

from boardproof.brand import PALETTE

DASHBOARD = Path(__file__).resolve().parents[1] / 'boardproof' / 'dashboard.py'


def _luminance(hex_colour: str) -> float:
    value = hex_colour.lstrip('#')
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]

    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class TestTextContrast(unittest.TestCase):
    def test_every_text_role_clears_4_5_in_both_themes(self):
        for theme, colours in PALETTE.items():
            for surface in ('page', 'card'):
                for role in ('ink', 'ink2', 'ink3', 'ink4'):
                    with self.subTest(theme=theme, surface=surface, role=role):
                        value = ratio(colours[role], colours[surface])
                        self.assertGreaterEqual(
                            round(value, 2), 4.5,
                            f"{theme}/{role} on {surface} is {value:.2f}:1")

    def test_hierarchy_is_preserved_after_fixing_contrast(self):
        for theme, colours in PALETTE.items():
            levels = [ratio(colours[role], colours['card'])
                      for role in ('ink', 'ink2', 'ink3', 'ink4')]
            self.assertEqual(levels, sorted(levels, reverse=True),
                             f"{theme}: ink > ink2 > ink3 > ink4 must hold")

    def test_css_uses_the_audited_values(self):
        css = DASHBOARD.read_text()
        light = PALETTE['light']
        dark = PALETTE['dark']
        for role in ('ink', 'ink2', 'ink3', 'ink4'):
            self.assertIn(light[role], css, f"light {role} drifted from the palette")
            self.assertIn(dark[role], css, f"dark {role} drifted from the palette")

    def test_verdict_colours_stay_readable(self):
        light = PALETTE['light']
        for signal in ('#0b7a5f', '#c0282c', '#8a5a00'):
            self.assertGreaterEqual(round(ratio(signal, light['card']), 2), 4.5)


class TestFocusAffordances(unittest.TestCase):
    def test_sticky_bar_does_not_hide_focus(self):
        css = DASHBOARD.read_text()
        self.assertIn('scroll-padding-top', css)
        self.assertIn('.skip', css)

    def test_run_output_is_announced_and_focusable(self):
        page = DASHBOARD.read_text()
        self.assertIn('id="log" tabindex="-1"', page)
        self.assertIn("aria-live=\\\"polite\\\"", page)
        self.assertIn("aria-busy", page)


if __name__ == '__main__':
    unittest.main()
