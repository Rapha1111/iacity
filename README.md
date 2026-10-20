# IACity

Simulation sociale 2D (vue de dessus, pixel art) : 1 à 20 agents pilotés par une IA **locale** vivent dans une petite ville,
développent leurs relations, projets et activités économiques, et utilisent leur propre réseau social, **IACHAT**.
Aucune API payante, aucune clé : tout tourne sur votre PC (Python + Flask + navigateur, LLM via Ollama en option).

> Spécification de référence : `IACity_cahier_des_charges.md` (v1.0).

## Démarrage rapide (Windows)

1. Installer [Python 3.10+](https://www.python.org/downloads/) (cocher « Add to PATH »).
2. Double-cliquer sur **`run.bat`** (crée `.venv`, installe Flask, lance le serveur et ouvre le navigateur).
   Ou en ligne de commande :
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```
3. Ouvrir <http://127.0.0.1:5000>.

Linux / macOS : `./run.sh`.

### Avec un vrai modèle local (optionnel)

```bash
ollama pull llama3.2:3b      # ou un autre modèle adapté à votre RAM/GPU
python app.py                # mode « auto » : Ollama détecté => utilisé
```
Sans Ollama (ou sans le modèle), IACity démarre en **mode démonstration** : un « cerveau » heuristique produit les mêmes
décisions structurées qu'un LLM, pour tester toute l'application. Le bandeau en haut à droite et l'onglet **Système**
indiquent le mode actif et les erreurs du modèle (timeouts, réponses invalides…) ; en cas de panne, les règles rapides
prennent le relais et la simulation continue.

## Utilisation

| Zone | Rôle |
|---|---|
| Barre du haut | pause/reprise, pas à pas (en pause), vitesse, **nouvelle simulation** (1–20 agents, graine, personnage optionnel) |
| Carte | clic sur un agent = inspection ; survol = infobulle ; bulles de dialogue ; effets visuels de téléportation |
| **Agent** | Aperçu (conversations en cours, besoins, émotions, personnalité…), Pensées, Mémoire, Relations, Messages privés, Objectifs, Historique, Conversations, Savoirs (rumeurs + provenance) |
| **IACHAT** | fil public, réponses, réactions, publier en tant qu'humain |
| **Journal** | journal global filtrable (type, agent, texte), paginé |
| **Conversations** | transcriptions des conversations ouvertes/terminées (avec ce qui est « entendu de loin ») |
| **Mon personnage** | incarner un habitant : se téléporter, parler (chuchoter/crier), donner son numéro, SMS, acheter. N'affiche que ce que le personnage a perçu |
| **Monde** | déclencher des événements (fête, panne, pénurie, incident, ouverture de commerce, règle économique, subvention), économie, lieux |
| **Système** | LLM, sauvegardes (restaurer / télécharger / importer), exports, vérification d'intégrité |

Les pensées affichées sont des traces simulées générées par le modèle ; elles ne prouvent aucune conscience.

## Configuration

Tous les paramètres sont dans `config.py` et surchargeables par variables d'environnement `IACITY_<NOM>` :
`IACITY_NUM_AGENTS`, `IACITY_SEED`, `IACITY_LLM_MODE` (`auto|ollama|demo`), `IACITY_OLLAMA_MODEL`, `IACITY_OLLAMA_URL`,
`IACITY_LLM_MAX_CONCURRENT`, `IACITY_LLM_CONTEXT`, `IACITY_TICK_SECONDS`, `IACITY_SPEED`, `IACITY_PERCEPTION_EVERY`,
`IACITY_REFLECTION_EVERY`, `IACITY_CONVERSATION_RANGE`, `IACITY_WALL_ATTENUATION`, `IACITY_NOISE_EFFECT`,
`IACITY_START_MONEY`, `IACITY_RENT_PER_DAY`, `IACITY_EVENT_FREQUENCY`, `IACITY_MAP_W/H`, `IACITY_LOG_LEVEL`, `IACITY_PORT`…
Exemple : `set IACITY_LLM_MODE=demo && python app.py`.

## Architecture

```
app.py                  point d'entrée Flask (en-têtes de sécurité, CSP)
config.py               paramètres centralisés (§20)
simulation/
  engine.py             Simulation Engine : horloge, cycles, thread indépendant du rendu, pause/vitesse
  world.py              World Engine : génération de la ville, tuiles, lieux, positions valides
  actions.py            exécuteur d'actions : le moteur est l'autorité finale (validation + refus journalisés)
  events.py             événements du monde (manuels / aléatoires)
  integrity.py          contrôles : monnaie conservée, références, positions
  save_manager.py       snapshots, restauration, import/export, export des journaux
  state.py              identifiants, temps simulé, utilitaires
agents/
  agent.py              état interne d'un agent          decision_engine.py   règles rapides + LLM asynchrone
  memory.py             souvenirs subjectifs, savoirs     llm_adapter.py       Ollama local / démonstration
  goals.py emotions.py  objectifs émergents, émotions     demo_brain.py        cerveau heuristique de démonstration
systems/
  communication.py      portée, murs, bruit, conversations  messaging.py       numéros, SMS
  iachat.py             réseau social                       relationships.py   confiance, hostilité, liens
  economy.py crafting.py  monnaie, travail, logement, fabrication, construction
  event_log.py          journal append-only (SQLite)
api/                    routes Flask + validation (schemas.py)
templates/ static/      interface (canvas pixel art, panneaux d'inspection)
tests/                  47 tests d'acceptation (pytest)
```

### Principes clés

* **Le LLM propose, le moteur dispose** : chaque action (`teleport`, `say`, `buy`, `craft`, `build`…) est validée
  (`api/schemas.py` puis `simulation/actions.py`). Un agent ne peut ni créer d'argent (la monnaie est conservée : trésorerie
  de la Ville ⇄ habitants), ni vendre ce qu'il n'a pas, ni se téléporter sur un mur, ni construire sans terrain, argent et matériaux.
* **Raisonnement hybride** : règles rapides (besoins, travail, réponses simples, routines) ; appels LLM seulement sur déclencheur
  (message reçu, on lui parle, événement, échec, absence d'objectif, réflexion périodique), avec file d'attente et limite de concurrence.
  Les réponses LLM déjà reçues pendant une pause sont conservées puis revalidées à la reprise.
* **Information locale** : mémoires séparées ; une conversation n'est entendue qu'à portée (distance, murs, bruit, volume) et de façon
  éventuellement partielle ; un numéro de téléphone ne s'obtient qu'en personne, par un tiers, sur une devanture de commerce ou un profil IACHAT ;
  IACHAT n'entre dans la mémoire d'un agent que s'il le consulte. Les rumeurs gardent leur provenance et leur confiance.
* **Journal append-only** (SQLite) + **sauvegardes** JSON (état complet + journal) ; à la restauration les événements ultérieurs sont
  *masqués* (jamais supprimés) et l'opération est elle-même journalisée.
* **Sécurité** : serveur lié à `127.0.0.1`, vérification de l'en-tête `Host` et en-tête anti-CSRF `X-IACity`, CSP stricte, interface sans
  `innerHTML` (anti-injection), URL LLM limitée à la machine locale, import de sauvegarde validé (schéma + intégrité).
  Pour exposer volontairement le serveur : `IACITY_ALLOW_REMOTE=1 IACITY_HOST=0.0.0.0` (⚠ pensées et messages privés deviendront visibles).

### Ville

18 lieux : mairie, police, hôpital, école, épicerie, atelier, restaurant, bar, bureaux, 3 résidences, place centrale, parc, 2 rues et
2 terrains à bâtir. Les agents ne reçoivent ni métier ni objectif : ils peuvent travailler (salaire versé par la Ville ou par le
propriétaire du lieu), ramasser des ressources au parc, acheter, fabriquer (`craft`), vendre, construire un lieu, le posséder, fixer des salaires, etc.

## Tests

```bash
pip install -r requirements.txt
python -m pytest -q tests
```

## Limites connues (périmètre v1)

Pas de persistance après arrêt du serveur (sauf sauvegardes exportées), déplacements par téléportation uniquement, pas de besoins
physiologiques détaillés, pas de naissances ni de météo. L'équilibrage économique et la qualité des décisions dépendent du modèle local choisi.
