import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from boardproof.netlist import load_enet, NetlistError
from boardproof.checks import run_checks
from boardproof.firmware import parse_defines
from boardproof.cli import execute

DEMO = Path(__file__).resolve().parents[1] / 'examples' / 'demo'

class TestBoardProof(unittest.TestCase):
    def test_clean_pass(self):
        config_path=DEMO/'boardproof.clean.json'
        cfg=json.loads(config_path.read_text())
        result=run_checks(load_enet(DEMO/'clean.enet'),cfg,config_path)
        self.assertEqual([],result)

    def test_broken_detects_multiple_independent_categories(self):
        config_path=DEMO/'boardproof.broken.json'
        cfg=json.loads(config_path.read_text())
        result=run_checks(load_enet(DEMO/'broken.enet'),cfg,config_path)
        self.assertEqual(5, len(result))
        kinds={f.code for f in result}
        self.assertEqual({'PIN_NET','MAX_VOLTAGE','CONNECTED','RESISTOR_BETWEEN','FIRMWARE_GPIO'},kinds)

    def test_good_cli_generates_reports(self):
        with TemporaryDirectory() as td:
            o=Path(td)
            self.assertEqual(0,execute(DEMO/'boardproof.clean.json',o/'result.json',o/'result.html',False))
            self.assertEqual('passed',json.loads((o/'result.json').read_text())['status'])
            self.assertIn('BoardProof', (o/'result.html').read_text())

    def test_bad_cli_exits_nonzero_and_generates_reports(self):
        with TemporaryDirectory() as td:
            o=Path(td)
            self.assertEqual(1,execute(DEMO/'boardproof.broken.json',o/'result.json',o/'result.html',True))
            self.assertEqual('failed',json.loads((o/'result.json').read_text())['status'])

    def test_bad_format_rejected(self):
        with TemporaryDirectory() as td:
            p=Path(td)/'standard.json'
            p.write_text(json.dumps({'head':{'docType':'1'},'shape':['LIB~...']}))
            with self.assertRaisesRegex(NetlistError, 'Not an EasyEDA Pro'):
                load_enet(p)

    def test_duplicate_designators_rejected(self):
        with TemporaryDirectory() as td:
            doc=json.loads((DEMO/'clean.enet').read_text())
            doc['components']['duplicate']=doc['components']['demo_U1']
            p=Path(td)/'duplicate.enet';p.write_text(json.dumps(doc))
            with self.assertRaisesRegex(NetlistError, 'Duplicate designator'):
                load_enet(p)

    def test_missing_pin_is_error(self):
        cfg={'schema_version':1,'rules':[{'type':'connected','component':'U1','pin':'999'}]}
        result=run_checks(load_enet(DEMO/'clean.enet'),cfg,DEMO/'boardproof.clean.json')
        self.assertEqual('MISSING_PIN',result[0].code)

    def test_unknown_voltage_fails_closed(self):
        cfg={'schema_version':1,'rules':[{'type':'max_voltage','component':'U1','pin':'1','max_v':3.6}]}
        result=run_checks(load_enet(DEMO/'clean.enet'),cfg,DEMO/'boardproof.clean.json')
        self.assertEqual('VOLTAGE_UNKNOWN',result[0].code)
        self.assertEqual('error',result[0].severity)

    def test_empty_rules_rejected(self):
        with self.assertRaisesRegex(ValueError, 'non-empty'):
            run_checks(load_enet(DEMO/'clean.enet'),{'schema_version':1,'rules':[]},DEMO/'boardproof.clean.json')

    def test_define_simple_numbers_only(self):
        with TemporaryDirectory() as td:
            p=Path(td)/'pin.h';p.write_text('#define A 6\n#define B GPIO_NUM_7\n#define C (0xA)\n')
            d=parse_defines(p)
            self.assertEqual({'A':6,'C':10},d)

    def test_unknown_firmware_macro_fails_closed(self):
        cfg={'schema_version':1,'firmware':'firmware_good.h','rules':[{'type':'firmware_gpio','component':'U1','net':'LED_STATUS','define':'UNDEFINED'}]}
        result=run_checks(load_enet(DEMO/'clean.enet'),cfg,DEMO/'boardproof.clean.json')
        self.assertEqual('FW_UNKNOWN', result[0].code)
        self.assertEqual('error', result[0].severity)

    def test_resistor_value_range(self):
        cfg={'schema_version':1,'rules':[{'type':'resistor_between','net_a':'I2C_SDA','net_b':'3V3','min_ohms':1000,'max_ohms':2000}]}
        result=run_checks(load_enet(DEMO/'clean.enet'),cfg,DEMO/'boardproof.clean.json')
        self.assertEqual('RESISTOR_BETWEEN', result[0].code)

if __name__ == '__main__':
    unittest.main()
