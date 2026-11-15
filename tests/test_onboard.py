"""Upload: netlist, KiCad layout, or a written brief emit layout + Gerbers."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from boardproof.footprints import resolve
from boardproof.onboard import UploadError, design_from_proposal, onboard
from boardproof.pcbcheck import find_kicad_cli

ROOT = Path(__file__).resolve().parents[1]
JEDEN = ROOT / 'boards' / 'jeden-arduino' / 'Jeden-Board.kicad_pcb'


class TestOnboard(unittest.TestCase):
    def test_empty_is_rejected(self):
        with TemporaryDirectory() as td:
            with self.assertRaises(UploadError):
                onboard(ROOT, Path(td), 'board.enet', b'')

    def test_kicad_pcb_writes_layout_and_svg(self):
        with TemporaryDirectory() as td:
            out = Path(td)
            result = onboard(ROOT, out, 'clone.kicad_pcb', JEDEN.read_bytes())
            self.assertTrue(result['ok'], result)
            self.assertEqual('clone.kicad_pcb', result['board'])
            self.assertTrue((out / 'clone.kicad_pcb').is_file())
            self.assertTrue((out / 'clone.svg').is_file())
            self.assertTrue((out / 'clone-3d.svg').is_file())
            labels = {row['label'] for row in result['downloads']}
            self.assertIn('KiCad board', labels)
            self.assertIn('U1', (out / 'clone.svg').read_text())

    def test_arduino_brief_generates_new_board_not_jeden_demo(self):
        with TemporaryDirectory() as td:
            out = Path(td)
            result = onboard(ROOT, out, 'brief.txt', b'',
                             brief='Arduino Uno clone with ATmega328P', kind='brief',
                             engine='offline')
            self.assertTrue(result['ok'], result)
            self.assertNotEqual('Jeden-Board.kicad_pcb', result['board'])
            self.assertTrue((out / result['board']).is_file())
            self.assertGreaterEqual(result['components'], 6)
            svg = (out / (Path(result['board']).stem + '.svg')).read_text()
            self.assertIn('U1', svg)
            labels = {row['label'] for row in result['downloads']}
            self.assertIn('KiCad board', labels)
            self.assertIn('2D view', labels)
            if find_kicad_cli():
                self.assertIn('Gerbers (zip)', labels)

    def test_brief_uses_gemini_path_offline_and_writes_board(self):
        with TemporaryDirectory() as td:
            out = Path(td)
            result = onboard(ROOT, out, 'blink.txt', b'',
                             brief='3.3V MCU with a 4.7k resistor and an LED on GPIO',
                             kind='brief', engine='offline')
            self.assertTrue(result['ok'], result)
            self.assertTrue(result['board'])
            self.assertTrue((out / result['board']).is_file())
            self.assertTrue((out / Path(result['board']).stem).with_suffix('.svg').is_file()
                            or (out / (Path(result['board']).stem + '.svg')).is_file())
            self.assertGreaterEqual(result['components'], 3)
            self.assertTrue(any('offline' in line for line in result['log']))

    def test_proposal_keeps_four_connectors_and_header_pins(self):
        pattern, source = resolve('J2', '', 'PinHeader_1x8_P2.54mm',
                                  [str(i) for i in range(1, 9)])
        self.assertEqual(8, len(pattern.pads))
        self.assertEqual('designator', source)
        data = {
            'title': 'farm',
            'arduino': False,
            'components': [
                {'ref': 'U1', 'value': 'MCU', 'part': 'DEMO', 'footprint': 'SOT563-6',
                 'pins': [{'number': '1', 'name': 'VDD', 'net': '3V3'},
                          {'number': '2', 'name': 'GND', 'net': 'GND'}]},
            ] + [
                {'ref': f'J{i}', 'value': 'HDR', 'part': '', 'footprint': 'PinHeader_1x4_P2.54mm',
                 'pins': [{'number': '1', 'name': '1', 'net': 'GND'}]}
                for i in range(1, 8)
            ],
        }
        design = design_from_proposal(data, 'test')
        self.assertEqual(1, sum(1 for ref in design.components if ref.startswith('U')))
        self.assertEqual(4, sum(1 for ref in design.components if ref.startswith('J')))
