# Agent Telegram — candidatures d'alternance

Deux briques autonomes qui tournent sur un VPS et se rejoignent sur Telegram :
un **bot** qui transforme une offre d'emploi en CV et lettre de motivation compilés
en PDF, et un **scraper** qui va chercher les offres tout seul deux fois par jour.

## Le bot (`agent/`)

On lui colle le texte d'une offre dans Telegram. Il répond avec deux PDF.

```
Offre collée dans Telegram
  └─ Gemini 2.5 Flash — pertinence + extraction (entreprise, poste, lieu, stack)
       ├─ hors sujet ──────────────────────────► rejet motivé
       └─ pertinente
            ├─ choix du template LaTeX selon le job_type détecté
            ├─ Gemini réécrit titre / profil / compétences (le reste est figé)
            ├─ Gemini rédige la lettre
            ├─ xelatex ×2 (la 2e passe résout les références TikZ)
            └─ les 2 PDF repartent sur Telegram → validation OUI / NON
```

Sept templates LaTeX couvrent les familles de postes (`java`, `devops`, `mobile`,
`web`, `web_mobile`, `backend`, `generic`). Le modèle choisit lequel charger, puis
n'a le droit de toucher qu'au titre, au profil, aux compétences et à la mobilité :
expériences, formation et timeline TikZ sont hors de sa portée, pour que le CV
tienne sur une page et que le LaTeX ne casse pas.

Le bot ne répond qu'à un seul `TELEGRAM_CHAT_ID`, tout autre expéditeur est ignoré.

## Le scraper (`scraper/`)

```
cron 2×/jour
  └─ HelloWork (Playwright) + France Travail (API OAuth2)
       ├─ déduplication sur les IDs déjà vus (storage.py)
       ├─ rejet rapide sans appel LLM : type de contrat, mots-clés, durée
       ├─ scoring Gemini par lot, seuil à 75/100
       └─ digest Telegram des 10 meilleures
```

Le rejet rapide passe avant le LLM : filtrer sur le type de contrat et la durée
coûte zéro token et élimine la majeure partie du bruit. Un piège rencontré en
route : France Travail encode les alternances en `"CDD - 24 Mois"`, donc exclure
« CDD » supprimait aussi les bonnes offres — le tri se fait sur la présence
d'« alternance » ou « apprentissage » dans le texte, pas sur le type de contrat.

`scrapers/indeed.py` et `scrapers/apec.py` sont présents mais pas enregistrés
dans `SCRAPERS` : Indeed bloque l'automatisation, APEC n'a pas été rebranché.

## Installation

```bash
git clone git@github.com:ebenezer-ngblogni/agent-telegram.git
cd agent-telegram
cp .env.example .env   # remplir les clés
```

Le bot a besoin de `xelatex` (`texlive-xetex`, `texlive-fonts-extra`) pour compiler.

```bash
pip install -r agent/requirements.txt
cp deploy/alternance-agent.service /etc/systemd/system/
systemctl enable --now alternance-agent
```

Le scraper tourne en conteneur :

```bash
cd scraper && docker compose run --rm scraper python main.py --dry-run
```

## Configuration

Tout passe par l'environnement, rien n'est en dur dans le code — voir
`.env.example`. `CANDIDATE_NAME`, `CANDIDATE_PROFILE`, `CANDIDATE_STACK` et
`CANDIDATE_PITCH` sont injectés dans les prompts : le dépôt est réutilisable en
changeant ces quatre variables et les templates.

Les templates de `cvs/` sont **anonymisés** (placeholders à la place des
coordonnées et des référents). Les vrais CV restent hors dépôt.

## Stack

Python 3 · python-telegram-bot 22.7 · google-genai (Gemini 2.5 Flash) ·
Playwright · LaTeX/XeLaTeX · Docker · systemd
