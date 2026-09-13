import unittest

from reconcave.report_html import render_html_report


def _base_result(**overrides):
    result = {
        "target": "example.com",
        "subdomains": [
            {"host": "www.example.com", "ips": ["1.2.3.4"], "resolves": True,
             "status_code": 200, "title": "Example", "source": ["crawl"]},
        ],
        "subdomain_count": 1,
        "diff": {"new": [], "removed": [], "unchanged_count": 1, "is_first_scan": False},
        "crawl": {"pages_visited": 1, "urls": [], "errors": {}, "external_links_found": []},
    }
    result.update(overrides)
    return result


class TestHtmlReportRendering(unittest.TestCase):
    """The HTML report has broken twice before in this project's history
    (once from a template formatting bug, once from --email/--dns-records
    data being silently absent from the output entirely). Every case here
    exists because of one of those two failure classes."""

    def test_renders_valid_html_shell_for_every_case(self):
        cases = [
            _base_result(),
            _base_result(email_security={"available": True, "spf": "v=spf1 ~all", "dmarc": None, "mx": []}),
            _base_result(email_security={"available": False, "reason": "dnspython not installed"}),
            _base_result(dns_records={"available": True, "NS": ["ns1.example.com"], "MX": [], "TXT": []}),
            _base_result(dns_records={"available": False}),
            _base_result(subdomains=[], subdomain_count=0),  # the exact zero-results scenario
        ]
        for i, result in enumerate(cases):
            with self.subTest(case=i):
                out = render_html_report(result)
                self.assertIn("<!DOCTYPE html>", out)
                self.assertIn("</html>", out)

    def test_optional_sections_hidden_when_data_absent(self):
        """Regression test: --email and --dns-records data used to be
        computed and saved to JSON but never shown anywhere in the HTML
        report at all. This confirms the opposite failure mode doesn't
        happen either — a plain scan that never requested this data
        shouldn't show empty/misleading section headers for it."""
        out = render_html_report(_base_result())
        self.assertNotIn("Email security", out)
        self.assertNotIn("DNS records", out)
        self.assertNotIn("External links found", out)

    def test_email_section_shows_actual_values(self):
        result = _base_result(email_security={
            "available": True,
            "spf": "v=spf1 include:_spf.example.com ~all",
            "dmarc": "v=DMARC1; p=reject;",
            "mx": ["mail.example.com"],
        })
        out = render_html_report(result)
        self.assertIn("Email security", out)
        self.assertIn("v=spf1 include:_spf.example.com ~all", out)
        self.assertIn("v=DMARC1; p=reject;", out)
        self.assertIn("mail.example.com", out)

    def test_email_section_shows_not_found_rather_than_blank(self):
        result = _base_result(email_security={"available": True, "spf": None, "dmarc": None, "mx": []})
        out = render_html_report(result)
        self.assertEqual(out.count("not found"), 2)

    def test_dns_section_shows_actual_records(self):
        result = _base_result(dns_records={
            "available": True,
            "NS": ["ns1.example.com", "ns2.example.com"],
            "MX": ["mail.example.com"],
            "TXT": ["v=spf1 ~all"],
        })
        out = render_html_report(result)
        self.assertIn("DNS records", out)
        self.assertIn("ns1.example.com", out)
        self.assertIn("mail.example.com", out)

    def test_external_links_section_lists_hosts(self):
        result = _base_result()
        result["crawl"]["external_links_found"] = ["social.example", "test.net"]
        out = render_html_report(result)
        self.assertIn("External links found", out)
        self.assertIn("social.example", out)
        self.assertIn("test.net", out)

    def test_html_injection_in_title_is_escaped(self):
        """The report displays page titles scraped from arbitrary target
        sites — those must never be inserted unescaped, or a malicious
        target page could inject script into the report a user opens
        locally."""
        result = _base_result()
        result["subdomains"][0]["title"] = "<script>alert(1)</script>"
        out = render_html_report(result)
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;", out)


if __name__ == "__main__":
    unittest.main()
