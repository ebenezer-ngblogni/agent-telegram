import asyncio
import random
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .base import BaseScraper, Offer


class IndeedScraper(BaseScraper):
    """Indeed France — Playwright requis (JS)."""

    name = "indeed"
    BASE_URL = "https://fr.indeed.com"
    SEARCH_URL = "https://fr.indeed.com/jobs"

    async def search_offers(self, query: str, location: str, page) -> list[Offer]:
        offers = []
        for page_num in range(self.config.MAX_PAGES_PER_QUERY):
            params = {
                "q": query,
                "l": location,
                "sc": "0kf:attr(DSQF7)jt(apprenticeship);",  # filtre alternance
                "start": page_num * 10,
                "sort": "date",
            }
            url = f"{self.SEARCH_URL}?{urlencode(params)}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.config.PLAYWRIGHT_TIMEOUT)
                await page.wait_for_timeout(self.config.PAGE_LOAD_WAIT)

                try:
                    await page.click('[aria-label="Fermer"]', timeout=2000)
                except Exception:
                    pass

                html = await page.content()
                page_offers = self._parse_search_results(html)
                if not page_offers:
                    break
                offers.extend(page_offers)
                delay = random.uniform(*self.config.DELAY_BETWEEN_REQUESTS)
                await asyncio.sleep(delay)
            except Exception as e:
                print(f"[Indeed] Erreur page {page_num} pour '{query}': {e}")
                break
        return offers

    def _parse_search_results(self, html: str) -> list[Offer]:
        soup = BeautifulSoup(html, "html.parser")
        offers = []
        cards = soup.find_all("div", class_=re.compile(r"job_seen_beacon|resultContent", re.I))
        for card in cards:
            try:
                link = card.find("a", href=re.compile(r"/rc/clk|/pagead/clk|/viewjob"))
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get("href", "")
                url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

                company_el = card.find(attrs={"data-testid": "company-name"}) or \
                             card.find(class_=re.compile(r"company|employer", re.I))
                company = company_el.get_text(strip=True) if company_el else ""

                location_el = card.find(attrs={"data-testid": "text-location"}) or \
                              card.find(class_=re.compile(r"location|companyLocation", re.I))
                location = location_el.get_text(strip=True) if location_el else ""

                date_el = card.find(class_=re.compile(r"date|posted", re.I))
                published = date_el.get_text(strip=True) if date_el else ""

                offers.append(Offer(
                    title=title,
                    company=company,
                    location=location,
                    url=url,
                    source=self.name,
                    published_at=published,
                ))
            except Exception:
                continue
        return offers

    async def get_offer_details(self, offer: Offer, page) -> Offer:
        try:
            await page.goto(offer.url, wait_until="domcontentloaded", timeout=self.config.PLAYWRIGHT_TIMEOUT)
            await page.wait_for_timeout(self.config.PAGE_LOAD_WAIT)
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            desc_el = soup.find(id="jobDescriptionText") or \
                      soup.find(class_=re.compile(r"jobDescription|description", re.I))
            if desc_el:
                offer.description = desc_el.get_text(separator="\n", strip=True)[:3000]

            for tag in soup.find_all(class_=re.compile(r"attribute_snippet|jobDetail", re.I)):
                text = tag.get_text(" ", strip=True).lower()
                if "bac" in text or "master" in text:
                    offer.education_level = tag.get_text(strip=True)
                elif "mois" in text or "durée" in text:
                    offer.duration = tag.get_text(strip=True)
        except Exception as e:
            print(f"[Indeed] Erreur détails {offer.url}: {e}")
        return offer
