import unittest

from reconcave.utils import (
    is_valid_hostname,
    normalize_url,
    registrable_domain,
    same_domain,
)


class TestHostnameValidation(unittest.TestCase):
    def test_valid_hostnames(self):
        for host in ["example.com", "www.example.com", "a.b.c.example.co.uk", "x-1.example.com"]:
            self.assertTrue(is_valid_hostname(host), host)

    def test_rejects_email_addresses(self):
        # This is the exact bug class seen in real crt.sh output
        for junk in ["admin@example.com", "aarjav-b480g7k2ab9@checkout.example.com"]:
            self.assertFalse(is_valid_hostname(junk), junk)

    def test_rejects_wildcards_and_whitespace(self):
        self.assertFalse(is_valid_hostname("*.example.com"))
        self.assertFalse(is_valid_hostname("exa mple.com"))
        self.assertFalse(is_valid_hostname(""))


class TestNormalizeUrl(unittest.TestCase):
    def test_strips_fragment(self):
        self.assertEqual(normalize_url("https://x.com/page#section"), "https://x.com/page")

    def test_strips_trailing_slash_except_root(self):
        self.assertEqual(normalize_url("https://x.com/page/"), "https://x.com/page")
        self.assertEqual(normalize_url("https://x.com/"), "https://x.com/")

    def test_lowercases_scheme_and_host(self):
        self.assertEqual(normalize_url("HTTPS://EXAMPLE.com/Path"), "https://example.com/Path")


class TestRegistrableDomain(unittest.TestCase):
    def test_simple_domain(self):
        self.assertEqual(registrable_domain("www.example.com"), "example.com")

    def test_deep_subdomain(self):
        self.assertEqual(registrable_domain("a.b.c.example.com"), "example.com")

    def test_bare_domain_unchanged(self):
        self.assertEqual(registrable_domain("example.com"), "example.com")


class TestSameDomain(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(same_domain("https://example.com/x", "example.com", include_subdomains=False))

    def test_subdomain_rejected_when_disabled(self):
        self.assertFalse(same_domain("https://sub.example.com/x", "example.com", include_subdomains=False))

    def test_subdomain_allowed_when_enabled(self):
        self.assertTrue(same_domain("https://sub.example.com/x", "example.com", include_subdomains=True))

    def test_different_domain_rejected(self):
        self.assertFalse(same_domain("https://other.com/x", "example.com", include_subdomains=True))


if __name__ == "__main__":
    unittest.main()
