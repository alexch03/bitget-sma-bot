# Installation rapide

[🇬🇧 English](INSTALL.md) | [🇫🇷 Français](INSTALL.fr.md)

Lis [DISCLAIMER.fr.md](DISCLAIMER.fr.md) avant d'utiliser le bot avec du vrai argent.

## Prérequis

- Python 3.11 ou plus récent
- Un compte Bitget avec clés API (uniquement pour les modes `demo` et `live`)

## Windows

1. Double-clique sur **`install.bat`** et attends la fin.
2. Ouvre **`.env`** dans un éditeur de texte et colle tes clés Bitget.
3. Double-clique sur **`start.bat`** pour lancer le bot, ou **`start_web.bat`** pour ouvrir le dashboard sur http://localhost:5000.
4. **`stop.bat`** ferme tout processus bot ou web en cours.

## Linux / macOS

```bash
chmod +x *.sh
./install.sh
# édite .env avec tes clés Bitget
./start.sh           # ou ./start_web.sh
./stop.sh            # pour arrêter
```

C'est tout. En cas de souci, relance `install.bat` / `install.sh` pour réparer le venv.
