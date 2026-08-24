import asyncio
import random
import re
import httpx

from bs4 import BeautifulSoup

from .base import BaseScraper, Offer


class ApecScraper(BaseScraper):
    """APEC — utilise l'API JSON publique, pas besoin de Playwright."""

    name = "apec"
    API_URL = "https://www.apec.fr/cms/webservices/rechercheOffre/rechercherOffres"
    OFFER_BASE_URL = "https://www.apec.fr/candidat/recherche-emploi.html/emploi"

    async def search_offers(self, query: str, location: str, page=None) -> list[Offer]:
        offers = []
        for page_num in range(self.config.MAX_PAGES_PER_QUERY):
            payload = {
                "motsCles": query,
                "typeContrat": [215],   # 215 = alternance/apprentissage chez APEC
                "pagination": {"nombreResultatsParPage": 20, "pageCourante": page_num},
                "tris": [{"type": "DATE_PUBLICATION", "ordre": "DESC"}],
            }
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.post(
                        self.API_URL,
                        json=payload,
                        headers={"Content-Type": "application/json", "Accept": "application/json"},
                    )
                if resp.status_code != 200:
                    break
                data = resp.json()
                results = data.get("resultats", [])
                if not results:
                    break
                for item in results:
                    offers.append(self._parse_apec_item(item))
                delay = random.uniform(*self.config.DELAY_BETWEEN_REQUESTS)
                await asyncio.sleep(delay)
            except Exception as e:
                print(f"[APEC] Erreur page {page_num} pour '{query}': {e}")
                break
        return offers

    def _parse_apec_item(self, item: dict) -> Offer:
        offer_id = item.get("numOffre", "")
        url = f"{self.OFFER_BASE_URL}/{offer_id}" if offer_id else ""
        return Offer(
            title=item.get("intitule", ""),
            company=item.get("nomSociete", ""),
            location=item.get("lieuTravail", {}).get("libelle", ""),
            url=url,
            source=self.name,
            contract_type=item.get("typeContrat", {}).get("libelle", ""),
            description=item.get("textOffre", "")[:3000],
            education_level=item.get("niveauFormation", {}).get("libelle", ""),
            duration=item.get("duree", ""),
            salary=item.get("salaireTexte", ""),
            published_at=item.get("datePublication", ""),
        )

    async def get_offer_details(self, offer: Offer, page=None) -> Offer:
        return offer
