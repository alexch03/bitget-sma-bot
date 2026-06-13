# Architecture

> [🇬🇧 English version](architecture.en.md)

Le bot a quatre composants principaux, volontairement découplés.

```
+------------+      +---------+      +-----------+      +----------+
|   config   | ---> | trader  | ---> | exchange  | ---> |  Bitget  |
|  (.env)    |      |  loop   |      |  (ccxt)   |      |   API    |
+------------+      +----+----+      +-----------+      +----------+
                         |
                         v
                  +-------------+      +-----------+
                  |  notifier   | ---> | Telegram  |
                  +-------------+      +-----------+
```

Diagramme complet en SVG : [docs/images/architecture.svg](images/architecture.svg)

## `config.py`

Source unique de vérité au runtime. Lit `.env`, valide, retourne un dataclass `Config`. Le mode `live` impose `CONFIRM_LIVE=yes` — c'est une protection contre les runs accidentels avec de l'argent réel. Idem pour le mode `demo` qui vérifie la présence des clés API.

## `exchange.py`

Wrapper du client `ccxt.bitget`. Les méthodes publiques (`fetch_ohlcv`, `fetch_ohlcv_range`, `fetch_ticker_price`) marchent sans credentials. Les méthodes de trading en ont besoin. C'est le seul endroit qui touche au réseau pour le trading ; tout le reste manipule des DataFrames.

En mode `demo`, le wrapper ajoute explicitement le header `paptrading: 1` aux requêtes (conforme à la doc officielle Bitget) en plus de l'appel `set_sandbox_mode(True)` de ccxt.

## `strategies/`

Framework pluggable. Toute stratégie hérite de `Strategy(ABC)` avec deux méthodes obligatoires :

- `signal(df) -> Decision` : règle pure sur la DataFrame des bougies, retourne `long`, `short` ou `flat` plus une raison textuelle
- `warmup() -> int` : nombre minimum de bougies nécessaires avant que `signal()` puisse retourner autre chose que `flat`

Le module `strategies` expose un registry `STRATEGIES` et une factory `make_strategy(name, **kwargs)`. Le trader et l'optimiseur sont totalement agnostiques de la stratégie utilisée — ils l'appellent par son nom.

Les stratégies ne savent rien des exchanges, de l'argent ou de Telegram. Elles ne connaissent que `pandas`. C'est ce qui les rend testables (les tests unitaires fournissent des DataFrames synthétiques).

## `trader.py`

La boucle principale. Tient le `PaperBook` en mémoire (balance + position), persiste l'état dans `state.json` pour survivre aux redémarrages en mode paper, et dispatche les ordres vers l'exchange en mode `demo` ou `live`.

À chaque tick :

1. Lit `control.json` : si `paused=true`, skip. Si `force_close=true`, ferme la position et reset le flag.
2. Fetch les bougies récentes
3. Si une position est ouverte, vérifie SL / TP. Si déclenché → ferme.
4. Appelle `strategy.signal(df)`. Décide : ouvrir, fermer, ou flipper.
5. Écrit `bot_status.json` (lu par le dashboard pour afficher le dernier signal).

À chaque fermeture (signal, SL, TP, manuel), append une ligne dans `trades.jsonl`.

## `telegram_notifier.py`

Messages fire-and-forget. Si `TELEGRAM_BOT_TOKEN` est vide, le notifier fait silencieusement no-op et le bot continue normalement.

## `web.py`

Dashboard Flask + endpoints API. Le dashboard est une SPA en un seul fichier HTML servie en `render_template_string` avec :

- Tailwind CSS via CDN
- `lightweight-charts` (TradingView) via CDN
- Vanilla JS pour le polling et les actions

Le dashboard gère **le cycle de vie du bot** : un POST `/api/bot/start` spawn `python -m src.main` en `subprocess.Popen` et store son handle. La stdout est lue dans un thread daemon et mise dans un ring buffer pour `/api/logs`.

Les changements de config se font via POST `/api/config` qui écrit dans `.env` (clés en whitelist) et propose un restart du bot.

## Files de runtime (tous gitignored)

| Fichier | Rôle | Écrit par | Lu par |
|---|---|---|---|
| `.env` | Config secrets + paramètres | l'utilisateur ou `/api/config` | `config.py` au démarrage |
| `state.json` | Balance + position (mode paper) | `trader.py` | `trader.py` au redémarrage, dashboard |
| `control.json` | Flags `paused`, `force_close` | dashboard, trader | `trader.py` à chaque tick |
| `bot_status.json` | Dernier tick, signal, prix, position | `trader.py` | dashboard |
| `trades.jsonl` | Historique append-only des trades | `trader._close()` | dashboard, equity curve |
| `runtime.json` | Overrides UI temporaires | dashboard | (réservé pour hot-reload futur) |

## Backtester

Deux moteurs cohabitent :

- **`backtest.py`** : moteur `backtrader` complet, équivalent à ce qu'on trouve dans la doc backtrader. Utilisé par `examples/run_backtest.py`. Génère PNG d'équité + CSV de trades.
- **`simple_backtest.py`** : moteur léger fait main qui itère bar-par-bar. Compatible avec n'importe quelle `Strategy`. Utilisé par `examples/optimize.py` et `examples/showcase.py` parce qu'il est ~10x plus rapide que cerebro pour une grille de 100+ combos.

Les deux supportent SL / TP / commission. Le simple engine est plus simple à lire si l'on veut comprendre l'enchaînement des règles.
