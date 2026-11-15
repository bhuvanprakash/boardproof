"""Backend guarantees: speed structure, fault coverage, revision gating."""
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from boardproof.bench import run as bench_run
from boardproof.checks import run_checks
from boardproof.cli import execute, main
from boardproof.diff import compare
from boardproof.firmware import parse_defines
from boardproof.index import index_for, ohms
from boardproof.netlist import load_enet
from boardproof.packs import load_pack, resolve_config
from boardproof.redteam import build_faults, run_redteam

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'examples' / 'demo'
CLEAN = DEMO / 'boardproof.pack.clean.json'
BROKEN = DEMO / 'boardproof.pack.json'


class TestIndex(unittest.TestCase):
    def test_ohms_parsing(self):
        self.assertEqual(4700.0, ohms('4.7k'))
        self.assertEqual(4700.0, ohms('4700R'))
        self.assertEqual(4700.0, ohms('4k7'))
        self.assertEqual(4700.0, ohms('4.7 kΩ'))
        self.assertEqual(1000000.0, ohms('1M'))
        self.assertIsNone(ohms(''))
        self.assertIsNone(ohms('see BOM'))

    def test_resistor_lookup_is_correct_and_indexed(self):
        design = load_enet(DEMO / 'clean.enet')
        index = index_for(design)
        hits = index.resistors_between('I2C_SDA', '3V3')
        self.assertEqual(1, len(hits))
        self.assertEqual(4700.0, hits[0][1])
        self.assertEqual([], index.resistors_between('I2C_SDA', 'GND'))
        # Second call must reuse the cached table, not rescan.
        self.assertIs(index_for(design), index)
        self.assertIs(index.resistors_between('I2C_SDA', '3V3'), hits)

    def test_large_board_stays_linear(self):
        """A 1000-component board must not turn the check into a quadratic scan."""
        start = time.perf_counter()
        result = bench_run(1000, 400, 1)
        elapsed = time.perf_counter() - start
        self.assertLess(result['checks_ms'], 250, f"checks took {result['checks_ms']} ms")
        self.assertLess(elapsed, 5.0)
        self.assertGreater(result['rules_per_second'], 1000)


class TestCaching(unittest.TestCase):
    def test_pack_cache_is_isolated(self):
        first = load_pack(DEMO / 'packs' / 'demo-mcu.json', require_vetted=True)
        second = load_pack(DEMO / 'packs' / 'demo-mcu.json', require_vetted=True)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        first['rules'][0]['max_v'] = 99.0
        third = load_pack(DEMO / 'packs' / 'demo-mcu.json', require_vetted=True)
        self.assertEqual(3.6, third['rules'][0]['max_v'])

    def test_firmware_cache_invalidates_on_change(self):
        with TemporaryDirectory() as td:
            path = Path(td) / 'pins.h'
            path.write_text('#define LED_PIN 4\n', encoding='utf-8')
            self.assertEqual(4, parse_defines(path)['LED_PIN'])
            time.sleep(0.01)
            path.write_text('#define LED_PIN 7\n', encoding='utf-8')
            self.assertEqual(7, parse_defines(path)['LED_PIN'])


class TestRedTeam(unittest.TestCase):
    def _resolved(self, path):
        spec = json.loads(path.read_text())
        return resolve_config(spec, path), path

    def test_clean_rules_catch_every_targeted_fault(self):
        spec, path = self._resolved(CLEAN)
        result = run_redteam(load_enet(DEMO / 'clean.enet'), spec, path)
        score = result['score']
        self.assertGreaterEqual(score['targeted'], 6)
        self.assertEqual(score['targeted'], score['caught'])
        self.assertEqual(1.0, score['ratio'])
        self.assertGreaterEqual(score['gaps'], 1)          # a real blind spot is named
        self.assertEqual(1, score['unverifiable'])         # footprint mapping is not claimable
        self.assertTrue(result['suggestions'])
        kinds = {f['kind'] for f in result['faults']}
        for expected in {'supply_swap', 'disconnect', 'remove_resistor',
                         'value_drift', 'firmware_shift', 'not_representable'}:
            self.assertIn(expected, kinds)

    def test_each_fault_is_a_real_mutation(self):
        spec, _ = self._resolved(CLEAN)
        design = load_enet(DEMO / 'clean.enet')
        def snapshot(board):
            return {c.ref: (c.value, {p.number: (p.net, p.name) for p in c.pins.values()})
                    for c in board.components.values()}

        before = snapshot(design)
        for fault in build_faults(design, spec):
            if not fault.representable:
                continue
            mutated, overrides = fault.apply()
            if overrides:
                continue                                   # firmware faults do not touch the board
            self.assertNotEqual(before, snapshot(mutated), f"{fault.id} did not mutate the design")

    def test_weak_rule_is_reported_as_missed(self):
        """A rule with bounds that cannot be violated must fail its mutation test."""
        spec, path = self._resolved(CLEAN)
        spec['rules'] = [{
            'id': 'pointless-supply-limit', 'type': 'max_voltage',
            'component': 'U1', 'pin': '1', 'min_v': 0.0, 'max_v': 99.0,
        }]
        result = run_redteam(load_enet(DEMO / 'clean.enet'), spec, path)
        statuses = [f['status'] for f in result['faults']]
        self.assertIn('missed', statuses)
        self.assertLess(result['score']['ratio'], 1.0)
        self.assertTrue(any('tighten it' in s for s in result['suggestions']))

    def test_min_score_gate_blocks_ci(self):
        self.assertEqual(0, main(['redteam', '--config', str(CLEAN), '--min-score', '1.0']))
        self.assertEqual(1, main(['redteam', '--config', str(CLEAN), '--min-score', '1.01']))


class TestRevisionDiff(unittest.TestCase):
    def _reports(self, td):
        clean = Path(td) / 'clean.json'
        broken = Path(td) / 'broken.json'
        execute(CLEAN, clean, None, False)
        execute(BROKEN, broken, None, False)
        return json.loads(clean.read_text()), json.loads(broken.read_text())

    def test_regression_is_isolated_from_backlog(self):
        with TemporaryDirectory() as td:
            clean, broken = self._reports(td)
            result = compare(clean, broken)
            self.assertTrue(result['regressed'])
            self.assertEqual(0, result['summary']['fixed'])
            self.assertEqual(5, result['summary']['introduced'])

            reverse = compare(broken, broken)
            self.assertFalse(reverse['regressed'])        # same backlog is not a new regression
            self.assertEqual(5, reverse['summary']['persisting'])

    def test_diff_cli_exit_codes(self):
        with TemporaryDirectory() as td:
            clean, broken = self._reports(td)
            base, head = Path(td) / 'clean.json', Path(td) / 'broken.json'
            self.assertEqual(1, main(['diff', '--base', str(base), '--head', str(head)]))
            self.assertEqual(0, main(['diff', '--base', str(base), '--head', str(head), '--no-fail']))
            self.assertEqual(0, main(['diff', '--base', str(head), '--head', str(base)]))
            self.assertTrue(clean and head)


class TestBench(unittest.TestCase):
    def test_bench_reports_measurable_throughput(self):
        result = bench_run(600, 240, 1)
        self.assertEqual(600, result['components'])
        self.assertGreater(result['parse_ms'], 0)
        self.assertGreater(result['checks_ms'], 0)
        self.assertGreater(result['rules_per_second'], 0)
        self.assertEqual(0, main(['bench', '--components', '400', '--rules', '120', '--repeat', '1']))

    def test_performance_budget_gate(self):
        self.assertEqual(0, main(['bench', '--components', '400', '--rules', '120',
                                   '--repeat', '1', '--max-checks-ms', '400']))
        self.assertEqual(1, main(['bench', '--components', '400', '--rules', '120',
                                  '--repeat', '1', '--max-checks-ms', '0.0001']))


class TestScopePassport(unittest.TestCase):
    def test_report_declares_what_it_did_not_verify(self):
        with TemporaryDirectory() as td:
            out = Path(td) / 'r.json'
            html_out = Path(td) / 'r.html'
            execute(CLEAN, out, html_out, False, True, 'offline')
            data = json.loads(out.read_text())
            self.assertIn('unverified_scope', data)
            self.assertTrue(any('PCB trace' in item for item in data['unverified_scope']))
            self.assertGreater(data['verified_by_type']['max_voltage'], 0)
            page = html_out.read_text()
            self.assertIn('Verification scope', page)
            self.assertIn('not checked', page)

    def test_config_can_override_the_scope_list(self):
        with TemporaryDirectory() as td:
            spec = json.loads(CLEAN.read_text())
            spec['unverified_scope'] = ['Customer-specific thermal review']
            path = DEMO / '_tmp_scope.json'
            path.write_text(json.dumps(spec), encoding='utf-8')
            out = Path(td) / 'r.json'
            try:
                execute(path, out, None, False)
            finally:
                path.unlink()
            self.assertEqual(['Customer-specific thermal review'],
                             json.loads(out.read_text())['unverified_scope'])


if __name__ == '__main__':
    unittest.main()
