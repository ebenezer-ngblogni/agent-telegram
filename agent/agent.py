#!/usr/bin/env python3
import os
import re
import json
import asyncio
import subprocess
import shutil
import logging
import tempfile
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from google import genai

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
AUTHORIZED_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
CVS_DIR = os.getenv("CVS_DIR", "/opt/alternance-agent/cvs")
LOG_FILE = os.getenv("LOG_FILE", "/var/log/alternance-agent.log")

CANDIDATE_NAME = os.getenv("CANDIDATE_NAME", "Prénom NOM")
CANDIDATE_PROFILE = os.getenv(
    "CANDIDATE_PROFILE",
    "élève ingénieur informatique, alternance 2 ans",
)
CANDIDATE_STACK = os.getenv(
    "CANDIDATE_STACK",
    "Java, JavaScript, PHP, Python, Flutter/Dart, React, Spring Boot, Laravel, Docker, Git, Linux",
)
CANDIDATE_PITCH = os.getenv(
    "CANDIDATE_PITCH",
    "Élève ingénieur en informatique. Recherche une alternance de 2 ans.",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)

CV_TEMPLATES = {
    "mobile":     "cv_amiltone_mobile.tex",
    "java":       "cv_capgemini_java.tex",
    "devops":     "cv_enedis_devops.tex",
    "web":        "cv_hutchinson_web.tex",
    "web_mobile": "cv_sg_web_mobile.tex",
    "backend":    "cv_credit_agricole_backend.tex",
    "generic":    "cv.tex",
}

pending_offers = {}


def check_relevance(offer_text: str) -> dict:
    prompt = f"""Tu filtres des offres pour {CANDIDATE_NAME}, {CANDIDATE_PROFILE}.
Profil : {CANDIDATE_STACK}. Mobilité France entière.

EXCLUS : organismes de formation qui recrutent pour LEUR propre diplôme (ISCOD, ARINFO, OpenClassrooms employeur), offres hors informatique, arnaques.

Réponds UNIQUEMENT en JSON valide :
{{
  "is_relevant": true/false,
  "reason": "explication courte",
  "job_type": "mobile|java|devops|web|backend|web_mobile|generic",
  "company": "nom entreprise",
  "title": "titre du poste",
  "location": "ville",
  "mobility": "région",
  "key_skills": ["skill1", "skill2", "skill3"]
}}

OFFRE :
{offer_text[:3000]}"""

    try:
        resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        text = resp.text.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        logger.error(f"Relevance check error: {e}")
    return {"is_relevant": False, "reason": "Erreur d'analyse"}


def adapt_cv(offer_text: str, analysis: dict, template_path: str) -> str:
    with open(template_path, "r") as f:
        cv_content = f.read()

    prompt = f"""Tu es expert LaTeX. Adapte ce CV pour l'offre ci-dessous.

RÈGLES ABSOLUES :
1. Modifie UNIQUEMENT : titre sous le nom, section Profil, ordre/contenu des Compétences, mobilité dans Contacts
2. Ne touche PAS aux sections Expériences, Formation, Références, Timeline TikZ
3. Le CV DOIT rester sur 1 page — ne rallonge pas les textes
4. Conserve EXACTEMENT la syntaxe LaTeX sans rien casser
5. Mets en avant les compétences : {", ".join(analysis.get("key_skills", []))}
6. Mobilité à mettre : {analysis.get("mobility", "France entière")}

POSTE : {analysis.get("title", "")} chez {analysis.get("company", "")}

OFFRE :
{offer_text[:2000]}

CV ACTUEL :
{cv_content}

Réponds UNIQUEMENT avec le LaTeX complet, sans balises markdown, sans commentaires."""

    resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    text = resp.text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text


def generate_cover_letter(offer_text: str, analysis: dict) -> str:
    prompt = f"""Génère une lettre de motivation LaTeX pour {CANDIDATE_NAME}.

PROFIL : {CANDIDATE_PITCH}

RÈGLES :
- Pas de tirets em/en dash dans le texte
- Pas de "squad" utilise "équipe"
- 4 paragraphes : accroche, compétences, motivation entreprise, conclusion
- Utilise \\oe{{}} pour le oe dans "coeur"
- Style LaTeX : documentclass article 11pt, marges 2.5cm, police Montserrat, couleur accentcolor RGB 70,80,60

DESTINATAIRE :
Poste : {analysis.get("title", "")}
Entreprise : {analysis.get("company", "")}
Lieu : {analysis.get("location", "")}
Compétences clés : {", ".join(analysis.get("key_skills", []))}

OFFRE :
{offer_text[:2000]}

Réponds UNIQUEMENT avec le LaTeX complet, sans balises markdown."""

    resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    text = resp.text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text


def compile_pdf(content: str, filename: str, work_dir: str) -> str:
    tex_path = os.path.join(work_dir, f"{filename}.tex")
    pdf_path = os.path.join(work_dir, f"{filename}.pdf")

    with open(tex_path, "w") as f:
        f.write(content)

    photo_src = os.path.join(CVS_DIR, "photo.png")
    if os.path.exists(photo_src):
        shutil.copy(photo_src, work_dir)

    for _ in range(2):
        subprocess.run(
            ["xelatex", "-interaction=nonstopmode", tex_path],
            cwd=work_dir, capture_output=True, timeout=60
        )

    if os.path.exists(pdf_path):
        return pdf_path
    raise Exception("Compilation PDF échouée")


async def process_offer(update: Update, context: ContextTypes.DEFAULT_TYPE, offer_text: str):
    chat_id = update.effective_chat.id

    await context.bot.send_message(chat_id, "Analyse de l'offre en cours.")
    analysis = check_relevance(offer_text)

    if not analysis.get("is_relevant"):
        await context.bot.send_message(
            chat_id,
            f"Offre écartée. Raison : {analysis.get('reason', 'non spécifiée')}"
        )
        return

    await context.bot.send_message(
        chat_id,
        f"Offre retenue.\n\n"
        f"Entreprise : {analysis.get('company', 'N/A')}\n"
        f"Poste : {analysis.get('title', 'N/A')}\n"
        f"Lieu : {analysis.get('location', 'N/A')}\n"
        f"Compétences : {', '.join(analysis.get('key_skills', []))}\n\n"
        f"Génération du CV et de la lettre."
    )

    job_type = analysis.get("job_type", "generic")
    template_name = CV_TEMPLATES.get(job_type, CV_TEMPLATES["generic"])
    template_path = os.path.join(CVS_DIR, template_name)
    if not os.path.exists(template_path):
        template_path = os.path.join(CVS_DIR, "cv.tex")

    try:
        adapted_cv = adapt_cv(offer_text, analysis, template_path)
        cover_letter = generate_cover_letter(offer_text, analysis)

        company_safe = re.sub(r"[^a-zA-Z0-9]", "_", analysis.get("company", "entreprise"))[:20]
        work_dir = tempfile.mkdtemp()

        cv_pdf = compile_pdf(adapted_cv, f"cv_{company_safe}", work_dir)
        lettre_pdf = compile_pdf(cover_letter, f"lettre_{company_safe}", work_dir)

        await context.bot.send_message(
            chat_id,
            "Dossier prêt. Réponds OUI pour valider, NON pour ignorer."
        )

        with open(cv_pdf, "rb") as f:
            await context.bot.send_document(chat_id, f, filename=f"CV_{company_safe}.pdf")
        with open(lettre_pdf, "rb") as f:
            await context.bot.send_document(chat_id, f, filename=f"Lettre_{company_safe}.pdf")

        pending_offers[chat_id] = {"analysis": analysis}
        shutil.rmtree(work_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"Error: {e}")
        await context.bot.send_message(chat_id, f"Erreur : {str(e)[:200]}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != AUTHORIZED_CHAT_ID:
        return

    text = update.message.text.strip()

    if text.upper() in ["OUI", "O", "YES"]:
        if AUTHORIZED_CHAT_ID in pending_offers:
            analysis = pending_offers[AUTHORIZED_CHAT_ID]["analysis"]
            await context.bot.send_message(
                AUTHORIZED_CHAT_ID,
                f"Validé. Dossier à envoyer chez {analysis.get('company', '')}.\n"
                f"Les PDFs sont dans ta conversation Telegram."
            )
            del pending_offers[AUTHORIZED_CHAT_ID]
        return

    if text.upper() in ["NON", "N", "NO"]:
        if AUTHORIZED_CHAT_ID in pending_offers:
            await context.bot.send_message(AUTHORIZED_CHAT_ID, "Offre ignorée.")
            del pending_offers[AUTHORIZED_CHAT_ID]
        return

    if len(text) > 80:
        await process_offer(update, context, text)
    else:
        await context.bot.send_message(
            AUTHORIZED_CHAT_ID,
            "Envoie une offre d'alternance (texte complet) pour générer le CV et la lettre adaptés."
        )


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        update.effective_chat.id,
        "Agent CV actif.\n\n"
        "Envoie une offre d'alternance, le bot va :\n"
        "1. Vérifier si elle te convient\n"
        "2. Adapter ton CV\n"
        "3. Générer une lettre de motivation\n"
        "4. Renvoyer les PDF\n\n"
        "Réponds OUI pour valider, NON pour ignorer."
    )


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Agent CV démarré")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
