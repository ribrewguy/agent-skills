"""Tests for probe.py against a hand-authored OTLP file-exporter sample."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe import check, parse  # noqa: E402

SAMPLE = Path(__file__).resolve().parent / "sample-telemetry.jsonl"
SERVICE = "fixture-demo"
CHECK_IDS = [
    "server-spans-same-trace",
    "client-span-under-server",
    "tier2-spans",
    "job-root-with-link",
    "log-correlated",
    "default-metrics",
    "resource-service-name",
    "no-error-on-happy-path",
    "error-on-boom",
]


def results(path=SAMPLE, service=SERVICE):
    return {cid: (ok, detail) for cid, ok, detail in check(parse(path), service)}


class ProbeTest(unittest.TestCase):
    def test_parse_counts(self):
        t = parse(SAMPLE)
        self.assertEqual(len(t.spans), 11)
        self.assertEqual(len(t.logs), 1)
        self.assertEqual(len(t.metrics), 2)

    def test_all_check_ids_reported(self):
        self.assertEqual(sorted(results()), sorted(CHECK_IDS))

    def test_server_spans_same_trace(self):
        self.assertTrue(results()["server-spans-same-trace"][0])

    def test_client_span_under_server(self):
        self.assertTrue(results()["client-span-under-server"][0])

    def test_tier2_spans(self):
        self.assertTrue(results()["tier2-spans"][0])

    def test_job_root_with_link(self):
        self.assertTrue(results()["job-root-with-link"][0])

    def test_log_correlated(self):
        self.assertTrue(results()["log-correlated"][0])

    def test_default_metrics(self):
        self.assertTrue(results()["default-metrics"][0])

    def test_resource_service_name(self):
        self.assertTrue(results()["resource-service-name"][0])

    def test_no_error_on_happy_path(self):
        self.assertTrue(results()["no-error-on-happy-path"][0])

    def test_error_on_boom(self):
        self.assertTrue(results()["error-on-boom"][0])

    def test_wrong_service_name_fails(self):
        self.assertFalse(results(service="unknown_service")["resource-service-name"][0])

    def test_missing_link_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.jsonl"
            lines = []
            for line in SAMPLE.read_text().splitlines():
                doc = json.loads(line)
                for rs in doc.get("resourceSpans", []):
                    for ss in rs["scopeSpans"]:
                        for s in ss["spans"]:
                            s.pop("links", None)
                lines.append(json.dumps(doc))
            p.write_text("\n".join(lines) + "\n")
            self.assertFalse(results(p)["job-root-with-link"][0])

    def test_empty_telemetry_fails_everything(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "empty.jsonl"
            p.write_text("")
            res = results(p)
            self.assertEqual(sorted(res), sorted(CHECK_IDS))
            self.assertTrue(all(not ok for ok, _ in res.values()))


if __name__ == "__main__":
    unittest.main()
