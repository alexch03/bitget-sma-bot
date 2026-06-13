# Disclaimer

> [🇬🇧 English version](DISCLAIMER.en.md)

Ce logiciel est fourni à des **fins éducatives uniquement**. C'est un exemple compact de la façon de construire un bot de trading crypto — rien de plus.

En utilisant ce code, l'utilisateur accepte que :

1. **Aucun conseil financier.** Les auteurs ne sont pas des conseillers financiers, brokers, ou professionnels licenciés. Aucune information de ce repo ne constitue une recommandation d'achat, de vente ou de conservation d'un actif.

2. **Aucune garantie.** Les résultats des backtests ne prédisent pas les performances futures. Les stratégies incluses (SMA crossover, Bollinger breakout, RSI mean-revert) sont des baselines bien connues et délibérément simples. Elles perdent dans de nombreuses conditions de marché.

3. **Tu es responsable de tes fonds.** Si tu mets `MODE=live`, le bot placera de vrais ordres sur ton compte Bitget. Les pertes peuvent dépasser le dépôt initial avec le levier. Les auteurs déclinent toute responsabilité pour les pertes financières.

4. **Teste d'abord en mode paper et demo.** Lance le bot au moins quelques semaines en mode `paper` ou `demo` avant de considérer le `live`. Assure-toi de comprendre chaque ligne de `src/strategies/` et `src/trader.py` avant de passer en réel.

5. **Clés API.** Ne partage jamais ton fichier `.env`, ne le commit jamais dans git, et donne à ta clé Bitget les permissions minimales nécessaires. **Désactive les retraits** sur toute clé utilisée par ce bot.

6. **Usage légal.** Le trading de dérivés est réglementé dans de nombreuses juridictions et interdit aux particuliers dans certaines. C'est ta responsabilité de connaître et de respecter ta loi locale.

Si l'un des points ci-dessus n'est pas acceptable pour toi, n'utilise pas ce logiciel.
