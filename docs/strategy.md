# Stratégies

> [🇬🇧 English version](strategy.en.md)

Le bot fournit trois stratégies, toutes héritant de `Strategy(ABC)` (voir [`src/strategies/base.py`](../src/strategies/base.py)). Chacune implémente une méthode `signal(df) -> Decision` qui renvoie `long`, `short` ou `flat`.

## 1. SMA Crossover (`sma_crossover`)

Le grand classique du trend-following à deux moyennes mobiles.

**Règles :**

Soit `f` la SMA rapide (par défaut 20) et `s` la SMA lente (par défaut 50), toutes deux calculées sur les prix de clôture.

- **Long** quand `f` croise au-dessus de `s` (le signe de `f - s` passe de ≤ 0 à > 0).
- **Short** quand `f` croise au-dessous de `s`.
- **Sortie** sur le signal inverse. Pas de stop-loss ni take-profit dans la règle, ceux-ci sont gérés au niveau du `Trader`.

**Quand elle marche bien :**
- Marchés tendanciels avec peu de whipsaw
- Timeframes hautes (4h, 1d) où le ratio signal/bruit est meilleur

**Quand elle perd :**
- Marchés range ou choppy : le bot flip constamment et brûle les frais
- Instruments à fort levier où le petit edge par trade est mangé par le funding

## 2. Bollinger Breakout (`bollinger`)

Stratégie de **breakout** basée sur les bandes de Bollinger.

**Règles :**

Soit `period` (par défaut 20) la longueur de la bande, et `std` (par défaut 2.0) le multiplicateur d'écart-type.

- Bande haute = SMA(close, period) + std × σ(close, period)
- Bande basse = SMA(close, period) - std × σ(close, period)

- **Long** quand le prix de clôture casse au-dessus de la bande haute (et était dedans ou en-dessous au bar précédent).
- **Short** quand le prix de clôture casse au-dessous de la bande basse.
- **Sortie** sur le signal opposé.

**Quand elle marche bien :**
- Marchés avec faux range puis explosion (compression suivie d'expansion)
- Cryptos qui restent latérales avant un mouvement brutal

**Quand elle perd :**
- Vraies plages serrées où le prix revient toujours dans les bandes
- Marchés en tendance fluide sans phase de compression visible

## 3. RSI Mean Revert (`rsi_mean_revert`)

Stratégie **contrarienne** sur RSI.

**Règles :**

Soit `period` (par défaut 14), `oversold` (par défaut 30) et `overbought` (par défaut 70).

- **Long** quand le RSI rebondit au-dessus du seuil oversold (croise de bas en haut le 30).
- **Short** quand le RSI chute sous le seuil overbought (croise de haut en bas le 70).
- **Sortie** sur le signal opposé.

**Quand elle marche bien :**
- Marchés range qui oscillent autour d'une moyenne
- Timeframes 4h où la respiration du marché est nette
- ETH sur 4h donne le meilleur Sharpe du backtest showcase (+0.63)

**Quand elle perd :**
- Tendances fortes où le RSI reste collé à l'extrême sans rebondir
- Daily où le signal est trop lent

## Récapitulatif des sweet spots

D'après le backtest showcase sur 180 jours :

| Stratégie | Sweet spot | Pourquoi |
|---|---|---|
| SMA crossover | 1h | Suffisamment de bougies pour confirmer un cross sans tomber dans le bruit |
| Bollinger breakout | 1d | Volatilité plus structurée, breakouts plus rares mais plus fiables |
| RSI mean revert | 4h | Cycles court à moyen terme, le RSI a le temps de respirer |

## Ajouter sa propre stratégie

```python
# src/strategies/ma_strategie.py
import pandas as pd
from .base import Strategy, Decision


class MaStrategie(Strategy):
    name = "ma_strategie"

    def __init__(self, lookback: int = 20, threshold: float = 0.02):
        self.lookback = lookback
        self.threshold = threshold

    def warmup(self) -> int:
        """Nombre minimum de bougies nécessaires avant que signal() puisse retourner autre chose que flat."""
        return self.lookback + 1

    def signal(self, df: pd.DataFrame) -> Decision:
        if len(df) < self.warmup():
            return Decision("flat", "pas assez d'historique")

        # Exemple : long si la dernière clôture est X% au-dessus de la moyenne mobile
        closes = df["close"]
        ma = closes.tail(self.lookback).mean()
        last = closes.iloc[-1]
        delta = (last - ma) / ma

        if delta > self.threshold:
            return Decision("long", f"prix {delta * 100:.2f}% au-dessus de MA{self.lookback}")
        if delta < -self.threshold:
            return Decision("short", f"prix {delta * 100:.2f}% au-dessous de MA{self.lookback}")
        return Decision("flat", "dans la zone neutre")
```

Puis enregistrer la stratégie dans le registry :

```python
# src/strategies/__init__.py
from .ma_strategie import MaStrategie

STRATEGIES = {
    "sma_crossover": SMACrossover,
    "bollinger": BollingerBreakout,
    "rsi_mean_revert": RSIMeanRevert,
    "ma_strategie": MaStrategie,  # nouvelle entrée
}
```

À partir de là :
- Le dashboard l'affichera automatiquement dans le sélecteur
- L'optimiseur (`examples/optimize.py --strategy ma_strategie`) peut grid-searcher ses params
- Le trader peut la charger via `STRATEGY=ma_strategie` dans `.env`

## Gestion du risque (au niveau du trader, pas de la stratégie)

Le SL / TP / sizing sont gérés au niveau du `Trader`, pas dans la stratégie elle-même. Cela évite de dupliquer ces règles dans chaque stratégie :

- **`RISK_PCT`** : fraction du capital risquée par trade. La taille du trade est calculée comme `notional = balance × RISK_PCT / 100`.
- **`STOP_LOSS_PCT`** : sortie automatique si le prix bouge X% contre la position (0 = désactivé).
- **`TAKE_PROFIT_PCT`** : sortie automatique si le prix bouge X% en faveur de la position (0 = désactivé).

Ces vérifications sont faites localement à chaque tick. **Aucun ordre stop n'est placé côté exchange.** Si le bot est arrêté quand le prix bouge, aucune sortie n'a lieu — c'est une limite à connaître. Pour le mode `live`, prévoir un broker-side stop est l'évolution naturelle.
