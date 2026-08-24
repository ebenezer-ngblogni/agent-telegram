import json
from datetime import datetime
from pathlib import Path

from scrapers.base import Offer


class OfferStorage:
    """Gère la persistance des offres et la déduplication."""

    def __init__(self, new_offers_file: Path, seen_offers_file: Path):
        self.new_offers_file = new_offers_file
        self.seen_offers_file = seen_offers_file
        self._seen_ids: set[str] = self._load_seen_ids()

    def _load_seen_ids(self) -> set[str]:
        if self.seen_offers_file.exists():
            try:
                data = json.loads(self.seen_offers_file.read_text())
                return set(data.get("ids", []))
            except Exception:
                return set()
        return set()

    def _save_seen_ids(self):
        self.seen_offers_file.parent.mkdir(parents=True, exist_ok=True)
        self.seen_offers_file.write_text(
            json.dumps({"ids": list(self._seen_ids)}, ensure_ascii=False, indent=2)
        )

    def filter_new(self, offers: list[Offer]) -> list[Offer]:
        """Retourne uniquement les offres non encore vues."""
        new = [o for o in offers if o.id not in self._seen_ids]
        # Dédup dans le lot courant
        seen_in_batch = set()
        unique_new = []
        for o in new:
            if o.id not in seen_in_batch:
                unique_new.append(o)
                seen_in_batch.add(o.id)
        return unique_new

    def save_new_offers(self, offers: list[Offer]):
        """Sauvegarde les nouvelles offres et met à jour les IDs vus."""
        if not offers:
            return

        existing: list[dict] = []
        if self.new_offers_file.exists():
            try:
                data = json.loads(self.new_offers_file.read_text())
                existing = data.get("offers", [])
            except Exception:
                existing = []

        new_dicts = [o.to_dict() for o in offers]
        all_offers = existing + new_dicts

        self.new_offers_file.parent.mkdir(parents=True, exist_ok=True)
        self.new_offers_file.write_text(
            json.dumps(
                {
                    "updated_at": datetime.now().isoformat(),
                    "total": len(all_offers),
                    "offers": all_offers,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        for o in offers:
            self._seen_ids.add(o.id)
        self._save_seen_ids()

        print(f"[Storage] {len(offers)} nouvelle(s) offre(s) sauvegardée(s). Total : {len(all_offers)}")
