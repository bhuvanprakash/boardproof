"""Tests for the propose -> vet -> enforce trust chain."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from boardproof.checks import run_checks
from boardproof.cli import execute, main
from boardproof.explain import attach, explain_findings
from boardproof.infer import proposal_from_pins, vet
from boardproof.netlist import load_enet
from boardproof.packs import PackError, load_pack, resolve_config, validate_pack
from boardproof.provenance import Citation
from boardproof.providers import OfflineProvider, redact_explanations

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'examples' / 'demo'
PACKS = DEMO / 'packs'
FIXTURE = DEMO / 'fixtures' / 'demo-mcu.facts.json'
PDF = DEMO / 'demo-mcu-SIMULATED.pdf'


def _proposal():
    provider = OfflineProvider(FIXTURE)
    facts = provider.extract(PDF, 'U1')
    design = load_enet(DEMO / 'broken.enet')
    return proposal_from_pins(facts, design, 'U1', 'test-pack', PDF, provider.name)


class TestRulePacks(unittest.TestCase):
    def test_citation_requires_page_and_quote(self):
        with self.assertRaises(ValueError):
            Citation.from_dict({'page': '6'})
        with self.assertRaises(ValueError):
            Citation.from_dict({'quote': 'no page'})
        self.assertEqual('p.6', Citation.from_dict({'page': '6', 'quote': 'VDD 2.7-3.6 V'}).locator())

    def test_numeric_rule_without_citation_is_rejected(self):
        pack = _proposal()
        del pack['rules'][0]['citation']
        with self.assertRaises(PackError) as ctx:
            validate_pack(pack, 'unit')
        self.assertIn('without a usable citation', str(ctx.exception))

    def test_proposed_pack_cannot_be_enforced(self):
        with self.assertRaises(PackError) as ctx:
            load_pack(PACKS / 'demo-mcu.propose.json', require_vetted=True)
        self.assertIn('not \'vetted\'', str(ctx.exception))

    def test_vetted_pack_enforces_and_carries_provenance(self):
        config_path = DEMO / 'boardproof.pack.json'
        spec = json.loads(config_path.read_text())
        resolved = resolve_config(spec, config_path)
        design = load_enet(DEMO / 'broken.enet')
        design.net_voltages = resolved['net_voltages']
        findings = run_checks(design, resolved, config_path)
        packed = [f for f in findings if (f.evidence.get('provenance') or {}).get('pack_id')]
        self.assertTrue(packed)
        prov = packed[0].evidence['provenance']
        self.assertEqual('vetted', prov['status'])
        self.assertIn('demo-mcu', prov['pack_id'])
        self.assertTrue(prov['citation']['quote'])


class TestInference(unittest.TestCase):
    def test_proposal_is_uncited_never_unbound(self):
        pack = _proposal()
        self.assertEqual('proposed', pack['pack']['status'])
        self.assertIsNone(pack['pack']['reviewed_by'])
        for rule in pack['rules']:
            self.assertIn('citation', rule)
        # U1 in this netlist has 4 pins; DATASHEET pins 5/6 must be skipped, not emitted unbound.
        self.assertEqual(2, len(pack['rules']))
        self.assertTrue(any('package mismatch' in n for n in pack['pack']['review_notes']))

    def test_extracted_absolute_max_is_not_silently_converted(self):
        notes = ' '.join(_proposal()['pack']['review_notes'])
        self.assertIn('absolute maximum', notes.lower())

    def test_vet_records_reviewer_and_flips_status(self):
        with TemporaryDirectory() as td:
            draft = Path(td) / 'draft.json'
            draft.write_text(json.dumps(_proposal()), encoding='utf-8')
            with self.assertRaises(PackError):
                vet(draft, '   ')
            pack = vet(draft, 'Reviewer Name', Path(td) / 'final.json')
            self.assertEqual('vetted', pack['pack']['status'])
            self.assertEqual('Reviewer Name', pack['pack']['reviewed_by'])
            self.assertTrue((Path(td) / 'final.json').is_file())
            self.assertIn('vetted', load_pack(Path(td) / 'final.json', require_vetted=True)['pack']['status'])

    def test_vet_refuses_uncited_rule(self):
        pack = _proposal()
        del pack['rules'][1]['citation']
        with TemporaryDirectory() as td:
            draft = Path(td) / 'draft.json'
            draft.write_text(json.dumps(pack), encoding='utf-8')
            with self.assertRaises(PackError) as ctx:
                vet(draft, 'Someone')
            self.assertIn('no citation', str(ctx.exception))

    def test_full_cli_chain_infer_vet_check(self):
        with TemporaryDirectory() as td:
            out = Path(td) / 'u1.propose.json'
            self.assertEqual(0, main(['infer', '--pdf', str(PDF), '--component', 'U1',
                                      '--netlist', str(DEMO / 'broken.enet'), '--out', str(out),
                                      '--engine', 'offline', '--fixture', str(FIXTURE),
                                      '--pack-id', 'demo-mcu']))
            self.assertEqual(0, main(['vet', '--proposal', str(out), '--reviewer', 'CI Tester']))
            config = json.loads((DEMO / 'boardproof.pack.json').read_text())
            config['packs'] = [str(Path(td) / 'u1.propose.json')]
            config_path = DEMO / '_tmp_chain.json'
            config_path.write_text(json.dumps(config), encoding='utf-8')
            try:
                self.assertEqual(1, execute(config_path, None, None, False))
            finally:
                config_path.unlink()


class TestExplanation(unittest.TestCase):
    def _findings(self):
        config_path = DEMO / 'boardproof.pack.json'
        spec = resolve_config(json.loads(config_path.read_text()), config_path)
        design = load_enet(DEMO / 'broken.enet')
        design.net_voltages = spec['net_voltages']
        return run_checks(design, spec, config_path), design

    def test_offline_explanation_is_grounded_in_evidence(self):
        findings, design = self._findings()
        bundle = explain_findings(findings, design, OfflineProvider())
        self.assertEqual(len(findings), len(bundle['explanations']))
        voltage = next(e for e in bundle['explanations'] if '5 V' in e['plain_english'])
        self.assertEqual('6', voltage['cited_page'])
        self.assertIn('3.3 V rail', voltage['suggested_fix'])

    def test_model_cannot_cite_pages_it_was_not_given(self):
        kept, rejected = redact_explanations(
            {'explanations': [
                {'rule_index': 1, 'plain_english': 'ok', 'suggested_fix': 'x', 'cited_page': '6'},
                {'rule_index': 1, 'plain_english': 'bad page', 'suggested_fix': 'x', 'cited_page': '99'},
                {'rule_index': 42, 'plain_english': 'invented', 'suggested_fix': 'x'},
            ]}, {1: {'6'}}, {1})
        self.assertEqual(2, len(kept))
        self.assertEqual([], [e for e in kept if e.get('cited_page') == '99'])
        self.assertTrue(any('99' in r for r in rejected))
        self.assertTrue(any('42' in r for r in rejected))

    def test_explanation_never_changes_the_verdict(self):
        findings, design = self._findings()
        before = [(f.code, f.severity) for f in findings]
        bundle = explain_findings(findings, design, OfflineProvider())
        attach(findings, bundle['explanations'])
        self.assertEqual(before, [(f.code, f.severity) for f in findings])

    def test_report_renders_citation_and_trust_boundary(self):
        with TemporaryDirectory() as td:
            html_out = Path(td) / 'r.html'
            json_out = Path(td) / 'r.json'
            self.assertEqual(1, execute(DEMO / 'boardproof.pack.json', json_out, html_out, False,
                                        True, 'offline'))
            page = html_out.read_text()
            self.assertIn('Recommended operating conditions', page)
            self.assertIn('cannot change the verdict', page)
            self.assertIn('vetted by', page)
            data = json.loads(json_out.read_text())
            self.assertIn('offline', data['explain_engine'])
            self.assertEqual('vetted', data['packs'][0]['status'])


if __name__ == '__main__':
    unittest.main()
