<div align="center">

# bitget-sma-bot

**Bot de trading Bitget USDT-M open-source. Stratégies modulables, dashboard de contrôle, modes paper / demo / live.**

![License](https://img.shields.io/badge/license-MIT-blue) ![Python](https://img.shields.io/badge/python-3.11+-blue) ![Tests](https://img.shields.io/badge/tests-54_passing-success) ![Bitget](https://img.shields.io/badge/exchange-Bitget-orange) ![Strategies](https://img.shields.io/badge/strategies-3-purple) ![Status](https://img.shields.io/badge/status-stable-green)

[🇬🇧 English](README.en.md) · [Installation](INSTALL.md) · [Documentation](docs/) · [Disclaimer](DISCLAIMER.md)

![Dashboard de contrôle](docs/images/web-ui.png)

</div>

---

## Pourquoi ce projet

La plupart des bots de trading sont soit des boîtes noires payantes, soit des scripts de quelques centaines de lignes impossibles à hacker. **bitget-sma-bot** est volontairement petit (~2 000 lignes Python), lisible en une soirée, et taillé pour servir de **point de départ solide** :

- ✅ 3 stratégies pluggables (SMA crossover, Bollinger breakout, RSI mean-revert)
- ✅ 4 modes d'exécution : `paper` (simulé), `dry` (logs only), `demo` (compte Bitget virtuel), `live` (argent réel)
- ✅ Dashboard de contrôle complet : démarrer / arrêter le bot, ajuster la stratégie, voir le PnL en temps réel — **zéro ligne de code à toucher**
- ✅ Backtester intégré + script d'optimisation par grid search
- ✅ Alertes Telegram, stop-loss, take-profit, gestion du risque par % du capital
- ✅ Testé end-to-end sur Bitget demo : ouverture / fermeture d'ordres réels, suivi des positions, vérification du PnL

---

## Aperçu rapide

| Composant | Détails |
|---|---|
| **Stratégies** | SMA crossover, Bollinger breakout, RSI mean-revert — toutes héritent de `Strategy(ABC)`. Ajouter la sienne = 1 fichier |
| **Modes** | `paper` (pas d'API key), `dry` (logs), `demo` (vrais ordres sur compte virtuel Bitget via header `paptrading: 1`), `live` |
| **Risk** | % du capital par trade, stop-loss et take-profit en % d'entrée, vérifiés à chaque tick |
| **Notifications** | Telegram à chaque entrée / sortie / erreur (optionnel) |
| **Backtests** | Moteur `backtrader` (classique) + moteur léger pour grid search rapide |
| **Tests** | 54 tests pytest + 9 tests end-to-end sur Bitget demo + 6 tests UI (Playwright) |

---

## Démarrage en 1 clic

**Windows** : double-clique `install.bat`, édite `.env`, double-clique `start.bat` (le bot) ou `start_web.bat` (le dashboard).

**Linux / macOS** :
```bash
chmod +x *.sh
./install.sh
./start_web.sh    # dashboard sur :5000
```

Puis ouvre **http://localhost:5000** et clique sur **Start Bot**.

---

## Le dashboard de contrôle

Tout se passe ici. Pas besoin de toucher au code.

- **Hero status** : badge RUNNING / PAUSED / STOPPED, uptime, boutons Start / Stop / Pause / Restart
- **5 stat cards** : balance, position, PnL non réalisé, dernier prix, dernier signal
- **Chart TradingView** : bougies + SMA fast / slow + ligne d'entrée. Sélecteur symbol + timeframe indépendant du bot (pour regarder l'ETH pendant que le bot trade le BTC)
- **Courbe d'équité** reconstruite à partir des trades passés
- **Activity log** : stdout du bot en live, polling toutes les 4 secondes
- **3 panneaux de config** : Strategy (avec switch SMA / Bollinger / RSI + params dynamiques), Risk (RPCT, SL, TP), Mode & Alerts (paper / dry / demo / live + Telegram)
- **Bouton Force close** : ferme la position courante au prochain tick (utilise `reduceOnly` côté exchange)

---

## Architecture

![Architecture](docs/images/architecture.svg)

Voir [docs/architecture.md](docs/architecture.md) pour le détail.

---

## Résultats des backtests

Conditions : 180 jours de données réelles Bitget, 1 000 USDT de départ, 2 % de risque par trade, SL 3 %, TP 6 %, commission 0.06 %. Reproductible avec :

```bash
python examples/showcase.py --days 180
```

### Meilleures configurations par paire et timeframe

| Symbole | TF | Stratégie | Trades | Win % | Return | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| **ETH** | 1d | Bollinger 20/2 | 9 | **66.7 %** | **+0.56 %** | 0.40 % | **+1.38** |
| ETH | 4h | RSI 14 30/70 | 52 | **57.7 %** | **+0.85 %** | 0.44 % | **+0.63** |
| ETH | 1h | SMA 20/50 | 41 | 43.9 % | +0.51 % | 0.63 % | +0.24 |
| BTC | 4h | RSI 14 30/70 | 49 | **59.2 %** | **+0.47 %** | 0.35 % | **+0.43** |
| BTC | 1h | SMA 20/50 | 35 | 42.9 % | +0.32 % | 0.46 % | +0.19 |
| BTC | 1d | Bollinger 20/2 | 7 | 42.9 % | +0.20 % | 0.34 % | +0.66 |

Grid complet dans `examples/results/showcase/summary.csv`.

### Préservation du capital pendant un crash de 30 %

Sur la même fenêtre, BTC est passé de ~91 k$ à ~63 k$ (-30 %). Le buy-and-hold tombe à ~700 USDT. Les trois stratégies tiennent la ligne autour de 1 000 USDT.

![Comparaison BTC 4h](examples/results/showcase/comparison_BTC_4h.png)

Le bot ne fait pas fortune en bull market. Il **évite les gros mouvements baissiers**. C'est le compromis classique d'un système systématique.

---

## Stratégies disponibles

| Nom | Module | Paramètres | Idée |
|---|---|---|---|
| `sma_crossover` | [src/strategies/sma_crossover.py](src/strategies/sma_crossover.py) | `fast`, `slow` | Long quand la SMA rapide croise au-dessus de la lente, short à l'inverse. |
| `bollinger` | [src/strategies/bollinger.py](src/strategies/bollinger.py) | `period`, `std` | Long sur breakout au-dessus de la bande haute, short sur le breakout bas. |
| `rsi_mean_revert` | [src/strategies/rsi_mean_revert.py](src/strategies/rsi_mean_revert.py) | `period`, `oversold`, `overbought` | Long quand le RSI rebondit depuis l'oversold, short quand il chute depuis l'overbought. |

Ajouter sa propre stratégie = créer un fichier dans `src/strategies/`, hériter de `Strategy`, l'enregistrer dans `__init__.py::STRATEGIES`. Le trader et l'optimiseur la prennent automatiquement.

```python
# src/strategies/ma_strategie.py
from .base import Strategy, Decision

class MaStrategie(Strategy):
    name = "ma_strategie"
    def __init__(self, lookback=14):
        self.lookback = lookback
    def warmup(self) -> int:
        return self.lookback + 1
    def signal(self, df) -> Decision:
        # ta règle ici
        return Decision("flat", "pas encore implémenté")
```

---

## Mode demo Bitget (recommandé avant le live)

Bitget propose un compte démo avec argent virtuel. Le bot supporte ce mode via le header `paptrading: 1` (voir [doc officielle Bitget](https://www.bitget.com/api-doc/common/demotrading/restapi)).

> 🎁 **Pas encore de compte Bitget ?** Inscris-toi via [le lien de parrainage du projet](https://www.bitget.com/expressly?languageType=0&channelCode=9K5D7K4J&vipCode=9K5D7K4J) (code `9K5D7K4J`).
>
> **Ce que tu gagnes** : le bonus de bienvenue Bitget en cours + des réductions de frais (le montant est fixé par Bitget, affiché sur la page d'inscription).
> **Ce que le projet gagne** : une part des frais de trading que tu paies à Bitget (sans surcoût pour toi). C'est ce qui permet au bot de rester gratuit et open-source — full disclosure.
> **Pour que l'affiliation soit prise en compte** : inscription via ce lien (le code est pré-rempli), KYC complété. La commission ne se déclenche que sur du volume réel, pas en `demo`.

1. https://www.bitget.com/asset/demo-trading — activer le compte démo
2. Passer en mode démo dans le dashboard Bitget (en haut)
3. Personal Center → API Key Management → **Create Demo API Key** (clés séparées du live)
4. Permissions : Read + Trade + Futures. **Pas** Withdrawal.
5. Mettre les valeurs dans `.env` :
   ```env
   BITGET_API_KEY=...
   BITGET_API_SECRET=...
   BITGET_API_PASSWORD=...
   MODE=demo
   ```
6. Vérifier que tout fonctionne avant de lancer le bot :
   ```bash
   python scripts/test_demo_connection.py
   ```

---

## Tests

```bash
pytest                                        # 54 tests, ~2 min
python scripts/e2e_full_demo.py               # 9 tests end-to-end sur Bitget demo
python scripts/test_ui_smoke.py               # 6 tests UI Playwright
```

Couverture :
- **Unit** : indicateurs, stratégies, trader (paper / dry / demo / live), SL / TP, registry
- **API contract** : tous les endpoints Flask + validation des entrées
- **E2E exchange** : vrais ordres market sur Bitget démo, vérification des positions, PnL accounting, edge cases
- **UI smoke** : Playwright headless, clic flow Start / Stop, dropdowns, erreurs JS

---

## Stack technique

| Couche | Choix |
|---|---|
| Langage | Python 3.11+ |
| Connexion exchange | [ccxt](https://github.com/ccxt/ccxt) (multi-exchange, on utilise Bitget) |
| Backtests | [backtrader](https://www.backtrader.com/) + moteur interne léger |
| Notifications | [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v20+ |
| Dashboard | Flask + Tailwind CSS (CDN) + [lightweight-charts](https://github.com/tradingview/lightweight-charts) |
| Tests | pytest + Playwright |
| Conteneurisation | Dockerfile + docker-compose |

---

## Structure du projet

```
src/
  config.py              Chargement .env + validation des modes / stratégies
  exchange.py            Wrapper ccxt Bitget (gère le header paptrading en mode demo)
  indicators.py          SMA, EMA, RSI, Bollinger bands
  strategies/            Framework pluggable
    base.py              Strategy(ABC), Decision, Signal
    sma_crossover.py     Stratégie SMA
    bollinger.py         Stratégie Bollinger
    rsi_mean_revert.py   Stratégie RSI
    __init__.py          Registry + factory make_strategy()
  trader.py              Boucle principale : check SL/TP, signal, paper/demo/live
  backtest.py            Moteur backtrader
  simple_backtest.py     Moteur léger pour grid search
  telegram_notifier.py   Client Telegram async
  web.py                 Dashboard Flask
  main.py                Point d'entrée du bot

examples/
  run_backtest.py        Backtest backtrader
  optimize.py            Grid search sur params
  showcase.py            18 backtests + graphique de comparaison

scripts/
  test_demo_connection.py   Smoke test Bitget demo
  e2e_full_demo.py          Suite end-to-end de 9 tests
  test_ui_smoke.py          Tests UI Playwright
  take_screenshots.py       Capture du dashboard

tests/                  54 tests pytest

docs/                   Architecture, stratégies, setup
```

---

## Disclaimer

Outil pédagogique. **N'utilise pas le mode `live` avec de l'argent que tu n'es pas prêt à perdre.** Le trading de futures avec levier peut vider un compte en quelques minutes. Lis [DISCLAIMER.md](DISCLAIMER.md) avant tout.

---

## Licence

[MIT](LICENSE).

---

<div align="center">

**Si le projet t'a été utile, mets-lui une ⭐ — ça aide d'autres devs à le découvrir.**

</div>
