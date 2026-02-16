# NVDA MCP Server

Serveur [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) pour piloter le lecteur d'écran [NVDA](https://www.nvaccess.org/) depuis une IA.

## Architecture

Le système est composé de deux parties :

1. **Plugin NVDA** (`nvda_global_plugin/nvdaMCPBridge.py`) — Tourne à l'intérieur de NVDA et expose une API HTTP locale (port 8765) donnant accès à toutes les APIs internes de NVDA.

2. **Serveur MCP** (`server.py`) — Processus standalone qui se connecte au plugin bridge et expose les capacités de NVDA comme des outils MCP (transport stdio ou SSE).

```
┌──────────────┐    stdio/SSE    ┌──────────────┐   HTTP (localhost)  ┌──────────┐
│   Client IA  │ ◄────────────► │  Serveur MCP │ ◄──────────────────► │   NVDA   │
│ (Claude, etc)│                │  (nvda_mcp)  │                     │ (bridge) │
└──────────────┘                └──────────────┘                     └──────────┘
```

## Installation

### 1. Plugin NVDA (bridge)

Copier le fichier du plugin dans le répertoire globalPlugins de NVDA :

```bash
copy nvda_global_plugin\nvdaMCPBridge.py %APPDATA%\nvda\globalPlugins\
```

Puis redémarrer NVDA. Le bridge HTTP démarre automatiquement sur `127.0.0.1:8765`.

### 2. Serveur MCP

```bash
pip install -e .
```

Ou directement :

```bash
pip install mcp
```

## Utilisation

### Lancer le serveur MCP (stdio)

```bash
python -m nvda_mcp
```

### Lancer avec SSE (accès réseau)

```bash
python -m nvda_mcp --transport sse --port 3000
```

### Configuration Claude Desktop

Ajouter dans `claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "nvda": {
      "command": "python",
      "args": ["-m", "nvda_mcp"]
    }
  }
}
```

### Variable d'environnement

Si le bridge tourne sur un port différent :

```bash
set NVDA_BRIDGE_URL=http://127.0.0.1:9999
python -m nvda_mcp
```

## Outils MCP disponibles

### Parole
| Outil | Description |
|-------|-------------|
| `speak` | Faire parler NVDA |
| `cancel_speech` | Arrêter la parole |
| `get_speech_history` | Historique des paroles récentes |
| `get_speech_settings` | Paramètres du synthétiseur |

### Navigation
| Outil | Description |
|-------|-------------|
| `get_focus` | Élément avec le focus clavier |
| `get_foreground` | Fenêtre au premier plan |
| `get_navigator` | Objet du curseur de revue |
| `move_navigator` | Déplacer le curseur (parent/enfant/suivant/précédent) |
| `activate_object` | Activer l'objet courant (clic/Entrée) |
| `get_object_tree` | Arbre d'accessibilité |

### Lecture
| Outil | Description |
|-------|-------------|
| `review_current_line` | Lire la ligne courante |
| `get_status_bar` | Lire la barre de statut |
| `get_clipboard` | Contenu du presse-papiers |
| `set_clipboard` | Modifier le presse-papiers |

### Braille
| Outil | Description |
|-------|-------------|
| `braille_message` | Afficher sur l'afficheur braille |

### Saisie
| Outil | Description |
|-------|-------------|
| `send_keys` | Simuler des touches clavier |
| `move_mouse` | Déplacer la souris |
| `click_mouse` | Cliquer à une position |

### Système
| Outil | Description |
|-------|-------------|
| `get_nvda_version` | Version de NVDA |
| `check_connection` | Vérifier la connexion au bridge |

## Exemples d'utilisation par l'IA

```
# Comprendre ce qui est à l'écran
get_focus()           → [bouton] "OK" states=[focalisé]
get_foreground()      → [fenêtre] "Bloc-notes" app=notepad
get_object_tree()     → arbre hiérarchique des éléments

# Naviguer dans l'interface
move_navigator("firstChild")
move_navigator("next")
activate_object()

# Lire du contenu
review_current_line() → "Ligne de texte courante"
get_status_bar()      → "Ln 1, Col 1"

# Interagir
send_keys("control+a")    # Tout sélectionner
send_keys("control+c")    # Copier
speak("Opération terminée")
```

## Sécurité

- Le bridge HTTP écoute uniquement sur `127.0.0.1` (localhost)
- Aucune authentification n'est requise car seul l'accès local est possible
- Les opérations sont exécutées avec les mêmes permissions que NVDA

## Licence

GPL-2.0-or-later (même licence que NVDA)
