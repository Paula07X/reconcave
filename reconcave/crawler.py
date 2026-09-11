"""Recursive, concurrent, same-domain page crawler."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .network import DEFAULT_USER_AGENT, RateLimiter, RobotsCache, build_session
from .utils import normalize_url, same_domain

log = logging.getLogger("reconcave")


class Crawler:
    def __init__(
        self,
        start_url,
        max_depth=2,
        workers=8,
        delay=0.2,
        include_subdomains=False,
        timeout=10.0,
        user_agent=DEFAULT_USER_AGENT,
        respect_robots=True,
        max_pages=None,
        session=None,
    ):
        self.start_url = normalize_url(start_url)
        self.base_netloc = urlparse(self.start_url).netloc.lower()
        self.max_depth = max_depth
        self.workers = workers
        self.include_subdomains = include_subdomains
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.max_pages = max_pages

        self.session = session or build_session(user_agent)
        self.rate_limiter = RateLimiter(delay)
        self.robots = RobotsCache(self.session, user_agent) if respect_robots else None

        self.visited = set()
        self.all_urls = set()
        self.host_info = {}  # host -> {"status_code": int|None, "title": str|None}
        self.errors = {}
        self._lock = Lock()

    def _record_host(self, url, status_code=None, title=None):
        host = urlparse(url).netloc.lower()
        with self._lock:
            info = self.host_info.setdefault(host, {"status_code": None, "title": None})
            if status_code is not None:
                info["status_code"] = status_code
            if title:
                info["title"] = title

    def _fetch(self, url):
        netloc = urlparse(url).netloc.lower()
        self.rate_limiter.wait(netloc)
        try:
            resp = self.session.get(url, timeout=self.timeout)
            self._record_host(url, status_code=resp.status_code)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            with self._lock:
                self.errors[url] = str(e)
            log.error("Failed to fetch %s: %s", url, e)
            return None

    def _extract_links(self, page_url, html):
        soup = BeautifulSoup(html, "html.parser")
        found = set()
        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                continue
            found.add(normalize_url(urljoin(page_url, href)))
        title_tag = soup.find("title")
        if title_tag and title_tag.text:
            self._record_host(page_url, title=title_tag.text.strip()[:200])
        return found

    def _crawl_page(self, url, depth):
        if self.respect_robots and not self.robots.allowed(url):
            log.info("Blocked by robots.txt: %s", url)
            return url, set(), depth
        resp = self._fetch(url)
        if resp is None:
            return url, set(), depth
        if "html" not in resp.headers.get("Content-Type", ""):
            return url, set(), depth
        links = self._extract_links(url, resp.content)
        log.info("[depth %d] %s -> %d links found", depth, url, len(links))
        return url, links, depth

    def crawl(self):
        frontier = {self.start_url: 0}
        try:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                while frontier:
                    if self.max_pages and len(self.visited) >= self.max_pages:
                        log.info("Reached max_pages limit; stopping.")
                        break

                    batch = list(frontier.items())
                    frontier = {}
                    futures = {}
                    for url, depth in batch:
                        if url in self.visited:
                            continue
                        if self.max_pages and len(self.visited) >= self.max_pages:
                            break
                        self.visited.add(url)
                        futures[pool.submit(self._crawl_page, url, depth)] = (url, depth)

                    for fut in as_completed(futures):
                        page_url, links, depth = fut.result()
                        self.all_urls.add(page_url)
                        self.all_urls.update(links)
                        if depth < self.max_depth:
                            for link in links:
                                if (
                                    link not in self.visited
                                    and link not in frontier
                                    and same_domain(link, self.base_netloc, self.include_subdomains)
                                ):
                                    frontier[link] = depth + 1
        except KeyboardInterrupt:
            log.warning(
                "Stopped by user — showing %d page(s) crawled so far.", len(self.visited)
            )

        log.info(
            "Crawl complete: %d pages visited, %d unique URLs, %d errors.",
            len(self.visited), len(self.all_urls), len(self.errors),
        )
        return self.all_urls
