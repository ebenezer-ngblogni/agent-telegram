import asyncio
import random
import re
from urllib.parse import urlencode, quote_plus

from bs4 import BeautifulSoup

from .base import BaseScraper, Offer


class HelloWorkScraper(BaseScraper):
    name = "hellowork"
    BASE_URL = "https://www.hellowork.com"
    SEARCH_URL = "https://www.hellowork.com/fr-fr/emploi/recherche.html"

    async def search_offers(self, query: str, location: str, page) -> list[Offer]:
        offers = []
        for page_num in range(1, self.config.MAX_PAGES_PER_QUERY + 1):
            params = {
                "k": query,
                "d": location if location != "France" else "",
                "type": "all",
                "ray": "100",
                "p": page_num,
            }
            url = f"{self.SEARCH_URL}?{urlencode(params)}"

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=self.config.PLAYWRIGHT_TIMEOUT)
                await page.wait_for_timeout(self.config.PAGE_LOAD_WAIT)

                html = await page.content()
                page_offers = self._parse_search_results(html)

                if not page_offers:
                    break

                offers.extend(page_offers)
                delay = random.uniform(*self.config.DELAY_BETWEEN_REQUESTS)
                await asyncio.sleep(delay)

            except Exception as e:
                print(f"[HelloWork] Erreur page {page_num} pour '{query}': {e}")
                break

        return offers

    def _parse_search_results(self, html: str) -> list[Offer]:
        soup = BeautifulSoup(html, "html.parser")
        offers = []

        # HelloWork utilise des liens avec data-cy="offerTitle" et aria-label riche
        links = soup.find_all("a", attrs={"data-cy": "offerTitle"})
        if not links:
            # Fallback : tout lien vers /emplois/<id>.html
            links = soup.find_all("a", href=re.compile(r"/emplois/\d+\.html"))

        seen_urls: set[str] = set()
        for link in links:
            try:
                href = link.get("href", "")
                url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # L'aria-label contient "titre à lieu, chez entreprise, pour contrat"
                aria = link.get("aria-label", "")

                # Titre — dans le premier <p> de l'<h3>
                h3 = link.find("h3")
                ps = h3.find_all("p") if h3 else []
                title = ps[0].get_text(strip=True) if ps else link.get_text(strip=True)
                company = ps[1].get_text(strip=True) if len(ps) > 1 else ""

                # Localisation — dans l'aria-label : "à <lieu>,"
                loc_match = re.search(r"\bà ([^,]+),", aria)
                location = loc_match.group(1).strip() if loc_match else ""

                contract_match = re.search(r"pour (?:un|une) ([^,]+),", aria)
                contract = contract_match.group(1).strip() if contract_match else ""

                # Date — chercher le <time> le plus proche
                card_root = link.parent
                for _ in range(5):
                    if card_root is None:
                        break
                    time_el = card_root.find("time")
                    if time_el:
                        break
                    card_root = card_root.parent
                published = time_el.get("datetime", time_el.get_text(strip=True)) if time_el else ""

                offers.append(Offer(
                    title=title,
                    company=company,
                    location=location,
                    url=url,
                    source=self.name,
                    contract_type=contract,
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
            return self._parse_offer_page(offer, html)
        except Exception as e:
            print(f"[HelloWork] Erreur détails {offer.url}: {e}")
            return offer

    def _parse_offer_page(self, offer: Offer, html: str) -> Offer:
        soup = BeautifulSoup(html, "html.parser")

        desc_el = (
            soup.find("div", class_=re.compile(r"description|job-detail|content", re.I))
            or soup.find("section", class_=re.compile(r"description|mission", re.I))
        )
        if desc_el:
            offer.description = desc_el.get_text(separator="\n", strip=True)[:3000]

        # Infos structurées (salaire, niveau, durée, rythme)
        for tag in soup.find_all(class_=re.compile(r"criteria|info|detail|badge|tag", re.I)):
            text = tag.get_text(" ", strip=True).lower()
            if "bac" in text or "master" in text or "licence" in text or "ingénieur" in text:
                offer.education_level = tag.get_text(strip=True)
            elif "mois" in text or "an" in text or "durée" in text:
                offer.duration = tag.get_text(strip=True)
            elif "semaine" in text or "rythme" in text or "alternance" in text:
                offer.rhythm = tag.get_text(strip=True)
            elif "€" in text or "salaire" in text or "rémunération" in text:
                offer.salary = tag.get_text(strip=True)

        return offer
