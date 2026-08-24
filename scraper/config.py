from pathlib import Path
import os

# Profil candidat
PROFILE = {
    "name": "Eben Ezer N'GBLOGNI",
    "level": "Bac+5 (Ingénieur en cours)",
    "contract": "alternance",
    "duration_months": 24,
    "start": "septembre 2026",
    "description": (
        "Élève ingénieur EILCO, major de promotion (17,17/20). "
        "Master 1 IA et Big Data (Très Bien). "
        "Expérience de développement fullstack en production (Ok2gether, Manobi Africa). "
        "Stack principal : Java, Python, React, Spring Boot, SQL, Docker, Linux."
    ),
}

# Requêtes de recherche par site
SEARCH_QUERIES = [
    "alternance développeur Java",
    "alternance développeur fullstack",
    "alternance développeur Python",
    "alternance développeur React",
    "alternance ingénieur logiciel",
    "alternance chef de projet IT",
    "alternance développeur Spring Boot",
    "alternance développeur backend",
]

LOCATIONS = ["France"]

# Filtres automatiques (rejet direct, avant appel LLM)
# "cdd" retiré : France Travail code les alternances comme "CDD - 24 Mois"
# Les vrais CDD sont filtrés par l'absence de "alternance/apprentissage" dans le texte
REJECT_CONTRACT_TYPES = ["cdi", "stage", "freelance", "vie"]

REJECT_IF_CONTAINS = [
    "bac+2", "bac+3", "bts", "dut", "bac +2", "bac +3",
    "permis b obligatoire", "permis obligatoire",
    "5 ans d'expérience", "10 ans d'expérience",
]

REJECT_RHYTHMS = [
    "1 semaine école / 3 semaines",
    "1 sem. école / 3 sem.",
    "1j/4j",
]

MIN_DURATION_MONTHS = 24

# Credentials France Travail API (https://francetravail.io/data/api/offres-emploi)
FRANCE_TRAVAIL_CLIENT_ID = os.getenv("FRANCE_TRAVAIL_CLIENT_ID", "")
FRANCE_TRAVAIL_CLIENT_SECRET = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET", "")

# Scoring de pertinence — Gemini API (niveau gratuit suffisant)
# Clé : https://aistudio.google.com/app/apikey
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Seuil de pertinence : seules les offres avec un score >= sont notifiées.
# 75 = uniquement les bons matchs. Baisser à 60 pour élargir, monter à 85 pour resserrer.
MIN_RELEVANCE_SCORE = int(os.getenv("MIN_RELEVANCE_SCORE", "75"))

# Fichiers de sortie (montés en volume Docker → accessible depuis /home/eben/Bureau/CV/)
DATA_DIR = Path("/data")
NEW_OFFERS_FILE = DATA_DIR / "offres_nouvelles.json"
SEEN_OFFERS_FILE = DATA_DIR / "offres_vues.json"

# Paramètres Playwright
PLAYWRIGHT_TIMEOUT = 30_000       # ms
PAGE_LOAD_WAIT = 2_000            # ms après navigation
DELAY_BETWEEN_REQUESTS = (2, 5)   # secondes (min, max) — anti-ban
MAX_PAGES_PER_QUERY = 5           # pages de résultats max par requête
