"""The studio: file discovery, the action API, and the dashboard panel."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from boardproof.dashboard import collect, render
from boardproof.studio import ACTION_HELP, discover_configs, newest_board, run_action, state

ROOT = Path(__file__).resolve().parents[1]
CONFIG = 'examples/tmp102/boardproof.json'


class TestDiscovery(unittest.TestCase):
    def test_finds_configs_and_ignores_artifacts(self):
        configs = discover_configs(ROOT)
        paths = {c['path'] for c in configs}
        self.assertIn(CONFIG, paths)
        self.assertFalse(any(p.startswith('artifacts/') for p in paths))

    def test_state_reports_actions_and_board(self):
        with TemporaryDirectory() as td:
            payload = state(ROOT, Path(td))
            self.assertEqual('BoardProof', payload['tool'])
            self.assertIn('prove', payload['actions'])
            self.assertIsNone(payload['board'] or None)


class TestActions(unittest.TestCase):
    def test_unknown_action_is_rejected(self):
        with TemporaryDirectory() as td:
            result = run_action(ROOT, Path(td), 'rm -rf', CONFIG)
            self.assertFalse(result['ok'])
            self.assertIn('unknown action', result['log'][0])

    def test_config_must_stay_inside_the_workspace(self):
        with TemporaryDirectory() as td:
            result = run_action(ROOT, Path(td), 'check', '../../../etc/passwd')
            self.assertFalse(result['ok'])
            self.assertIn('outside the workspace', result['log'][0])

    def test_missing_config_is_reported(self):
        with TemporaryDirectory() as td:
            result = run_action(ROOT, Path(td), 'check', 'examples/nope.json')
            self.assertFalse(result['ok'])
            self.assertIn('not found', result['log'][0])

    def test_check_produces_artifacts(self):
        with TemporaryDirectory() as td:
            out = Path(td)
            result = run_action(ROOT, out, 'check', CONFIG)
            self.assertTrue(result['ok'], result['log'])
            self.assertTrue((out / 'boardproof.json').is_file())
            self.assertTrue((out / 'index.html').is_file())

    def test_prove_runs_the_whole_pipeline(self):
        with TemporaryDirectory() as td:
            out = Path(td)
            result = run_action(ROOT, out, 'prove', CONFIG)
            self.assertTrue(result['ok'], result['log'])
            for name in ('report.html', 'pcb-check.json', 'redteam.json', 'passport.html'):
                self.assertTrue((out / name).is_file(), name)
            self.assertEqual(result['code'], 0)

    def test_design_then_verify_board(self):
        with TemporaryDirectory() as td:
            out = Path(td)
            self.assertTrue(run_action(ROOT, out, 'design', CONFIG)['ok'])
            board = newest_board(out)
            self.assertIsNotNone(board)
            result = run_action(ROOT, out, 'pcb', CONFIG)
            self.assertTrue(result['ok'], result['log'])
            self.assertTrue((out / 'pcb-check.json').is_file())

    def test_redteam_and_passport(self):
        with TemporaryDirectory() as td:
            out = Path(td)
            self.assertTrue(run_action(ROOT, out, 'check', CONFIG)['ok'])
            red = run_action(ROOT, out, 'redteam', CONFIG)
            self.assertTrue(red['ok'], red['log'])
            self.assertIn('targeted faults caught', red['log'][0])
            doc = run_action(ROOT, out, 'passport', CONFIG)
            self.assertTrue(doc['ok'], doc['log'])
            data = json.loads((out / 'passport.json').read_text())
            self.assertIn('passport_hash', data)


class TestDashboardPanel(unittest.TestCase):
    def test_interactive_panel_is_optional(self):
        static = render({'reports': [], 'passport': None, 'redteam': None, 'redteams': [],
                         'diffs': [], 'designs': [], 'pcb_checks': [], 'html': []})
        self.assertNotIn('data-action', static)
        self.assertNotIn('id="log"', static)

    def test_board_preview_embeds_the_generated_svg(self):
        empty = {'reports': [], 'passport': None, 'redteam': None, 'redteams': [], 'diffs': [],
                 'designs': [], 'pcb_checks': [], 'html': []}
        self.assertIn('No generated board yet', render(empty))
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'
        with_board = dict(empty, boards=[{
            'file': 'board.svg', 'svg': svg, 'html': None,
            'check': {'status': 'passed', 'counts': {'error': 0},
                      'census': {'footprints': 5, 'pads': 14, 'width_mm': 44, 'height_mm': 52,
                                 'segments': 0, 'vias': 0},
                      'nets': {'total': 5, 'fully_connected': 0},
                      'verified': ['land pattern vs datasheet SOT-5X3 (DRL) (p.30)',
                                   'track current capacity (IPC-2221, 1 oz copper)']}}])
        page = render(with_board)
        self.assertIn('<svg', page)
        self.assertIn('Board preview', page)
        self.assertIn('Verified candidate', page)
        self.assertIn('land pattern vs datasheet', page)
        self.assertIn('routing not attempted', page)
        self.assertIn('Generated layout', page)
        self.assertIn('land pattern vs datasheet SOT-5X3', page)
        self.assertIn('44 × 52 mm', page)

    def test_panel_lists_configs_and_actions(self):
        configs = discover_configs(ROOT)
        page = render({'reports': [], 'passport': None, 'redteam': None, 'redteams': [],
                       'diffs': [], 'designs': [], 'pcb_checks': [], 'html': []},
                      studio=configs)
        self.assertIn('data-action="prove"', page)
        self.assertIn('id="cfg"', page)
        self.assertIn('id="log"', page)
        self.assertIn(CONFIG, page)
        self.assertIn('/api/run', page)
        self.assertIn('Drop a layout, schematic, netlist or design photo', page)
        self.assertIn('Made by Team SuperX', page)
        self.assertIn('id="brief"', page)

    def test_collect_keeps_jeden_as_demo_preview(self):
        with TemporaryDirectory() as td:
            directory = Path(td)
            svg = '<svg xmlns="http://www.w3.org/2000/svg"></svg>'
            (directory / 'Jeden-Board.svg').write_text(svg, encoding='utf-8')
            (directory / 'blink.svg').write_text(svg, encoding='utf-8')
            found = collect(directory)
            self.assertEqual('Jeden-Board.svg', found['boards'][0]['file'])


if __name__ == '__main__':
    unittest.main()


class TestBrand(unittest.TestCase):
    def test_mark_is_inline_and_network_free(self):
        from boardproof.brand import mark

        svg = mark(24)
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn('viewBox="0 0 24 24"', svg)
        self.assertNotIn("http", svg.replace("http://www.w3.org", ""))

    def test_icon_set_covers_every_action(self):
        from boardproof.brand import icon

        for name in ("prove", "check", "design", "pcb", "redteam", "passport", "refresh", "upload"):
            self.assertIn("<svg", icon(name), name)
        self.assertEqual("", icon("nope"))

    def test_three_artifacts_share_the_mark(self):
        from boardproof.brand import mark

        page = render({"reports": [], "passport": None, "redteam": None, "redteams": [],
                       "diffs": [], "designs": [], "pcb_checks": [], "html": []},
                      studio=discover_configs(ROOT))
        self.assertIn("bp-mark", page)
        self.assertIn("rel=\"icon\"", page)
        self.assertIn("bp-mark", mark(18))


class TestRobustness(unittest.TestCase):
    def test_rate_limit_is_per_client_and_recovers(self):
        from boardproof.serve import _HITS, allow_request

        _HITS.clear()
        for _ in range(3):
            self.assertTrue(allow_request("1.2.3.4", limit=3, window=60)[0])
        blocked, wait = allow_request("1.2.3.4", limit=3, window=60)
        self.assertFalse(blocked)
        self.assertGreater(wait, 0)
        self.assertTrue(allow_request("5.6.7.8", limit=3, window=60)[0],
                        "a different client must not inherit the limit")
        _HITS.clear()

    def test_footprint_provenance_is_recorded(self):
        from boardproof.design import build_board
        from boardproof.netlist import load_enet

        design = load_enet(ROOT / 'examples' / 'tmp102' / 'rev-c-fixed.enet')
        _board, report = build_board(design, None, None)
        self.assertEqual([], report['footprints']['guessed'])
        self.assertTrue(report['footprints']['from_export'])

    def test_strict_mode_refuses_unverified_geometry(self):
        from boardproof.footprints import FootprintError, resolve

        with self.assertRaises(FootprintError) as ctx:
            resolve('C9', 'UNKNOWN-PART', '', ['1', '2'], allow_generic=False)
        self.assertIn('Refusing to guess', str(ctx.exception))
        pattern, source = resolve('C9', 'UNKNOWN-PART', '', ['1', '2'], allow_generic=True)
        self.assertEqual('designator', source)

    def test_named_footprint_beats_the_part_number(self):
        from boardproof.footprints import resolve

        pattern, source = resolve('U1', 'TMP102AIDRLR', 'SOT563-6', ['1', '2', '3', '4', '5', '6'])
        self.assertEqual('export', source)
        self.assertEqual('SOT563-6', pattern.name)
