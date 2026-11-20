"""Datasheet-driven layout verification: fetch -> package spec -> land pattern check."""
import json
import socket
from pathlib import Path
from tempfile import TemporaryDirectory
import urllib.request
import unittest
from unittest.mock import patch

import boardproof.datasheets as datasheets
from boardproof.design import build_board, write_board
from boardproof.netlist import load_enet
from boardproof.package import (PackageError, current_findings, empty_spec, ipc2221_current,
                                land_pattern_findings, load_spec, validate_spec, vet_spec)
from boardproof.pcbcheck import check_board

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'examples' / 'tmp102'
PACKAGE = ROOT / 'packs' / 'packages' / 'tmp102.json'


def _spec(pitch=0.5, part='TMP102AIDRLR'):
    spec = empty_spec('spec', part, 'SOT-5X3 (DRL)')
    spec['package']['status'] = 'vetted'
    spec['package']['reviewed_by'] = 'unit test'
    spec['geometry'] = {'pin_count': 6, 'pitch_mm': pitch, 'body_w_mm': 1.6, 'body_h_mm': 1.2,
                        'pad_w_mm': 0.3, 'pad_h_mm': 0.22, 'thermal_pad': False,
                        'citation': {'page': '30', 'quote': '4X 0.5'}}
    return spec


class TestDatasheetRegistry(unittest.TestCase):
    def test_fetch_records_hash_and_verify_detects_drift(self):
        with TemporaryDirectory() as td:
            directory = Path(td)
            source = directory / 'src.pdf'
            source.write_bytes(b'%PDF-1.4 fake datasheet for tests')
            with patch.object(datasheets, '_validate_public_pdf_url', side_effect=lambda url: url):
                entry = datasheets.fetch('TMP102AIDRLR', directory, url=source.as_uri())
            self.assertTrue(Path(entry['path']).is_file())
            self.assertEqual(64, len(entry['sha256']))
            self.assertTrue(datasheets.verify('TMP102AIDRLR', directory)['ok'])
            Path(entry['path']).write_bytes(b'%PDF-1.4 tampered')
            self.assertFalse(datasheets.verify('TMP102AIDRLR', directory)['ok'])

    def test_non_pdf_is_refused(self):
        with TemporaryDirectory() as td:
            directory = Path(td)
            bogus = directory / 'x.pdf'
            bogus.write_bytes(b'<html>nope</html>')
            with self.assertRaises(datasheets.DatasheetError):
                with patch.object(datasheets, '_validate_public_pdf_url', side_effect=lambda url: url):
                    datasheets.fetch('TMP102AIDRLR', directory, url=bogus.as_uri())
            self.assertFalse((directory / 'tmp102aidrlr.pdf').exists())

    def test_unknown_part_requires_explicit_url(self):
        with self.assertRaises(datasheets.DatasheetError):
            datasheets.guess_url('XYZ999')


class TestDatasheetUrlSafety(unittest.TestCase):
    def test_rejects_non_web_and_private_ip_urls(self):
        urls = ('file:///etc/passwd', 'ftp://example.com/datasheet.pdf',
                'http://127.0.0.1/latest', 'https://[::1]/datasheet.pdf')
        for url in urls:
            with self.subTest(url=url), self.assertRaises(datasheets.DatasheetError):
                datasheets._validate_public_pdf_url(url)

    def test_rejects_hostnames_with_private_dns_answers(self):
        private = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.8', 443))]
        with patch.object(datasheets.socket, 'getaddrinfo', return_value=private):
            with self.assertRaises(datasheets.DatasheetError):
                datasheets._validate_public_pdf_url('https://datasheet.example/file.pdf')

    def test_accepts_public_hosts_and_rejects_private_redirects(self):
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
        with patch.object(datasheets.socket, 'getaddrinfo', return_value=public):
            self.assertEqual(
                'https://datasheet.example/file.pdf',
                datasheets._validate_public_pdf_url('https://datasheet.example/file.pdf'),
            )
        handler = datasheets._PublicRedirectHandler()
        request = urllib.request.Request('https://datasheet.example/start.pdf')
        with self.assertRaises(datasheets.DatasheetError):
            handler.redirect_request(request, None, 302, 'Found', {}, 'http://127.0.0.1/secret')


class TestPackageSpec(unittest.TestCase):
    def test_citation_is_required(self):
        spec = _spec()
        del spec['geometry']['citation']
        with self.assertRaises(PackageError):
            validate_spec(spec, 'unit')

    def test_pitch_is_required(self):
        spec = _spec()
        spec['geometry']['pitch_mm'] = None
        with self.assertRaises(PackageError):
            validate_spec(spec, 'unit')

    def test_unvetted_spec_cannot_be_enforced(self):
        spec = _spec()
        spec['package']['status'] = 'proposed'
        spec['package']['reviewed_by'] = None
        with TemporaryDirectory() as td:
            path = Path(td) / 'p.json'
            path.write_text(json.dumps(spec))
            with self.assertRaises(PackageError):
                load_spec(path, require_vetted=True)

    def test_vet_requires_a_reviewer_name(self):
        with TemporaryDirectory() as td:
            path = Path(td) / 'p.json'
            path.write_text(json.dumps(_spec()))
            with self.assertRaises(PackageError):
                vet_spec(path, '   ')
            vetted = vet_spec(path, 'Reviewer')
            self.assertEqual('vetted', vetted['package']['status'])

    def test_checked_in_spec_matches_the_datasheet_drawing(self):
        spec = load_spec(PACKAGE, require_vetted=True)
        self.assertEqual('TMP102AIDRLR', spec['package']['part'])
        self.assertEqual(0.5, spec['geometry']['pitch_mm'])   # TI DRL0006A, p.30 "4X 0.5"
        self.assertEqual('30', str(spec['geometry']['citation']['page']))


class TestLandPatternCheck(unittest.TestCase):
    def _board(self):
        design = load_enet(DEMO / 'tmp102.enet')
        board, _ = build_board(design, 32.0, 26.0)
        return design, board

    def test_wrong_pitch_is_caught_with_the_page(self):
        design, board = self._board()
        findings = land_pattern_findings(_spec(pitch=0.65), board, design)
        self.assertTrue(findings)
        top = findings[0]
        self.assertEqual('LAND_PATTERN_MISMATCH', top['code'])
        self.assertIn('0.65', top['message'])
        self.assertIn('0.5', top['message'])
        self.assertIn('p.30', top['message'])

    def test_correct_pitch_passes(self):
        design, board = self._board()
        self.assertEqual([], land_pattern_findings(_spec(pitch=0.5), board, design))

    def test_spec_only_governs_its_own_part(self):
        design, board = self._board()
        spec = _spec()
        spec['package']['part'] = 'LM75B'
        self.assertEqual([], land_pattern_findings(spec, board, design))

    def test_pin_count_mismatch_is_an_error(self):
        design, board = self._board()
        spec = _spec()
        spec['geometry']['pin_count'] = 8
        codes = {f['code'] for f in land_pattern_findings(spec, board, design)}
        self.assertIn('LAND_PATTERN_MISMATCH', codes)


def _board_pair():
    design = load_enet(DEMO / 'tmp102.enet')
    board, _ = build_board(design, 32.0, 26.0)
    return design, board


class TestCurrentCapacity(unittest.TestCase):
    def test_ipc2221_grows_with_width(self):
        self.assertGreater(ipc2221_current(1.0), ipc2221_current(0.25))
        self.assertGreater(ipc2221_current(0.25, external=False),
                           0) if False else self.assertLess(
            ipc2221_current(0.25, external=False), ipc2221_current(0.25, external=True))

    def test_overloaded_net_is_flagged(self):
        design, board = _board_pair()
        board.segments = [__import__('boardproof.pcb', fromlist=['x']).Segment(
            '3V3', 'F.Cu', 1, 1, 10, 1, 0.25)]
        findings = current_findings(board, {'3V3': 5.0}, copper_oz=1.0)
        self.assertEqual(1, len(findings))
        self.assertEqual('TRACK_CURRENT', findings[0]['code'])
        self.assertEqual([], current_findings(board, {'3V3': 0.1}, copper_oz=1.0))


class TestEndToEnd(unittest.TestCase):
    def test_pcb_check_runs_the_datasheet_checks(self):
        design = load_enet(DEMO / 'tmp102.enet')
        board, _ = build_board(design, 32.0, 26.0)
        with TemporaryDirectory() as td:
            path = Path(td) / 'b.kicad_pcb'
            write_board(board, path)
            result = check_board(path, design, packages=[load_spec(PACKAGE, require_vetted=True)],
                                 net_currents={'3V3': 0.05}, run_drc=False)
            self.assertEqual('passed', result['status'])
            self.assertTrue(any('datasheet' in v for v in result['verified']))
            self.assertTrue(any('IPC-2221' in v for v in result['verified']))
            self.assertFalse(any('land patterns not checked' in v for v in result['unverified']))


if __name__ == '__main__':
    unittest.main()
