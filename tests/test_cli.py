import unittest

from reconcave.cli import split_by_scope


class TestScopeFiltering(unittest.TestCase):
    """Regression tests for two real bugs found via a live scan during
    development:

    1. The crawler correctly refuses to *follow* outbound links to third
       parties, but was still reporting those third parties as if they
       were in-scope subdomains — meaning an unrelated external domain
       ended up DNS-resolved, TLS-checked, and HTTP-probed just because
       the target site's homepage linked to it.

    2. The first fix for (1) then over-corrected: it used
       --include-subdomains (a crawl-recursion setting) to decide scope,
       which wrongly excluded a genuine subdomain of the target as
       "external" whenever --include-subdomains wasn't passed. Scope
       must be decided by registrable domain, not by the crawl-recursion
       flag.
    """

    def test_outbound_links_are_excluded_from_scope(self):
        crawl_urls = {
            "https://example.com/",
            "https://example.com/about",
            "https://blog.example.com/first-post",
            "http://social.example/ExampleCompany",
            "http://test.net/some-page",
        }
        in_scope, external = split_by_scope(crawl_urls, "example.com")

        self.assertIn("example.com", in_scope)
        self.assertIn("social.example", external)
        self.assertIn("test.net", external)

    def test_real_subdomain_stays_in_scope_regardless_of_crawl_recursion_setting(self):
        """blog.example.com must be in-scope even though it's a different
        host than example.com and even if --include-subdomains was never
        passed — that flag only controls crawl recursion, not reporting
        scope."""
        crawl_urls = {"https://example.com/", "https://blog.example.com/first-post"}
        in_scope, external = split_by_scope(crawl_urls, "example.com")

        self.assertIn("blog.example.com", in_scope)
        self.assertNotIn("blog.example.com", external)

    def test_different_registrable_domain_is_external(self):
        crawl_urls = {"https://example.com/", "https://test.net/page"}
        in_scope, external = split_by_scope(crawl_urls, "example.com")

        self.assertIn("example.com", in_scope)
        self.assertIn("test.net", external)


if __name__ == "__main__":
    unittest.main()
