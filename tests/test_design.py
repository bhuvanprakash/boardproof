"""Verify → generate → verify again: the layout leg."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from boardproof.cli import main
from boardproof.design import build_board, parse_outline, write_board
from boardproof.netlist import load_enet
from boardproof.pcb import read_kicad
from boardproof.pcbcheck import check_board

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'examples' / 'tmp102'
GOOD = DEMO / 'boardproof.json'
BAD = DEMO / 'boardproof.5v.json'


class TestOutline(unittest.TestCase):
    def test_parses_and_validates(self):
        self.assertEqual((32.0, 26.0), parse_outline('32x26mm'))
        self.assertEqual((40.0, 30.0), parse_outline('40 x 30'))
        with self.assertRaises(ValueError):
            parse_outline('32')
        with self.assertRaises(ValueError):
            parse_outline('1x1mm')


class TestGeneration(unittest.TestCase):
    def test_board_matches_the_schematic_pad_for_pad(self):
        design = load_enet(DEMO / 'tmp102.enet')
        board, report = build_board(design, 44.0, 48.0)
        self.assertEqual(5, report['board']['footprints'])
        self.assertEqual(14, report['board']['pads'])
        for footprint in board.footprints:
            for pad in footprint.pads:
                self.assertEqual(design.pin(pad.ref, pad.number).net, pad.net,
                                 f"{pad.ref}.{pad.number} net mismatch")

    def test_every_netlist_component_is_placed_once(self):
        design = load_enet(DEMO / 'tmp102.enet')
        board, report = build_board(design, 32.0, 26.0)
        refs = [f.ref for f in board.footprints]
        self.assertEqual(sorted(design.components), sorted(refs))
        self.assertEqual(len(refs), len(set(refs)))
        self.assertTrue(all(report['placement']))

    def test_generated_file_round_trips(self):
        design = load_enet(DEMO / 'tmp102.enet')
        board, _ = build_board(design, 44.0, 48.0)
        with TemporaryDirectory() as td:
            path = Path(td) / 'b.kicad_pcb'
            write_board(board, path)
            reparsed = read_kicad(path.read_text())
            self.assertEqual(board.width, reparsed.width)
            self.assertEqual(len(board.pads()), len(reparsed.pads()))
            self.assertEqual(len(board.segments), len(reparsed.segments))
            self.assertEqual(len(board.vias), len(reparsed.vias))

    def test_router_refuses_geometry_it_cannot_clear(self):
        """0.5 mm pitch: a 0.6 mm via cannot fan out, so the router must refuse."""
        design = load_enet(DEMO / 'tmp102.enet')
        with self.assertRaises(ValueError) as ctx:
            build_board(design, 44.0, 48.0, route=True)
        self.assertIn('refusing to emit', str(ctx.exception))

    def test_verified_placement_board_passes_the_physical_check(self):
        design = load_enet(DEMO / 'tmp102.enet')
        board, _ = build_board(design, 32.0, 26.0)
        with TemporaryDirectory() as td:
            path = Path(td) / 'placement.kicad_pcb'
            write_board(board, path)
            result = check_board(path, design, run_drc=False)
            self.assertEqual('passed', result['status'], result['findings'][:3])
            self.assertEqual(0, result['counts']['error'])

    def test_unrouted_board_reports_notices_not_failures(self):
        design = load_enet(DEMO / 'tmp102.enet')
        board, _ = build_board(design, 32.0, 26.0, route=False)
        with TemporaryDirectory() as td:
            path = Path(td) / 'placement.kicad_pcb'
            write_board(board, path)
            result = check_board(path, design)
            self.assertEqual('passed', result['status'])
            self.assertTrue(any(f['severity'] == 'notice' and f['code'] == 'UNROUTED_NET'
                                for f in result['findings']))


class TestPhysicalVerification(unittest.TestCase):
    def test_swapped_pad_net_is_caught(self):
        """The whole point: a board that looks fine but disagrees with the schematic."""
        design = load_enet(DEMO / 'tmp102.enet')
        board, _ = build_board(design, 32.0, 26.0)
        with TemporaryDirectory() as td:
            path = Path(td) / 'b.kicad_pcb'
            write_board(board, path)
            text = path.read_text()
            # move U1.SDA onto the 3V3 net in the file only
            import re
            ident = re.search(r'\(net (\d+) "I2C_SDA"\)', text).group(1)
            tampered = text.replace(f'(net {ident} "I2C_SDA")', '(net 1 "3V3")')
            self.assertNotEqual(text, tampered)
            path.write_text(tampered)
            result = check_board(path, design)
            self.assertEqual('failed', result['status'])
            codes = {f['code'] for f in result['findings']}
            self.assertIn('PAD_NET_MISMATCH', codes)

    def test_missing_footprint_is_caught(self):
        design = load_enet(DEMO / 'tmp102.enet')
        board, _ = build_board(design, 32.0, 26.0)
        board.footprints = [f for f in board.footprints if f.ref != 'R3']
        with TemporaryDirectory() as td:
            path = Path(td) / 'b.kicad_pcb'
            write_board(board, path)
            result = check_board(path, design)
            self.assertIn('MISSING_FOOTPRINT', {f['code'] for f in result['findings']})


class TestDesignCli(unittest.TestCase):
    def test_design_refuses_a_schematic_that_fails_review(self):
        with TemporaryDirectory() as td:
            out = Path(td) / 'bad.kicad_pcb'
            self.assertEqual(1, main(['design', '--config', str(BAD), '--output', str(out)]))
            self.assertFalse(out.exists())

    def test_design_then_pcb_check(self):
        with TemporaryDirectory() as td:
            board = Path(td) / 'b.kicad_pcb'
            report = Path(td) / 'd.json'
            self.assertEqual(0, main(['design', '--config', str(GOOD), '--output', str(board),
                                      '--json', str(report), '--outline', '32x26mm']))
            self.assertTrue(board.exists())
            self.assertTrue(Path(td) / 'b.svg')
            data = json.loads(report.read_text())
            self.assertEqual('design', data['kind'])
            self.assertFalse(data['routing']['attempted'])
            self.assertEqual(0, main(['pcb-check', '--board', str(board), '--config', str(GOOD)]))


class TestBoardView(unittest.TestCase):
    def test_jeden_render_draws_named_parts_and_covers_copper(self):
        from boardproof.pcbview import board_model, render_2d

        board = read_kicad((ROOT / 'boards' / 'jeden-arduino' / 'Jeden-Board.kicad_pcb').read_text())
        svg = render_2d(board)
        self.assertIn('U1', svg)
        self.assertIn('LED1', svg)
        self.assertIn('J7', svg)
        self.assertGreater(svg.lower().count('<rect'), 40)
        self.assertNotIn('overflow="hidden"', svg)
        model = board_model(board)
        self.assertEqual(29, len(model['parts']))
        self.assertEqual('arduino', model['look'])
        kinds = {part['kind'] for part in model['parts']}
        self.assertTrue({'dip', 'usb', 'header', 'led'} <= kinds)
        u1 = next(part for part in board.footprints if part.ref == 'U1')
        from boardproof.pcbview import _centre, _visual_size
        cx, cy = _centre(u1)
        bw, bh = _visual_size(u1, 'dip')
        self.assertGreaterEqual(cx - bw / 2, -0.8)
        self.assertLessEqual(cx + bw / 2, board.width + 0.8)
        self.assertGreaterEqual(cy - bh / 2, -0.8)
        self.assertLessEqual(cy + bh / 2, board.height + 0.8)



if __name__ == '__main__':
    unittest.main()
