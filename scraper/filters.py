import re
import json

import httpx

from scrapers.base import Offer
import config as cfg


def quick_reject(offer: Offer) -> tuple[bool, str]:
    """
    Rejet rapide sans appel API — vérifie les critères éliminatoires évidents.
    Retourne (True, raison) si l'offre doit être rejetée.
    """
    text = f"{offer.title} {offer.contract_type} {offer.description} {offer.education_level}".lower()

    for keyword in cfg.REJECT_IF_CONTAINS:
        if keyword in text:
            return True, f"Contient '{keyword}'"

    for contract in cfg.REJECT_CONTRACT_TYPES:
        if contract in offer.contract_type.lower():
            return True, f"Type de contrat rejeté : {offer.contract_type}"

    # Durée du contrat : l'alternance ingénieur fait 24 mois (2 ans).
    # France Travail code la durée dans contract_type (ex : "CDD - 12 Mois").
    m = re.search(r"(\d+)\s*mois", offer.contract_type.lower())
    if m and int(m.group(1)) < cfg.MIN_DURATION_MONTHS:
        return True, f"Durée {m.group(1)} mois < {cfg.MIN_DURATION_MONTHS}"

    for rhythm in cfg.REJECT_RHYTHMS:
        if rhythm.lower() in text:
            return True, f"Rythme incompatible : {rhythm}"

    # Pas de mot "alternance" ou "apprentissage" → suspect
    if not re.search(r"altern|apprenti", text):
        return True, "Pas de mention alternance/apprentissage"

    return False, ""


SCORE_BATCH_SIZE = 12  # offres par requête Gemini (éviter timeout / JSON tronqué)


def _score_batch(offers: list[Offer]) -> None:
    """Score un lot d'offres en place via l'API Gemini."""
    offers_text = "\n\n".join(
        f"ID: {o.id}\n"
        f"Titre: {o.title}\n"
        f"Entreprise: {o.company}\n"
        f"Lieu: {o.location}\n"
        f"Niveau: {o.education_level}\n"
        f"Durée: {o.duration}\n"
        f"Rythme: {o.rhythm}\n"
        f"Description (extrait): {o.description[:600]}"
        for o in offers
    )

    prompt = f"""Tu es un assistant de recherche d'emploi pour ce profil candidat :
{cfg.PROFILE['description']}
Contrat recherché : alternance 2 ans, démarrage septembre 2026, niveau ingénieur (Bac+5).
Rythme EILCO : 2 semaines école / 2 semaines entreprise (incompatible avec 1 sem/3 sem ou 1j/4j).

Voici {len(offers)} offres à évaluer :

{offers_text}

Pour chaque offre, réponds UNIQUEMENT en JSON valide, tableau d'objets :
[
  {{
    "id": "...",
    "score": 0-100,
    "notes": "justification en une phrase courte"
  }},
  ...
]

Critères de score :
- 80-100 : stack aligné, niveau Bac+4/5, alternance 2 ans, rythme compatible ou non précisé
- 50-79 : profil partiellement aligné, quelques écarts mineurs
- 0-49 : niveau trop bas, CDI déguisé, stack sans rapport, rythme incompatible
"""

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{cfg.GEMINI_MODEL}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "maxOutputTokens": 16384,
            # Désactive le "thinking" de Gemini 2.5 (sinon il consomme le
            # budget de sortie et le JSON est tronqué)
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    response = httpx.post(
        url,
        params={"key": cfg.GEMINI_API_KEY},
        json=payload,
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    candidate = data["candidates"][0]
    if candidate.get("finishReason") == "MAX_TOKENS":
        print("[Filter]   ⚠ Réponse tronquée (MAX_TOKENS) — lot trop gros")
    text = candidate["content"]["parts"][0]["text"]
    # Sécurité : retire d'éventuels fences ```json … ```
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    scores = json.loads(text)
    score_map = {str(s["id"]): s for s in scores}
    for offer in offers:
        if str(offer.id) in score_map:
            offer.relevance_score = score_map[str(offer.id)].get("score", 0)
            offer.relevance_notes = score_map[str(offer.id)].get("notes", "")


def score_offers(offers: list[Offer]) -> list[Offer]:
    """
    Évalue la pertinence des offres via l'API Gemini, par lots.
    Remplit offer.relevance_score (0-100) et offer.relevance_notes.

    Sans clé GEMINI_API_KEY, attribue un score neutre (50) à toutes les
    offres pour qu'elles passent le seuil — mieux vaut sur-notifier que rater.
    """
    if not offers:
        return offers

    if not cfg.GEMINI_API_KEY:
        print("[Filter] Pas de GEMINI_API_KEY — scoring désactivé, score neutre 50.")
        for offer in offers:
            offer.relevance_score = 50
            offer.relevance_notes = "Non scoré (pas de clé Gemini)"
        return offers

    total = len(offers)
    for start in range(0, total, SCORE_BATCH_SIZE):
        batch = offers[start:start + SCORE_BATCH_SIZE]
        num = start // SCORE_BATCH_SIZE + 1
        print(f"[Filter] Lot {num} : {len(batch)} offres ({start + len(batch)}/{total})")
        try:
            _score_batch(batch)
        except Exception as e:
            print(f"[Filter] Erreur Gemini API (lot {num}) : {e}")
            # En cas d'échec, score neutre pour ne pas perdre les offres du lot
            for offer in batch:
                if offer.relevance_score == 0:
                    offer.relevance_score = 50
                    offer.relevance_notes = "Non scoré (erreur API)"

    return offers
