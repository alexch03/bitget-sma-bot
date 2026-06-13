# Setup

> [🇬🇧 English version](setup.en.md)

## Prérequis

- Python 3.11 ou supérieur
- Un compte Bitget (uniquement si on veut le mode `demo` ou `live`)

## Installation

### En 1 clic (recommandé)

**Windows** :
1. Double-clique sur `install.bat`
2. Édite `.env` avec tes clés Bitget
3. Double-clique sur `start_web.bat` pour ouvrir le dashboard

**Linux / macOS** :
```bash
chmod +x *.sh
./install.sh
./start_web.sh
```

### En manuel

```bash
git clone https://github.com/alexch03/bitget-sma-bot
cd bitget-sma-bot

python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # puis édite avec tes clés
```

## Clés API Bitget

Nécessaires uniquement pour les modes `demo` et `live`. Le mode `paper` n'a besoin d'aucune clé.

> **Pas encore de compte Bitget ?** Inscris-toi via [le lien de parrainage du projet](https://www.bitget.com/expressly?languageType=0&channelCode=9K5D7K4J&vipCode=9K5D7K4J) (code `9K5D7K4J`).
> Tu reçois le bonus de bienvenue Bitget en cours + des réductions de frais. En échange, le projet touche une part des frais de trading que tu paies à Bitget (zéro surcoût pour toi) — c'est ce qui finance le bot open-source. Pour que l'affiliation soit prise en compte, il faut s'inscrire via ce lien (le code est pré-rempli) et compléter le KYC. La commission ne se déclenche que sur du volume réel, pas en `demo`.

### Pour le mode demo (recommandé pour tester)

1. https://www.bitget.com/asset/demo-trading
2. Active le compte démo (USDT virtuels)
3. Passe en mode démo dans le dashboard Bitget (bouton en haut)
4. Personal Center → API Key Management → **Create Demo API Key**
5. Permissions : Read + Trade + Futures. **Sans** Withdrawal.
6. Note bien la passphrase, elle n'est définissable qu'à la création

### Pour le mode live (ATTENTION)

1. https://www.bitget.com/account/newapi
2. Génère une clé. Permissions : Read + Trade. **Désactive Withdrawal**.
3. Restreins par IP si possible

Dans `.env` :

```env
BITGET_API_KEY=ta_clé
BITGET_API_SECRET=ton_secret
BITGET_API_PASSWORD=ta_passphrase
```

## Telegram (optionnel)

1. Parle à [@BotFather](https://t.me/BotFather), `/newbot`, suis les étapes → token
2. Parle à [@userinfobot](https://t.me/userinfobot) pour récupérer ton chat id
3. Envoie `/start` à ton bot une fois pour qu'il puisse te contacter

Dans `.env` :

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Lancer le bot

```bash
# Bot principal (utilise MODE depuis .env)
python -m src.main

# Dashboard dans un autre terminal
python -m src.web
# → http://127.0.0.1:5000

# Backtest
python examples/run_backtest.py --symbol BTC/USDT:USDT --timeframe 1h --days 180

# Showcase (18 backtests + chart de comparaison)
python examples/showcase.py --days 180

# Grid search
python examples/optimize.py --strategy sma_crossover --symbol BTC/USDT:USDT \
    --timeframe 1h --days 180 --grid '{"fast":[10,20,50],"slow":[50,100,200]}'
```

## Tests

```bash
pytest                              # 54 tests unit + API
python scripts/e2e_full_demo.py     # 9 tests end-to-end sur Bitget demo
python scripts/test_ui_smoke.py     # 6 tests UI Playwright
```

Les tests pytest ne touchent pas au réseau (l'exchange est mocké).

## Avant de passer en live (à lire deux fois)

1. Run le bot au moins une semaine en mode `paper` et review tous les trades générés
2. Passe en mode `demo` (argent virtuel, mêmes endpoints) pour valider que les ordres sont correctement placés
3. Mets `MODE=live` et `CONFIRM_LIVE=yes` dans `.env`
4. Utilise un sous-compte Bitget avec une petite balance (~100 USDT) pour le premier run
5. Relis [DISCLAIMER.md](../DISCLAIMER.md) une dernière fois
