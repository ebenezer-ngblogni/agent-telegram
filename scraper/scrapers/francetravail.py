"""
Scraper France Travail (ex-Pôle Emploi) — API officielle publique.

Inscription gratuite sur https://francetravail.io/data/api/offres-emploi
Crée une application → récupère FRANCE_TRAVAIL_CLIENT_ID et FRANCE_TRAVAIL_CLIENT_SECRET.

Note : l'API n'a pas de code typeContrat spécifique pour l'alternance.
Les offres d'alternance sont filtrées via les mots-clés (query contient "alternance").
"""

import asyncio
import random
import httpx

from .base import BaseScraper, Offer


TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
PAGE_SIZE = 50


class FranceTravailScraper(BaseScraper):
    """France Travail — API OAuth2 publique, pas besoin de Playwright."""

    name = "francetravail"

    def __init__(self, config):
        super().__init__(config)
        self._token: str | None = None
        self._auth_failed = False

    async def _get_token(self) -> str:
        client_id = getattr(self.config, "FRANCE_TRAVAIL_CLIENT_ID", "")
        client_secret = getattr(self.config, "FRANCE_TRAVAIL_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise RuntimeError(
                "FRANCE_TRAVAIL_CLIENT_ID / FRANCE_TRAVAIL_CLIENT_SECRET non configurés"
            )
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                TOKEN_URL,
                params={"realm": "/partenaire"},
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "api_offresdemploiv2 o2dsoffre",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
            return self._token

    async def search_offers(self, query: str, location: str, page=None) -> list[Offer]:
        if self._auth_failed:
            return []
        if not self._token:
            try:
                await self._get_token()
            except Exception as e:
                print(f"[FranceTravail] Impossible d'obtenir le token : {e}")
                self._auth_failed = True
                return []

        offers: list[Offer] = []
        for page_num in range(self.config.MAX_PAGES_PER_QUERY):
            start = page_num * PAGE_SIZE
            end = start + PAGE_SIZE - 1
            params = {
                "motsCles": query,
                "range": f"{start}-{end}",
                "sort": "1",  # tri par date
            }
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.get(
                        SEARCH_URL,
                        params=params,
                        headers={
                            "Authorization": f"Bearer {self._token}",
                            "Accept": "application/json",
                        },
                    )
                if resp.status_code == 204:
                    break
                if resp.status_code == 401:
                    await self._get_token()
                    continue
                if resp.status_code not in (200, 206):
                    print(f"[FranceTravail] HTTP {resp.status_code} pour '{query}'")
                    break
                data = resp.json()
                results = data.get("resultats", [])
                if not results:
                    break
                for item in results:
                    offers.append(self._parse_item(item))
                await asyncio.sleep(random.uniform(*self.config.DELAY_BETWEEN_REQUESTS))
            except Exception as e:
                print(f"[FranceTravail] Erreur '{query}' page {page_num}: {e}")
                break

        return offers

    def _parse_item(self, item: dict) -> Offer:
        lieu = item.get("lieuTravail", {})
        formation = item.get("formations", [{}])
        niv = formation[0].get("niveauLibelle", "") if formation else ""
        salaire = item.get("salaire", {}).get("libelle", "")
        duree = item.get("dureeTravailLibelle", "")
        return Offer(
            title=item.get("intitule", ""),
            company=item.get("entreprise", {}).get("nom", ""),
            location=lieu.get("libelle", ""),
            url=item.get("origineOffre", {}).get("urlOrigine", "")
                or f"https://www.francetravail.fr/offres-d-emploi/detail/{item.get('id', '')}",
            source=self.name,
            contract_type=item.get("typeContratLibelle", ""),
            description=item.get("description", "")[:3000],
            education_level=niv,
            duration=duree,
            salary=salaire,
            published_at=item.get("dateCreation", ""),
        )

    async def get_offer_details(self, offer: Offer, page=None) -> Offer:
        return offer
