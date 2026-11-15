"""The three artifacts that leave the tool: passport, draft config, dashboard."""
import json
import threading
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from boardproof.checks import run_checks
from boardproof.cli import execute, main
from boardproof.dashboard import collect, render
from boardproof.init import draft_config
from boardproof.netlist import load_enet
from boardproof.passport import build, passport_hash, render as render_passport
from boardproof.serve import serve

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'examples' / 'demo'


def _summary(config, out_dir):
    out = Path(out_dir) / 'report.json'
    execute(config, out, None, False)
    return json.loads(out.read_text())


class TestPassport(unittest.TestCase):
    def test_passport_answers_the_three_questions(self):
        with TemporaryDirectory() as td:
            data = _summary(DEMO / 'boardproof.pack.json', td)
            document = build(data, revision='Condor Mini+ · Revision B')
            page = render_passport(document)
            self.assertEqual('blocked', document['status'])
            self.assertEqual(5, document['counts']['critical'])
            self.assertTrue(document['counts']['unverified'] >= 1)
            self.assertIn('BLOCKED', page)
            self.assertIn('Critical failures', page)
            self.assertIn('Verified by this run', page)
            self.assertIn('Not verified', page)
            self.assertIn('Manufacturing Preflight Passport', page)
            self.assertIn('Condor Mini+', page)
            self.assertEqual(64, len(document['passport_hash']))
            self.assertIn(document['passport_hash'][:32], page)

    def test_hash_identifies_the_verdict(self):
        with TemporaryDirectory() as td:
            clean = _summary(DEMO / 'boardproof.pack.clean.json', td)
            broken = _summary(DEMO / 'boardproof.pack.json', td)
            self.assertNotEqual(passport_hash(clean), passport_hash(broken))
            self.assertEqual(passport_hash(clean), passport_hash(dict(clean)))
            self.assertEqual('cleared', build(clean)['status'])

    def test_redteam_and_delta_are_embedded(self):
        with TemporaryDirectory() as td:
            clean = _summary(DEMO / 'boardproof.pack.clean.json', td)
            broken = _summary(DEMO / 'boardproof.pack.json', td)
            redteam = json.loads((ROOT / 'artifacts' / 'redteam.json').read_text()) \
                if (ROOT / 'artifacts' / 'redteam.json').exists() else None
            document = build(broken, base=clean, redteam=redteam)
            page = render_passport(document)
            self.assertEqual(5, document['delta']['summary']['introduced'])
            self.assertIn('Change since previous revision', page)
            if redteam:
                self.assertIn('Fault coverage', page)

    def test_passport_cli_writes_artifacts_and_keeps_the_verdict(self):
        with TemporaryDirectory() as td:
            html_out = Path(td) / 'passport.html'
            json_out = Path(td) / 'passport.json'
            code = main(['passport', '--config', str(DEMO / 'boardproof.pack.json'),
                         '--out', str(html_out), '--json', str(json_out),
                         '--revision', 'Rev B', '--engine', 'offline'])
            self.assertEqual(1, code)
            doc = json.loads(json_out.read_text())
            self.assertEqual('manufacturing-preflight-passport', doc['kind'])
            self.assertEqual('Rev B', doc['revision'])
            self.assertTrue(html_out.is_file())


class TestDraftConfig(unittest.TestCase):
    def test_generated_rules_never_block_a_build(self):
        design = load_enet(DEMO / 'broken.enet')
        config, notes = draft_config(design, 'broken.enet')
        self.assertTrue(config['rules'])
        for rule in config['rules']:
            self.assertEqual('warning', rule['severity'])
            self.assertIn('DRAFT', rule['note'])
        findings = run_checks(design, config, DEMO / 'boardproof.pack.json')
        # Whatever the draft finds, nothing may be an error: a generated rule cannot block CI.
        self.assertEqual([], [f for f in findings if f.severity == 'error'])
        self.assertTrue(any('GUESSED' in n for n in notes))

    def test_init_cli_writes_a_usable_draft(self):
        with TemporaryDirectory() as td:
            out = Path(td) / 'boardproof.json'
            self.assertEqual(0, main(['init', '--netlist', str(DEMO / 'clean.enet'), '--out', str(out)]))
            config = json.loads(out.read_text())
            self.assertEqual(1, config['schema_version'])
            self.assertIn('unverified_scope', config)
            # The emitted config is loadable and yields no blocking findings.
            findings = run_checks(load_enet(DEMO / 'clean.enet'), config, out)
            self.assertEqual([], [f for f in findings if f.severity == 'error'])


class TestDashboard(unittest.TestCase):
    def test_dashboard_links_every_artifact(self):
        with TemporaryDirectory() as td:
            directory = Path(td)
            execute(DEMO / 'boardproof.pack.json', directory / 'broken.json',
                    directory / 'broken.html', False)
            main(['redteam', '--config', str(DEMO / 'boardproof.pack.clean.json'),
                  '--json', str(directory / 'redteam.json')])
            main(['passport', '--config', str(DEMO / 'boardproof.pack.json'),
                  '--out', str(directory / 'passport.html'),
                  '--json', str(directory / 'passport.json'), '--engine', 'offline'])
            found = collect(directory)
            self.assertEqual(1, len(found['reports']))
            self.assertIsNotNone(found['passport'])
            self.assertIsNotNone(found['redteam'])
            page = render(found)
            self.assertIn('Your PCB compiles', page)
            self.assertIn('first line of defense between a design and a mistake', page)
            self.assertIn('broken.html', page)
            self.assertIn('Passport ·', page)
            self.assertIn('Red team', page)
            self.assertIn('How a revision flows', page)
            self.assertIn('Made by Team SuperX', page)

    def test_dashboard_cli_writes_index(self):
        with TemporaryDirectory() as td:
            self.assertEqual(0, main(['dashboard', '--dir', td]))
            self.assertTrue((Path(td) / 'index.html').is_file())


class TestServe(unittest.TestCase):
    def test_health_endpoint_for_cloud_run(self):
        with TemporaryDirectory() as td:
            (Path(td) / 'index.html').write_text('<h1>ok</h1>', encoding='utf-8')
            httpd = serve(Path(td), 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            port = httpd.server_address[1]
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=5) as response:
                    body = json.loads(response.read())
                    self.assertEqual('ok', body['status'])
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=5) as response:
                    self.assertIn(b'ok', response.read())
            finally:
                httpd.shutdown()
                httpd.server_close()


if __name__ == '__main__':
    unittest.main()
