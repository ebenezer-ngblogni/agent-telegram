from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any
import hashlib

try:
    from playwright.async_api import Page as PlaywrightPage
except ImportError:
    PlaywrightPage = Any


@dataclass
class Offer:
    title: str
    company: str
    location: str
    url: str
    source: str
    description: str = ""
    contract_type: str = ""
    education_level: str = ""
    duration: str = ""
    rhythm: str = ""
    salary: str = ""
    published_at: str = ""
    # Rempli par le filtre LLM après scraping
    relevance_score: int = 0
    relevance_notes: str = ""
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(self.url.encode()).hexdigest()

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @staticmethod
    def from_dict(d: dict) -> "Offer":
        return Offer(**{k: v for k, v in d.items() if k in Offer.__dataclass_fields__})


class BaseScraper(ABC):
    """Classe de base pour tous les scrapers."""

    name: str = "base"

    def __init__(self, config):
        self.config = config

    @abstractmethod
    async def search_offers(self, query: str, location: str, page: Optional[PlaywrightPage] = None) -> list[Offer]:
        """Retourne une liste d'offres pour une requête donnée."""
        ...

    @abstractmethod
    async def get_offer_details(self, offer: Offer, page: Optional[PlaywrightPage] = None) -> Offer:
        """Enrichit une offre avec les détails de sa page dédiée."""
        ...
