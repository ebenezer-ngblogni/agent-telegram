"""
Point d'entrée du scraper.

Usage :
    python main.py                  # scrape tout
    python main.py --dry-run        # sans sauvegarder ni notifier
    python main.py --sites hellowork francetravail
"""

import argparse
import asyncio
import sys

import config as cfg
from scrapers.base import Offer
from scrapers.hellowork import HelloWorkScraper
from scrapers.francetravail import FranceTravailScraper
from scrapers.indeed import IndeedScraper
from storage import OfferStorage
from filters import quick_reject, score_offers
from notifier import notify_telegram


SCRAPERS = {
    "hellowork": HelloWorkScraper,
    "francetravail": FranceTravailScraper,
    "indeed": IndeedScraper,
}

PLAYWRIGHT_SITES = {"hellowork", "indeed"}
API_SITES = {"francetravail"}


async def run(sites: list[str], dry_run: bool):
    storage = OfferStorage(cfg.NEW_OFFERS_FILE, cfg.SEEN_OFFERS_FILE)
    all_raw: list[Offer] = []

    needs_browser = any(s in PLAYWRIGHT_SITES for s in sites)

    async def _scrape(page=None):
        for site_name in sites:
            scraper_cls = SCRAPERS.get(site_name)
            if not scraper_cls:
                print(f"[Main] Site inconnu : {site_name}")
                continue

            scraper = scraper_cls(cfg)
            print(f"\n[{site_name.upper()}] Démarrage...")

            for query in cfg.SEARCH_QUERIES:
                for location in cfg.LOCATIONS:
                    print(f"  → '{query}' / {location}")
                    try:
                        offers = await scraper.search_offers(
                            query, location,
                            page=(page if site_name in PLAYWRIGHT_SITES else None),
                        )
                        print(f"     {len(offers)} offres trouvées")
                        all_raw.extend(offers)
                    except Exception as e:
                        print(f"     Erreur : {e}")

    if needs_browser:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="fr-FR",
            )
            page = await context.new_page()
            await _scrape(page)
            await browser.close()
    else:
        await _scrape()

    seen_urls: set[str] = set()
    unique_offers: list[Offer] = []
    for o in all_raw:
        if o.url not in seen_urls:
            unique_offers.append(o)
            seen_urls.add(o.url)
    print(f"\n[Main] {len(unique_offers)} offres uniques (avant filtre vu/pas vu)")

    new_offers = storage.filter_new(unique_offers)
    print(f"[Main] {len(new_offers)} offres nouvelles (jamais vues)")

    if not new_offers:
        print("[Main] Rien de nouveau. Fin.")
        return

    kept: list[Offer] = []
    for offer in new_offers:
        rejected, reason = quick_reject(offer)
        if rejected:
            print(f"  ✗ Rejeté ({reason}) : {offer.title} — {offer.company}")
        else:
            kept.append(offer)
    print(f"[Main] {len(kept)} offres après filtre rapide")

    print("[Main] Évaluation par Gemini API...")
    scored = score_offers(kept)

    seuil = cfg.MIN_RELEVANCE_SCORE
    relevant = [o for o in scored if o.relevance_score >= seuil]
    print(f"[Main] {len(relevant)} offres pertinentes (score ≥ {seuil})")

    if dry_run:
        print("\n[DRY RUN] Résultats (non sauvegardés) :")
        for o in sorted(relevant, key=lambda x: x.relevance_score, reverse=True):
            print(f"  [{o.relevance_score:3d}] {o.title} — {o.company} ({o.location})")
            print(f"       {o.url}")
            if o.relevance_notes:
                print(f"       {o.relevance_notes}")
        return

    storage.save_new_offers(relevant)

    await notify_telegram(relevant)
    print("[Main] Terminé.")


def main():
    parser = argparse.ArgumentParser(description="Scraper d'offres d'alternance")
    parser.add_argument("--sites", nargs="+", default=list(SCRAPERS.keys()),
                        choices=list(SCRAPERS.keys()), help="Sites à scraper")
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche les résultats sans sauvegarder ni notifier")
    args = parser.parse_args()

    asyncio.run(run(args.sites, args.dry_run))


if __name__ == "__main__":
    main()
