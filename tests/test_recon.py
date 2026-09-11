import unittest
from unittest.mock import MagicMock, patch

from reconcave.recon import build_subdomain_report, discover_subdomains_crtsh


class TestCrtshDiscovery(unittest.TestCase):
    def test_filters_email_addresses_from_results(self):
        """Regression test for a real bug found via a live scan: crt.sh's name_value field sometimes contains email addresses mixed
        in with real hostnames."""
        fake_response = MagicMock()
        fake_response.json.return_value = [
            {"name_value": "www.example.com\nadmin@example.com"},
            {"name_value": "api.example.com"},
            {"name_value": "weird-b480g7k2ab9@checkout.example.com"},
        ]
        fake_response.raise_for_status.return_value = None

        fake_session = MagicMock()
        fake_session.get.return_value = fake_response

        result = discover_subdomains_crtsh("example.com", fake_session)

        self.assertIn("www.example.com", result)
        self.assertIn("api.example.com", result)
        self.assertNotIn("admin@example.com", result)
        self.assertNotIn("weird-b480g7k2ab9@checkout.example.com", result)

    def test_returns_empty_set_on_request_failure(self):
        fake_session = MagicMock()
        fake_session.get.side_effect = Exception("network down")
        # discover_subdomains_crtsh catches requests.RequestException specifically;
        # simulate that more precisely:
        import requests
        fake_session.get.side_effect = requests.RequestException("network down")

        result = discover_subdomains_crtsh("example.com", fake_session)
        self.assertEqual(result, set())


class TestSubdomainReport(unittest.TestCase):
    @patch("reconcave.recon.resolve_ips")
    def test_merges_crawl_info_without_reprobing(self, mock_resolve):
        mock_resolve.return_value = ["1.2.3.4"]
        fake_session = MagicMock()

        crawl_info = {"www.example.com": {"status_code": 200, "title": "Example"}}
        report = build_subdomain_report(
            hosts={"www.example.com"},
            session=fake_session,
            crawl_host_info=crawl_info,
            probe_live=True,
        )

        self.assertEqual(len(report), 1)
        entry = report[0]
        self.assertEqual(entry["status_code"], 200)
        self.assertEqual(entry["title"], "Example")
        self.assertIn("crawl", entry["source"])
        # Should not have hit the network for a live probe since crawl already had status
        fake_session.get.assert_not_called()

    @patch("reconcave.recon.resolve_ips")
    def test_unresolved_host_marked_correctly(self, mock_resolve):
        mock_resolve.return_value = []
        fake_session = MagicMock()

        report = build_subdomain_report(
            hosts={"dead.example.com"},
            session=fake_session,
            crawl_host_info={},
            probe_live=True,
        )

        self.assertEqual(len(report), 1)
        self.assertFalse(report[0]["resolves"])
        self.assertEqual(report[0]["ips"], [])


if __name__ == "__main__":
    unittest.main()
