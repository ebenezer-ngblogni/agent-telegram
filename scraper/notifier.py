import os
import httpx

from scrapers.base import Offer


TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


async def notify_telegram(offers: list[Offer]):
    """Envoie un résumé des nouvelles offres pertinentes via Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Notifier] Variables TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID manquantes.")
        return
    if not offers:
        return

    top = sorted(offers, key=lambda o: o.relevance_score, reverse=True)[:10]

    lines = [f"*{len(offers)} nouvelle(s) offre(s) pertinente(s)*\n"]
    for i, o in enumerate(top, 1):
        score_bar = "🟢" if o.relevance_score >= 80 else "🟡" if o.relevance_score >= 50 else "🔴"
        lines.append(
            f"{score_bar} *{i}. {_esc(o.title)}*\n"
            f"   {_esc(o.company)} — {_esc(o.location)}\n"
            f"   Score : {o.relevance_score}/100 — {_esc(o.relevance_notes)}\n"
            f"   [{_esc(o.source)}]({o.url})\n"
        )

    lines.append("\n_Dis à Claude : \"génère le CV pour l'offre N\" pour créer le dossier._")
    message = "\n".join(lines)

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False,
                },
                timeout=10,
            )
        print(f"[Notifier] Message envoyé à Telegram ({len(top)} offres).")
    except Exception as e:
        print(f"[Notifier] Erreur Telegram : {e}")


def _esc(text: str) -> str:
    """Échappe les caractères spéciaux Markdown Telegram."""
    for ch in ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]:
        text = text.replace(ch, f"\\{ch}")
    return text
