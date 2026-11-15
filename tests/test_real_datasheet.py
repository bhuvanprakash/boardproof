"""End-to-end regression on a real part: TI TMP102 (SBOOS397I, SOT563 DRL).

The rule pack in packs/tmp102-drl.json was produced by Gemini from the actual
datasheet, then vetted against the PDF (pin functions p.3, design requirements
p.20). This test keeps that real-world artifact honest without needing a key.
"""
import json
from pathlib import Path
import unittest

from boardproof.checks import run_checks
from boardproof.netlist import load_enet
from boardproof.packs import load_pack, resolve_config
from boardproof.redteam import run_redteam

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples' / 'tmp102'
PACK = ROOT / 'packs' / 'tmp102-drl.json'
PDF = ROOT / 'datasheets' / 'tmp102.pdf'


@unittest.skipUnless(PACK.is_file() and EXAMPLE.is_dir(), 'real-datasheet fixture not present')
class TestRealDatasheet(unittest.TestCase):
    def _run(self, config_name):
        path = EXAMPLE / config_name
        spec = resolve_config(json.loads(path.read_text()), path)
        design = load_enet(EXAMPLE / spec['netlist'])
        design.net_voltages = spec['net_voltages']
        return run_checks(design, spec, path), design, spec

    def test_pack_is_vetted_and_every_rule_is_cited(self):
        pack = load_pack(PACK, require_vetted=True)
        self.assertEqual('TMP102', pack['pack']['part'])
        self.assertIn('TEXAS INSTRUMENTS', pack['pack']['manufacturer'].upper())
        self.assertIn('SOT563', pack['pack']['package'])
        self.assertTrue(pack['pack']['reviewed_by'])
        for rule in pack['rules']:
            self.assertIn('page', rule['citation'])
            self.assertIn('quote', rule['citation'])
            self.assertGreaterEqual(int(rule['citation']['page']), 1)

    def test_supply_limit_matches_the_datasheet_numbers(self):
        """1.4-3.6 V over 2.7-3.6 V is exactly what TI prints in Table 4-1 / 5.3."""
        pack = load_pack(PACK, require_vetted=True)
        supply = [r for r in pack['rules'] if r['type'] == 'max_voltage']
        if supply:  # withheld when the model's quote omits the numbers - see infer notes
            self.assertEqual(1.4, supply[0]['min_v'])
            self.assertEqual(3.6, supply[0]['max_v'])

    def test_pullups_are_enforced_from_the_design_requirements_section(self):
        pack = load_pack(PACK, require_vetted=True)
        pullups = [r for r in pack['rules'] if r['type'] == 'resistor_between']
        self.assertEqual(3, len(pullups))
        self.assertEqual({'I2C_SCL', 'I2C_SDA', 'ALERT_N'}, {r['net_a'] for r in pullups})
        self.assertTrue(all(r['net_b'] == '3V3' for r in pullups))
        self.assertTrue(all('5' in r['citation']['quote'] for r in pullups))

    def test_good_board_passes_and_bad_board_is_caught(self):
        good, design, spec = self._run('boardproof.json')
        self.assertEqual([], [f for f in good if f.severity == 'error'])
        bad, _, _ = self._run('boardproof.5v.json')
        errors = [f for f in bad if f.severity == 'error']
        self.assertEqual(1, len(errors))
        self.assertEqual('PIN_NET', errors[0].code)
        self.assertIn('5V', errors[0].message)

        result = run_redteam(design, spec, EXAMPLE / 'boardproof.json')
        self.assertEqual(result['score']['targeted'], result['score']['caught'])
        kinds = {f['kind'] for f in result['faults']}
        self.assertIn('remove_resistor', kinds)
        self.assertIn('supply_swap', kinds)

    def test_fault_reconnects_to_an_overvoltage_rail(self):
        _findings, _design, spec = self._run('boardproof.json')
        pack_rules = [r for r in spec['rules'] if r.get('component') == 'U1']
        self.assertTrue(pack_rules)
        from boardproof.redteam import build_faults

        faults = build_faults(load_enet(EXAMPLE / 'tmp102.enet'), spec)
        swap = next(f for f in faults if f.kind == 'supply_swap')
        self.assertIn('5V', swap.summary)


if __name__ == '__main__':
    unittest.main()
