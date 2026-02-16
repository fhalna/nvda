# NVDA MCP Server

Serveur [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) pour piloter le lecteur d'écran [NVDA](https://www.nvaccess.org/) depuis une IA.

## Pré-requis

> **NVDA est un lecteur d'écran Windows.** Il nécessite un poste Windows
> avec un bureau graphique. Il ne tourne pas sous Linux, pas dans un
> conteneur, et pas sans affichage.

| Composant | Requis | Détail |
|-----------|--------|--------|
| **Windows** | 10 / 11 | Bureau graphique actif (pas de session headless) |
| **NVDA** | ≥ 2024.1 | [Télécharger](https://www.nvaccess.org/download/) |
| **Firefox** | ≥ 115 ESR | **Seul navigateur pleinement supporté** par NVDA (IAccessible2). Chrome a un support UIA partiel et incomplet. Edge/Safari ne sont pas supportés. |
| **Python** | ≥ 3.10 | Pour le serveur MCP et le navigateur |

### Pourquoi Firefox ?

NVDA interagit avec les navigateurs via des APIs d'accessibilité :

- **Firefox** : Implémente IAccessible2 (IA2), l'API que NVDA utilise nativement. Le mode navigation (browse mode), le curseur virtuel, et toutes les commandes rapides (H, K, D, F, T, G…) fonctionnent pleinement.
- **Chrome/Edge** : Support partiel via UIA. Certaines fonctionnalités manquent ou sont instables. Non recommandé pour l'audit.
- **Autres** : Non supportés.

## Architecture

```
┌─────────────────────── Poste Windows ───────────────────────┐
│                                                             │
│  ┌──────────┐    IAccessible2    ┌──────────┐              │
│  │ Firefox  │ ◄────────────────► │   NVDA   │              │
│  │ (page)   │                    │          │              │
│  └──────────┘                    │  bridge  │──┐           │
│                                  │  plugin  │  │ HTTP      │
│                                  └──────────┘  │ :8765     │
│                                                │           │
│                                  ┌──────────┐  │           │
│                                  │ Serveur  │◄─┘           │
│                                  │   MCP    │              │
│                                  │(nvda_mcp)│              │
│                                  └────┬─────┘              │
│                                       │ stdio / SSE        │
└───────────────────────────────────────┼─────────────────────┘
                                        │
                               ┌────────┴────────┐
                               │   Client IA     │
                               │ (Claude, script, │
                               │  navigator.py)  │
                               └─────────────────┘
```

**Tout tourne sur le même poste Windows** (ou le client IA peut être distant via SSE).

## Installation

### Étape 1 : Installer le plugin NVDA (bridge)

Le bridge est un global plugin NVDA qui expose une API HTTP locale.

```cmd
:: Copier le plugin dans NVDA
copy nvda_global_plugin\nvdaMCPBridge.py "%APPDATA%\nvda\globalPlugins\"

:: Redémarrer NVDA (le bridge démarre automatiquement sur 127.0.0.1:8765)
```

Vérifier que le bridge fonctionne :

```cmd
curl http://127.0.0.1:8765/health
:: Doit retourner : {"status": "ok", "version": "2025.1"}
```

### Étape 2 : Installer le serveur MCP

```cmd
cd nvda_mcp
pip install -e .
```

Ou juste la dépendance :

```cmd
pip install mcp
```

### Étape 3 : Configurer Firefox

1. Ouvrir Firefox
2. S'assurer qu'il est le navigateur au premier plan
3. NVDA doit annoncer "Firefox" quand on alt-tab vers lui

## Utilisation

### Mode 1 : Claude Desktop (stdio)

Ajouter dans `%APPDATA%\Claude\claude_desktop_config.json` :

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

Claude peut alors piloter NVDA directement :
> "Navigue vers tanaguru.com et lis-moi les titres de la page"

### Mode 2 : Serveur SSE (accès réseau ou script)

```cmd
python -m nvda_mcp --transport sse --port 8080
```

Le serveur MCP est accessible sur `http://localhost:8080/sse`.

### Mode 3 : Navigator — Parcours automatisé avec restitution

Le navigator est un vrai client MCP qui pilote NVDA comme un utilisateur aveugle :

```cmd
:: Démarrer le serveur MCP
python -m nvda_mcp --transport sse --port 8080

:: Parcourir une page et produire le fichier de restitution
python -m nvda_mcp.navigator https://www.tanaguru.com -o restitution.txt
```

Le navigator exécute cette séquence de commandes NVDA :

| Étape | Touche NVDA | Action |
|-------|-------------|--------|
| 1 | `Ctrl+L` | Ouvrir la barre d'adresse Firefox |
| 2 | `Ctrl+V` + `Entrée` | Coller l'URL et charger la page |
| 3 | `Ctrl+Home` | Revenir en haut de page |
| 4 | `D` (répété) | Parcourir tous les **repères** (landmarks) |
| 5 | `H` (répété) | Parcourir tous les **titres** (headings) |
| 6 | `↓` (répété) | Lire la page **ligne par ligne** |
| 7 | `K` (répété) | Parcourir tous les **liens** |
| 8 | `F` (répété) | Parcourir tous les **champs de formulaire** |
| 9 | `G` (répété) | Parcourir toutes les **images** |
| 10 | `T` (répété) | Parcourir tous les **tableaux** |

Options du navigator :

```
python -m nvda_mcp.navigator URL [options]
  -o FILE       Fichier de sortie (défaut : stdout)
  --mcp-url     URL du serveur MCP (défaut : http://localhost:8080/sse)
  --skip-nav    Ne pas naviguer vers l'URL (page déjà ouverte)
  --delay 0.5   Délai entre les commandes (défaut : 0.3s)
```

### Variable d'environnement

```cmd
set NVDA_BRIDGE_URL=http://127.0.0.1:9999
python -m nvda_mcp
```

## Docker (serveur MCP uniquement)

Le conteneur Docker ne contient que le **serveur MCP**. NVDA + Firefox doivent tourner sur le poste Windows hôte.

```
┌──── Docker ─────┐         ┌──── Windows (hôte) ────┐
│  Serveur MCP    │◄───────►│  NVDA + Bridge (:8765)  │
│  :8080 (SSE)    │  HTTP   │  Firefox                │
└─────────────────┘         └─────────────────────────┘
```

```bash
docker compose up mcp-server
```

Pour le navigator via Docker :

```bash
docker compose run --rm --profile nav navigator https://www.tanaguru.com -o /output/restitution.txt
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

## Exemple de restitution

Voici un extrait du fichier produit par le navigator :

```
========================================================================
  RESTITUTION NVDA — https://www.tanaguru.com
  Date : 2025-06-15 14:32:01
  NVDA : NVDA version 2025.1
  Durée du parcours : 45.2s
========================================================================

------------------------------------------------------------------------
  REPÈRES / LANDMARKS (4)
  Navigation : touche D
------------------------------------------------------------------------
    1. bannière  repère
    2. navigation  repère
    3. contenu principal  repère
    4. informations de contenu  repère

------------------------------------------------------------------------
  TITRES / HEADINGS (8)
  Navigation : touche H
------------------------------------------------------------------------
    1. titre de niveau 1  L'accessibilité numérique, simplement
    2. titre de niveau 2  Nos services
    3. titre de niveau 3  Audit
    ...

------------------------------------------------------------------------
  PARCOURS COMPLET — LIGNE PAR LIGNE (97 lignes)
  Navigation : flèche bas (downArrow)
------------------------------------------------------------------------
    1. lien Aller au contenu
    2. bannière  repère
    3. lien graphique  logo Tanaguru
    ...
```

## Sécurité

- Le bridge HTTP écoute uniquement sur `127.0.0.1` (localhost)
- Aucune authentification n'est requise car seul l'accès local est possible
- Les opérations sont exécutées avec les mêmes permissions que NVDA

## Licence

GPL-2.0-or-later (même licence que NVDA)
