"""Preview assets: the schematic must fit its own pins, and PDF rasterising must admit failure."""
import xml.etree.ElementTree as ET
from pathlib import Path
import unittest

from boardproof.netlist import load_enet
from boardproof.preview import render_pdf_page, render_schematic

ROOT = Path(__file__).resolve().parents[1]
NETLIST = ROOT / "examples" / "tmp102" / "rev-c-fixed.enet"
SVG = "{http://www.w3.org/2000/svg}"


class TestSchematicLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svg = render_schematic(load_enet(NETLIST))
        cls.root = ET.fromstring(cls.svg)

    def test_sheet_is_well_formed_and_labelled_as_derived(self):
        self.assertTrue(self.root.tag.endswith("svg"))
        self.assertIn("derived connectivity, not the original schematic sheet", self.svg)

    def test_every_pin_stub_lands_inside_its_component_box(self):
        """A pin drawn outside its block is a layout bug, not a style choice."""
        boxes = [element for element in self.root.iter(f"{SVG}rect")
                 if element.get("x") == "24"]
        stubs = [element for element in self.root.iter(f"{SVG}line")
                 if element.get("x1") == "156"]
        self.assertTrue(boxes and stubs)
        for stub in stubs:
            y = float(stub.get("y1"))
            inside = any(float(box.get("y")) <= y <= float(box.get("y")) + float(box.get("height"))
                         for box in boxes)
            self.assertTrue(inside, f"pin stub at y={y} falls outside every component box")

    def test_component_boxes_do_not_overlap_each_other(self):
        boxes = sorted((float(element.get("y")), float(element.get("height")))
                       for element in self.root.iter(f"{SVG}rect") if element.get("x") == "24")
        for (top_a, height_a), (top_b, _) in zip(boxes, boxes[1:]):
            self.assertLess(top_a + height_a, top_b, "component rows overlap")

    def test_view_box_covers_every_drawn_box(self):
        view_height = float(self.root.get("viewBox").split()[3])
        for element in self.root.iter(f"{SVG}rect"):
            top, box_height = element.get("y"), element.get("height")
            if top is None or box_height is None or "%" in box_height:
                continue  # the full-bleed background rect
            bottom = float(top) + float(box_height)
            self.assertLessEqual(bottom, view_height, "element drawn past the sheet edge")


class TestPdfPage(unittest.TestCase):
    def test_missing_pdf_is_reported_not_raised(self):
        result = render_pdf_page(ROOT / "datasheets" / "does-not-exist.pdf", 3,
                                 Path("/tmp/boardproof-should-not-exist.png"))
        self.assertFalse(result["available"])
        self.assertIn("not on disk", result["note"])

    def test_a_non_numeric_page_is_refused(self):
        result = render_pdf_page(ROOT / "datasheets" / "tmp102.pdf", "front cover",
                                 Path("/tmp/boardproof-should-not-exist.png"))
        self.assertFalse(result["available"])
        self.assertIn("not a number", result["note"])


if __name__ == "__main__":
    unittest.main()
