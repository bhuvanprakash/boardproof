"""The HTTP API: preview listing, the datasheet registry, and their guards."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from boardproof import api, datasheets


def _request(method: str = "GET") -> Request:
    return Request({"type": "http", "method": method, "path": "/", "headers": [],
                    "query_string": b"", "client": ("127.0.0.1", 4711),
                    "server": ("127.0.0.1", 8000), "scheme": "http"})


class TestPreviewListing(unittest.TestCase):
    def test_only_schematic_and_datasheet_previews_are_served(self):
        for name in ("schematic.svg", "netlist-schematic.svg", "uno-schematic.png",
                     "datasheet-tmp102.png"):
            self.assertTrue(api._is_preview(name), name)
        for name in ("board.svg", "index.html", "../secrets.png", "datasheet-x.jpg"):
            self.assertFalse(api._is_preview(name), name)

    def test_previews_endpoint_reports_kind_size_and_time(self):
        with TemporaryDirectory() as td:
            preview = Path(td) / "preview"
            preview.mkdir()
            (preview / "schematic.svg").write_text(
                '<svg><text>schematic · 6 parts · 5 nets</text></svg>', encoding="utf-8")
            (preview / "datasheet-tmp102.png").write_bytes(b"\x89PNG fake")
            (preview / "board.svg").write_text("<svg/>", encoding="utf-8")
            with patch.object(api, "OUT_DIR", Path(td)):
                payload = api.get_previews(_request())
        self.assertEqual(2, payload["count"])
        self.assertEqual(1, payload["schematic"])
        self.assertEqual(1, payload["datasheets"])
        self.assertEqual({"schematic.svg", "datasheet-tmp102.png"},
                         {item["name"] for item in payload["previews"]})
        entry = next(item for item in payload["previews"] if item["name"] == "schematic.svg")
        self.assertGreater(entry["bytes"], 0)
        self.assertRegex(entry["modified"], r"T\d{2}:\d{2}:\d{2}\+00:00$")
        self.assertEqual((6, 5), (entry["parts"], entry["nets"]))
        page = next(item for item in payload["previews"] if item["kind"] == "datasheet")
        self.assertIsNone(page["parts"])


class TestDatasheetEndpoints(unittest.TestCase):
    @staticmethod
    def _store(directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        pdf = directory / "tmp102aidrlr.pdf"
        pdf.write_bytes(b"%PDF-1.4 fixture datasheet")
        registry = {"schema_version": 1, "documents": {"tmp102aidrlr": {
            "part": "TMP102AIDRLR", "path": str(pdf), "sha256": datasheets.sha256(pdf),
            "url": "https://example.com/tmp102.pdf",
            "fetched_at": "2026-01-01T00:00:00+00:00", "status": "cached"}}}
        (directory / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
        return directory

    def test_registry_reports_presence_hash_and_cited_page(self):
        with TemporaryDirectory() as td:
            directory = self._store(Path(td) / "datasheets")
            preview = Path(td) / "preview"
            preview.mkdir()
            (preview / "datasheet-tmp102aidrlr.png").write_bytes(b"\x89PNG fake")
            with patch.object(api, "DATASHEETS_DIR", directory), \
                 patch.object(api, "OUT_DIR", Path(td)):
                payload = api.get_datasheets(_request())
        self.assertIn("TMP", payload["prefixes"])
        self.assertGreaterEqual(payload["max_pdf_mb"], 1)
        document = payload["documents"][0]
        self.assertTrue(document["exists"])
        self.assertTrue(document["hash_ok"])
        self.assertEqual("datasheet-tmp102aidrlr.png", document["page"])
        self.assertEqual("/api/datasheets/pdf/tmp102aidrlr", document["pdf"])

    def test_a_registry_entry_without_its_file_is_reported_not_hidden(self):
        with TemporaryDirectory() as td:
            directory = self._store(Path(td) / "datasheets")
            (directory / "tmp102aidrlr.pdf").unlink()
            with patch.object(api, "DATASHEETS_DIR", directory):
                payload = api.get_datasheets(_request())
        document = payload["documents"][0]
        self.assertFalse(document["exists"])
        self.assertFalse(document["hash_ok"])

    def test_pdf_download_and_traversal_guard(self):
        with TemporaryDirectory() as td:
            directory = self._store(Path(td) / "datasheets")
            with patch.object(api, "DATASHEETS_DIR", directory):
                response = api.get_datasheet_pdf("TMP102AIDRLR", _request())
                self.assertEqual(200, response.status_code)
                with self.assertRaises(HTTPException) as caught:
                    api.get_datasheet_pdf("../../etc/passwd", _request())
        self.assertEqual(404, caught.exception.status_code)

    def test_verify_flags_a_tampered_file(self):
        with TemporaryDirectory() as td:
            directory = self._store(Path(td) / "datasheets")
            body = api.DatasheetVerifyRequest(part="TMP102AIDRLR")
            with patch.object(api, "DATASHEETS_DIR", directory):
                self.assertTrue(api.verify_datasheet(body, _request())["ok"])
                (directory / "tmp102aidrlr.pdf").write_bytes(b"%PDF-1.4 tampered")
                self.assertFalse(api.verify_datasheet(body, _request())["ok"])

    def test_verify_all_reports_every_document(self):
        with TemporaryDirectory() as td:
            directory = self._store(Path(td) / "datasheets")
            with patch.object(api, "DATASHEETS_DIR", directory):
                payload = api.verify_all_datasheets(_request())
                self.assertTrue(payload["ok"])
                self.assertEqual(1, payload["count"])
                (directory / "tmp102aidrlr.pdf").write_bytes(b"%PDF-1.4 tampered")
                payload = api.verify_all_datasheets(_request())
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["results"][0]["ok"])
        self.assertEqual("", payload["results"][0]["note"])
        self.assertEqual("TMP102AIDRLR", payload["results"][0]["part"])
    def test_fetch_pins_a_pdf_and_refuses_a_non_pdf(self):
        with TemporaryDirectory() as td:
            directory = Path(td) / "datasheets"
            source = Path(td) / "src.pdf"
            source.write_bytes(b"%PDF-1.4 fetched")
            with patch.object(api, "DATASHEETS_DIR", directory), patch.object(
                    datasheets, "_validate_public_pdf_url", side_effect=lambda url: url):
                entry = api.fetch_datasheet(
                    api.DatasheetFetchRequest(part=" XYZ9 ", url=source.as_uri()), _request())
                self.assertEqual("xyz9", entry["slug"])
                self.assertTrue(entry["exists"])
                source.write_bytes(b"<html>not a pdf</html>")
                with self.assertRaises(HTTPException) as caught:
                    api.fetch_datasheet(
                        api.DatasheetFetchRequest(part="XYZ9", url=source.as_uri(),
                                                  refresh=True), _request())
        self.assertEqual(422, caught.exception.status_code)

    def test_unknown_part_without_url_is_a_client_error(self):
        with TemporaryDirectory() as td:
            with patch.object(api, "DATASHEETS_DIR", Path(td)):
                with self.assertRaises(HTTPException) as caught:
                    api.fetch_datasheet(api.DatasheetFetchRequest(part="XYZ999"), _request())
        self.assertEqual(422, caught.exception.status_code)


if __name__ == "__main__":
    unittest.main()
