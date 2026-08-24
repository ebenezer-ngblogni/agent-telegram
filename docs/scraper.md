# Scraper d'offres d'alternance

## Déploiement sur le VPS

```bash
# 1. Copier le dossier sur le VPS
scp -r scraper/ user@VOTRE_VPS:~/cv_scraper/

# 2. Créer le fichier d'environnement
cp .env.example .env
nano .env   # remplir les clés

# 3. Build et test
docker compose build
docker compose run --rm scraper python main.py --dry-run

# 4. Lancer pour de vrai
docker compose run --rm scraper python main.py

# 5. Planifier avec cron (2x par jour : 8h et 20h)
crontab -e
# Ajouter :
# 0 8,20 * * * cd ~/cv_scraper && docker compose run --rm scraper python main.py >> ~/cv_scraper/scraper.log 2>&1
```

## Flux complet

```
Cron (2x/jour)
  → Scraper (HelloWork + APEC + Indeed)
  → Filtre rapide (rejet bac+2, CDI, rythme incompatible...)
  → Score Claude API (Haiku — peu coûteux)
  → Sauvegarde dans /home/eben/Bureau/CV/offres_nouvelles.json
  → Notification Telegram
```

## Utilisation avec Claude Code

Le fichier `offres_nouvelles.json` est dans `/home/eben/Bureau/CV/`.
Dans Claude Code, dis simplement :

> "Regarde les nouvelles offres"

Claude lit le fichier, présente un tableau, et tu peux demander :

> "Génère le dossier pour l'offre 3"

## Ajouter un nouveau site

1. Créer `scrapers/monsite.py` qui hérite de `BaseScraper`
2. Implémenter `search_offers()` et `get_offer_details()`
3. L'ajouter dans `SCRAPERS` dans `main.py`
