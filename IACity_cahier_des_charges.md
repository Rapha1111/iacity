# IACity — Cahier des charges fonctionnel et technique

**Version :** 1.0  
**Date :** 20 octobre 2026  
**Statut :** spécification initiale à valider avant développement

---

## 1. Présentation du projet

### 1.1. Nom

**IACity**

### 1.2. Vision

IACity est une simulation sociale en 2D, vue de dessus et en pixel art, dans laquelle un groupe de 1 à 20 agents pilotés par une IA locale vit dans une petite ville virtuelle. Les agents doivent pouvoir développer progressivement leurs propres préférences, croyances, objectifs, activités économiques et relations sociales, sans qu'un métier, une personnalité détaillée ou un objectif de vie leur soit imposé au départ.

L'utilisateur observe la société émerger, peut inspecter les états internes des agents, consulter les conversations auxquelles ils participent, lire leurs messages privés et interagir avec le réseau social fictif **IACHAT**. Il peut aussi incarner un personnage dans la ville et provoquer des événements.

Le but est de créer un environnement expérimental et extensible, permettant d'observer des comportements sociaux émergents : coopération, conflits, commerce, rumeurs, réputation, amitiés, rivalités, créations et changements d'opinion.

### 1.3. Principes directeurs

1. **Autonomie émergente :** aucun objectif ou métier n'est obligatoire au départ. Un agent peut découvrir un intérêt, lancer une activité, fabriquer un objet ou créer un lieu.
2. **Identité évolutive :** personnalité, compétences, valeurs, habitudes et opinions peuvent évoluer selon les expériences.
3. **Information locale :** les agents ne connaissent que les informations qu'ils ont perçues, déduites ou reçues. Ils ne partagent pas automatiquement la mémoire des autres.
4. **Mémoire individuelle :** chaque agent possède sa propre mémoire et son propre historique de pensées.
5. **Conséquences dans le monde :** les actions modifient l'état de la simulation (argent, inventaire, relations, objets, lieux, réputation, etc.).
6. **IA locale et coût nul d'API :** aucun service d'IA payant ne doit être nécessaire.
7. **Observabilité :** l'utilisateur peut inspecter les pensées simulées, les actions et les relations, sans que cette capacité d'observation soit accordée aux autres agents.
8. **Architecture extensible :** les systèmes doivent être séparés afin de permettre l'ajout futur de fonctionnalités.

---

## 2. Périmètre fonctionnel

### 2.1. Inclus dans la première version

- Création d'une simulation avec un nombre configurable de 1 à 20 agents.
- Ville 2D en pixel art, avec environ 10 à 20 bâtiments initiaux.
- Déplacements par téléportation, comme choix explicite de conception initiale.
- Agents autonomes dotés d'états internes, de besoins sociaux et d'émotions simulées.
- Raisonnement hybride : règles locales rapides et appels à un LLM local pour les décisions importantes.
- Mémoire individuelle persistante pendant la session de simulation, conservée indéfiniment jusqu'à l'arrêt ou la réinitialisation de cette simulation.
- Conversations en personne, avec portée influencée par le lieu, les murs et le bruit.
- Téléphone fictif : messages directs possibles uniquement si les agents connaissent le numéro de téléphone du destinataire.
- Réseau social fictif **IACHAT**, consultable par l'utilisateur et sur lequel celui-ci peut publier en tant qu'humain.
- Relations sociales : confiance, amitié, rivalité, hostilité, alliances, réputation, relations professionnelles et commerciales, familles et couples.
- Rumeurs et transmission d'informations de proche en proche.
- Argent, inventaires, achats, ventes et logement.
- Création par les agents d'objets et de lieux, puis possibilité de les vendre ou de les exploiter.
- Contrôles : pause/reprise, événements manuels, sauvegarde/retour à un état antérieur et export des journaux.
- Inspection d'un agent et consultation de ses conversations, pensées, mémoire et état social.
- Interface web servie par un serveur Flask sur le PC de l'utilisateur.

### 2.2. Hors périmètre initial, mais architecture préparée

- Simulation persistante après fermeture du navigateur ou arrêt du serveur.
- Population supérieure à 20 agents.
- Naissances, vieillissement et générations.
- Météo complexe, cycle saisonnier et simulation physique poussée.
- Réseau multi-utilisateur réel.
- Synchronisation entre plusieurs ordinateurs.
- IA distribuée sur plusieurs machines.
- Simulation économique ou politique à grande échelle.

Ces fonctionnalités pourront être ajoutées ultérieurement sans devoir réécrire le cœur de la simulation.

---

## 3. Utilisateurs et rôles

### 3.1. Observateur / administrateur

L'utilisateur principal peut :

- créer et réinitialiser une simulation ;
- choisir le nombre d'agents ;
- démarrer, mettre en pause et reprendre la simulation ;
- accélérer ou ralentir le temps simulé ;
- sélectionner un agent ;
- consulter les pensées internes simulées, les souvenirs, les objectifs, les besoins et les relations ;
- inspecter les conversations en cours et les messages privés ;
- lire les publications et commentaires d'IACHAT ;
- publier sur IACHAT en tant qu'humain ;
- déclencher un événement ;
- sauvegarder un état et restaurer une sauvegarde ;
- exporter les journaux.

L'observateur ne doit pas être traité comme un agent omniscient par les habitants : les informations révélées par l'interface d'administration ne deviennent pas automatiquement connues des agents.

### 3.2. Personnage humain incarné

L'utilisateur peut également apparaître dans la ville comme un personnage contrôlé par lui-même.

Fonctions minimales prévues :
- afficher un nom ou pseudonyme ;
- choisir une position ou une destination ;
- se téléporter vers un lieu ;
- interagir avec un agent ;
- engager une conversation ;
- être reconnu par les agents qui l'ont rencontré ;
- utiliser IACHAT selon les règles de la simulation.

Le personnage humain et le panneau d'administration sont deux modes distincts : l'utilisateur peut observer les coulisses tout en gardant son personnage ignorant des informations qu'il n'a pas découvertes dans le monde.

---

## 4. Agents autonomes

### 4.1. Population initiale

Au démarrage, le système génère entre 1 et 20 agents. Tous sont présents dès le début.

Aucun agent ne reçoit obligatoirement :
- un métier ;
- une ambition prédéfinie ;
- un alignement moral prédéfini ;
- une relation préétablie ;
- un projet économique obligatoire.

Chaque agent reçoit cependant une identité technique unique et les paramètres minimaux nécessaires à son fonctionnement. Les traits psychologiques initiaux peuvent être neutres, faiblement définis ou générés à partir d'une distribution aléatoire. Les préférences et objectifs peuvent ensuite émerger par l'expérience et le raisonnement.

### 4.2. État interne d'un agent

Chaque agent doit disposer au minimum de :

- `id` : identifiant unique ;
- `name` : nom affiché ;
- `position` : position ou lieu actuel ;
- `inventory` : objets possédés ;
- `money` : solde monétaire ;
- `needs` : besoins simulés pertinents ;
- `emotions` : état émotionnel simulé ;
- `personality` : traits qui peuvent évoluer ;
- `beliefs` : croyances et degré de confiance ;
- `values` : valeurs progressivement construites ;
- `goals` : objectifs actuels, éventuellement vides au départ ;
- `plans` : plans d'action ;
- `skills` : compétences acquises ;
- `relationships` : liens avec les autres habitants ;
- `known_contacts` : personnes connues et numéros mémorisés ;
- `memory` : souvenirs personnels ;
- `knowledge` : informations connues et leur provenance ;
- `current_activity` : activité en cours ;
- `reputation` : réputation par domaine ou auprès d'autres agents ;
- `history` : historique d'actions, de pensées et d'événements.

### 4.3. Boucle de décision

À chaque cycle de simulation, un agent suit une boucle de décision :

1. Percevoir son état et les événements accessibles.
2. Évaluer ses besoins, ses émotions, ses objectifs et ses engagements.
3. Déterminer si une décision simple peut être prise par des règles rapides.
4. Si nécessaire, préparer une requête au LLM local avec le contexte utile.
5. Recevoir une décision structurée.
6. Vérifier que l'action est autorisée par les règles du monde.
7. Exécuter l'action ou la rejeter si elle est impossible.
8. Mettre à jour l'état de l'agent et du monde.
9. Enregistrer la pensée, la décision, l'action et ses conséquences dans l'historique.
10. Mettre à jour les souvenirs, croyances, relations et objectifs si l'expérience le justifie.

Le LLM propose une intention ou une action ; **le moteur de simulation reste l'autorité finale**. Un agent ne peut pas créer de l'argent, se téléporter, fabriquer un objet ou modifier un bâtiment sans passer par les règles et validations correspondantes.

### 4.4. Raisonnement hybride

Le système utilise deux niveaux :

**Décisions rapides, sans LLM**
- vérifier les besoins ;
- se déplacer ou se téléporter ;
- consulter un inventaire ;
- exécuter une transaction validée ;
- mettre à jour des compteurs ;
- détecter un événement à portée ;
- effectuer des actions répétitives déjà apprises.

**Décisions approfondies, avec LLM local**
- définir ou réviser un objectif ;
- choisir une activité nouvelle ;
- préparer un projet ;
- résoudre un conflit ;
- interpréter une conversation ambiguë ;
- décider de faire confiance à quelqu'un ;
- élaborer une stratégie sociale ;
- créer une entreprise, un objet ou un lieu ;
- réévaluer une croyance à la lumière d'un événement.

Les appels au modèle doivent être déclenchés par un besoin réel, pas automatiquement à chaque image ou chaque rafraîchissement de l'interface.

### 4.5. Objectifs émergents

Les agents commencent sans objectif obligatoire. Un objectif peut apparaître à la suite :
- d'un besoin ;
- d'une curiosité ;
- d'une conversation ;
- d'une opportunité économique ;
- d'une observation ;
- d'un succès ou d'un échec ;
- d'une influence sociale ;
- d'une croyance ou d'une valeur.

Exemple : un agent remarque que d'autres habitants recherchent du pain, imagine pouvoir en produire, cherche les ressources nécessaires, fabrique du pain, fixe un prix, propose ses produits et peut progressivement développer une boulangerie.

Les objectifs doivent être formulés de façon vérifiable autant que possible : obtenir un objet, rencontrer quelqu'un, gagner une somme, créer un lieu, améliorer une relation, acquérir une compétence. Un agent peut abandonner ou modifier un objectif lorsque ses priorités changent.

### 4.6. Émotions, croyances et stratégie sociale

Les agents peuvent simuler :
- joie, tristesse, colère, peur, frustration, curiosité, confiance, jalousie et autres états pertinents ;
- croyances vraies, fausses ou incertaines ;
- mensonge, omission, persuasion, négociation et manipulation sociale ;
- stratégies à court ou long terme ;
- changement d'opinion après une expérience ;
- apprentissage à partir de réussites et d'erreurs.

Ces états sont des mécanismes simulés, et non la preuve d'une conscience réelle. Les journaux doivent distinguer si possible les faits observés, les croyances d'un agent et les hypothèses produites par le modèle.

---

## 5. Mémoire et connaissance

### 5.1. Mémoire individuelle

Chaque agent possède une mémoire séparée. Elle contient :

- pensées internes générées ;
- événements personnellement vécus ;
- conversations entendues ou auxquelles il a participé ;
- actions et conséquences ;
- objectifs et projets ;
- personnes rencontrées ;
- informations reçues et leur source ;
- changements de relation ;
- succès, échecs et leçons apprises ;
- croyances anciennes et nouvelles ;
- éléments incertains, oubliés ou potentiellement déformés.

### 5.2. Conservation

Durant une simulation, l'historique est conservé sans limite arbitraire imposée par le produit. La réinitialisation crée un monde neuf et efface l'état de la simulation en cours.

Comme la mémoire complète peut devenir volumineuse, le système doit :
- enregistrer les événements dans une structure efficace ;
- paginer les journaux dans l'interface ;
- permettre une recherche et un filtrage ;
- éviter de charger tout l'historique en mémoire du navigateur ;
- ne pas supprimer silencieusement les événements anciens.

La conservation indéfinie s'applique à la durée de vie de la simulation active. Les sauvegardes exportées peuvent servir à reprendre un monde ultérieurement, mais la conservation après arrêt du serveur n'est pas requise dans le périmètre initial.

### 5.3. Souvenirs imparfaits

Un agent peut se tromper ou se souvenir de manière incomplète. Il faut distinguer :
- le fait d'origine enregistré dans le journal global ;
- le souvenir subjectif de l'agent ;
- son interprétation ;
- son niveau de confiance ;
- les modifications éventuelles de son souvenir.

Une rumeur n'est pas automatiquement transformée en fait vérifié. Chaque transmission peut conserver une provenance et un niveau d'incertitude.

---

## 6. Communication en personne

### 6.1. Détection de proximité

La portée d'une conversation dépend du contexte :
- distance entre les personnages ;
- présence d'un mur ou d'un obstacle ;
- intérieur ou extérieur ;
- bruit ambiant ;
- volume ou discrétion de la conversation ;
- type de lieu.

Une conversation chuchotée doit être moins audible qu'une conversation forte. Un mur doit limiter la transmission. Le calcul peut être simplifié dans le premier prototype, mais il doit être centralisé dans un module de perception pour pouvoir être amélioré.

### 6.2. Participation

Les agents à portée peuvent entendre une conversation, en comprendre une partie, choisir de participer, de rester silencieux ou de partir. Ils ne reçoivent pas automatiquement une transcription parfaite si le contexte rend l'écoute difficile.

Les discussions peuvent comporter plusieurs tours de parole, des désaccords, des négociations, des interruptions, des changements de sujet et des départs.

### 6.3. Conséquences

Une conversation peut :
- créer ou modifier un souvenir ;
- modifier une relation ;
- déclencher un objectif ;
- transmettre une information ;
- propager une rumeur ;
- lancer une transaction ;
- déclencher un conflit ou une réconciliation ;
- mener à un échange de numéros de téléphone.

Les bulles de dialogue s'affichent au-dessus des agents concernés dans la ville.

---

## 7. Téléphone et messages privés

### 7.1. Carnet de contacts

Chaque agent dispose de son propre carnet de contacts. Il ne peut envoyer un message direct qu'à une personne dont il connaît le numéro.

Le numéro est un identifiant fictif attribué dans la simulation. Il peut être communiqué en personne, découvert par une règle explicite du monde ou obtenu par un autre mécanisme autorisé. Il ne doit pas être deviné ou ajouté arbitrairement par le système.

### 7.2. Messagerie

Fonctionnalités :
- envoyer et recevoir des messages ;
- historique des conversations par paire d'agents ;
- horodatage simulé ;
- état de livraison et de lecture si ces notions sont retenues ;
- conservation des messages dans la mémoire des participants ;
- possibilité pour l'observateur de consulter les messages privés via un panneau d'administration.

L'observateur a un accès spécial de supervision. Les autres agents ne voient que leurs propres conversations et les messages qui leur sont effectivement accessibles.

Les messages privés ne sont pas visibles publiquement sur IACHAT, sauf si un participant les publie volontairement ou en révèle le contenu à un autre agent.

---

## 8. Réseau social IACHAT

### 8.1. Concept

**IACHAT** est un réseau social fictif inspiré des plateformes de micropublication. Il est distinct de la messagerie privée et des conversations en personne.

### 8.2. Fonctionnalités minimales

- fil de publications ;
- auteur et horodatage ;
- texte de publication ;
- réponses et commentaires ;
- réactions simples ;
- profil de chaque agent ;
- affichage des publications de l'utilisateur humain ;
- publication humaine depuis l'interface ;
- historique des publications et réponses ;
- possibilité pour les agents de lire des publications accessibles, de répondre ou de s'en inspirer.

### 8.3. Comportements émergents

Les agents peuvent utiliser IACHAT pour :
- partager une information ;
- raconter un événement ;
- promouvoir un commerce ou un objet ;
- exprimer une opinion ;
- rechercher des partenaires ;
- lancer une invitation ;
- débattre, critiquer ou répandre une rumeur.

Les publications influencent les agents uniquement si ceux-ci les consultent ou les reçoivent par un mécanisme défini. Le système ne doit pas injecter automatiquement chaque publication dans la mémoire de toute la population.

### 8.4. Distinction des canaux

Les canaux doivent rester distincts :
1. conversation en personne ;
2. message direct privé ;
3. publication publique sur IACHAT ;
4. pensée privée ;
5. journal d'administration visible uniquement par l'utilisateur.

---

## 9. Ville et environnement

### 9.1. Présentation visuelle

- vue de dessus en 2D ;
- esthétique pixel art ;
- caméra montrant toute la ville par défaut ;
- sélection d'agents et de bâtiments ;
- bulles de dialogue ;
- représentation claire des lieux, personnages et objets ;
- interface utilisable sur un navigateur de bureau.

La ville initiale comporte environ 10 à 20 bâtiments et espaces.

### 9.2. Lieux initiaux

La génération initiale peut inclure :
- maisons et appartements ;
- rues et place centrale ;
- parc ;
- commerces et restaurants ;
- école ou université ;
- bureaux ou lieux de travail ;
- lieux de loisirs, bars ou clubs ;
- mairie ;
- police ;
- hôpital.

La présence de tous ces lieux n'est pas obligatoire dans chaque carte, mais la génération doit assurer une ville cohérente et variée.

### 9.3. Téléportation

Le déplacement est volontairement fondé sur la téléportation dans la première version. Un agent peut choisir un lieu ou une position valide, puis y apparaître immédiatement. Le système doit :
- empêcher l'apparition dans une position interdite ;
- vérifier que le lieu existe et est accessible ;
- mettre à jour la position et l'historique ;
- déclencher les perceptions locales à l'arrivée ;
- permettre d'afficher visuellement le changement de position.

L'architecture doit permettre de remplacer ultérieurement la téléportation par un déplacement progressif.

### 9.4. Création de lieux

Un agent peut proposer de créer un lieu. La création doit passer par une validation du moteur qui vérifie :
- les ressources nécessaires ;
- le coût éventuel ;
- la disponibilité d'un emplacement ;
- les règles de construction ;
- le type et les propriétés du lieu ;
- l'impact sur l'économie et le monde.

Un agent peut créer, exploiter, posséder ou vendre un lieu selon les règles économiques retenues. Une proposition générée par le LLM n'est pas appliquée directement sans validation.

### 9.5. Objets créés par les agents

Les agents peuvent imaginer et fabriquer des objets, puis les vendre ou les échanger. Chaque objet doit avoir au minimum :
- identifiant ;
- nom ;
- description ;
- créateur ;
- propriétaire actuel ;
- prix éventuel ;
- catégorie ;
- ressources ou coût de fabrication ;
- règles d'utilisation, si nécessaire.

Les objets sont des entités du monde, pas uniquement du texte dans une conversation. La fabrication et la vente doivent modifier les stocks, les ressources et les soldes.

---

## 10. Économie et vie quotidienne

### 10.1. Système monétaire

Chaque agent possède un solde. Les transactions doivent être atomiques et vérifiées : un acheteur ne peut pas payer plus que ce qu'il possède, et un vendeur ne peut pas vendre un objet qu'il ne possède pas.

### 10.2. Inventaires et commerce

- achat et vente d'objets ;
- transfert de propriété ;
- prix défini par le vendeur ou négocié ;
- inventaire de chaque agent ;
- historique des transactions ;
- création de produits par les agents ;
- possibilité d'ouvrir une activité commerciale.

### 10.3. Logement

Les agents peuvent posséder, louer ou occuper un logement si le système économique correspondant est activé. Les règles exactes de loyer, de propriété et de coût de vie sont des paramètres à définir et à équilibrer.

### 10.4. Besoins et loisirs

Les mécaniques de première version privilégient :
- argent et achats ;
- logement ;
- loisirs ;
- événements collectifs ;
- besoins sociaux ;
- émotions et relations.

Les besoins physiologiques détaillés ne sont pas obligatoires dans la première version. L'architecture peut les accueillir plus tard.

---

## 11. Interface utilisateur

### 11.1. Vue principale

La page principale affiche :
- la ville en pixel art ;
- les agents et leurs positions ;
- les bâtiments et lieux ;
- les bulles de dialogue ;
- l'état de la simulation ;
- les commandes pause/reprise ;
- l'accès aux panneaux d'inspection.

### 11.2. Panneau d'agent

Lorsqu'un agent est sélectionné, l'interface affiche au minimum ses conversations en cours. Le panneau pourra proposer des onglets :
- **Aperçu :** nom, position, argent, activité actuelle ;
- **Pensées :** pensées simulées et décisions récentes ;
- **Mémoire :** souvenirs et événements retenus ;
- **Relations :** liens, confiance, hostilité et historique ;
- **Messages :** conversations privées de cet agent, accessibles à l'observateur ;
- **Objectifs :** objectifs actuels et progression ;
- **Historique :** actions, déplacements et événements.

Les journaux doivent être horodatés en temps simulé et, si utile, en temps réel.

### 11.3. IACHAT

Une vue dédiée doit permettre de :
- consulter le fil public ;
- filtrer ou consulter les publications d'un agent ;
- lire les réponses ;
- écrire et publier un message en tant qu'humain ;
- identifier clairement les publications humaines et celles des agents.

### 11.4. Contrôles de simulation

- démarrer, mettre en pause et reprendre ;
- modifier la vitesse de simulation ;
- déclencher un événement depuis une liste de scénarios ;
- enregistrer une sauvegarde ;
- restaurer une sauvegarde ;
- exporter les journaux.

Exemples d'événements : fête de quartier, panne, ouverture d'un commerce, pénurie, incident public ou changement de règle économique. Chaque événement doit avoir un effet explicite sur l'état du monde.

---

## 12. Architecture technique proposée

### 12.1. Principes

Le projet est une application web locale. Flask sert l'interface et expose les API de contrôle. La simulation et le modèle de langage fonctionnent sur le PC de l'utilisateur. Le navigateur affiche le monde et envoie les commandes.

### 12.2. Technologies envisagées

- **Python 3** pour la simulation ;
- **Flask** pour le serveur web et les API ;
- **HTML, CSS et JavaScript** pour l'interface ;
- **Canvas HTML5** ou une bibliothèque 2D légère pour dessiner la ville ;
- **SQLite** ou un journal structuré pour conserver l'état et les événements de la session ;
- **Ollama** ou un serveur local compatible pour appeler un LLM installé sur la machine, sous réserve de disponibilité et de configuration.

Le choix final du modèle local dépendra de la RAM, du processeur et, le cas échéant, du GPU du PC. Le système doit rester utilisable sans clé API et sans connexion à un fournisseur payant. Le téléchargement initial d'un modèle local peut nécessiter Internet, mais les appels d'inférence ne doivent pas dépendre d'un service distant.

### 12.3. Composants logiciels

1. **Simulation Engine** : horloge simulée, cycles, événements et orchestration.
2. **Agent Engine** : état, perception, décision, objectifs et actions.
3. **LLM Adapter** : appels au modèle local, prompts et validation de réponses structurées.
4. **World Engine** : carte, lieux, positions, objets et règles d'accès.
5. **Communication Engine** : proximité, portée, conversations et audibilité.
6. **Messaging Engine** : contacts, numéros et messages privés.
7. **IACHAT Engine** : publications, réponses et consultation du fil.
8. **Social Engine** : relations, réputation, confiance, conflits et rumeurs.
9. **Economy Engine** : monnaie, inventaires, transactions, fabrication et ventes.
10. **Memory Engine** : souvenirs, pensées, croyances et provenance de l'information.
11. **Event Log** : journal append-only des événements et actions.
12. **Save/Replay Manager** : sauvegardes et restauration d'un état antérieur.
13. **Flask API** : accès contrôlé à l'état et commandes de l'interface.
14. **Frontend** : ville, panneaux d'inspection et contrôles.

### 12.4. Organisation de fichiers indicative

```text
IACity/
├── app.py
├── config.py
├── requirements.txt
├── README.md
├── simulation/
│   ├── engine.py
│   ├── clock.py
│   ├── world.py
│   ├── events.py
│   └── save_manager.py
├── agents/
│   ├── agent.py
│   ├── decision_engine.py
│   ├── goals.py
│   ├── emotions.py
│   ├── memory.py
│   └── llm_adapter.py
├── systems/
│   ├── communication.py
│   ├── messaging.py
│   ├── iachat.py
│   ├── relationships.py
│   ├── economy.py
│   ├── crafting.py
│   └── event_log.py
├── api/
│   ├── routes.py
│   └── schemas.py
├── data/
│   ├── maps/
│   └── assets/
├── templates/
│   └── index.html
└── static/
    ├── css/
    ├── js/
    └── assets/
```

Cette arborescence est indicative et peut évoluer pendant le développement.

---

## 13. Moteur de simulation et temps

### 13.1. Boucle indépendante du rendu

Le moteur de simulation ne doit pas dépendre de la fréquence de rafraîchissement graphique. L'interface peut se rafraîchir régulièrement, tandis que la simulation progresse selon une horloge propre.

### 13.2. Cycle logique

À chaque cycle :
1. avancer l'horloge simulée ;
2. mettre à jour les événements planifiés ;
3. actualiser les perceptions des agents ;
4. déclencher les décisions nécessaires ;
5. valider et appliquer les actions ;
6. traiter les conversations et messages ;
7. mettre à jour relations, économie et souvenirs ;
8. enregistrer les événements ;
9. transmettre au navigateur les changements pertinents.

### 13.3. Pause et vitesse

La pause doit arrêter la progression du temps simulé et l'exécution des nouvelles décisions. La vitesse modifie la progression du monde sans changer la logique de validation des actions. Les requêtes LLM déjà en cours doivent être traitées de manière déterministe : soit elles sont annulées proprement, soit leur résultat est conservé mais appliqué uniquement après reprise et revalidation.

### 13.4. Exécution avec navigateur ouvert

Le serveur Flask tourne localement sur le PC. La simulation continue tant que le processus serveur fonctionne, même si l'onglet est momentanément inactif. Le navigateur peut être fermé sans garantir l'arrêt immédiat du serveur ; l'arrêt de la simulation doit être contrôlé par le serveur ou par sa fermeture. Le périmètre initial ne requiert pas de persistance après arrêt du serveur.

---

## 14. Modèle de données

Les données devront être structurées, validées et versionnées. Les principales entités sont :

- **Simulation** : identifiant, horloge, état de pause, vitesse, version du schéma.
- **Agent** : identité, état courant, besoins, personnalité, objectifs, inventaire.
- **ThoughtEvent** : agent, horodatage, contenu généré, type, décision associée.
- **WorldEvent** : événement, lieu, acteurs, effets et horodatage.
- **Conversation** : participants, lieu, portée, état et historique des tours de parole.
- **Message** : expéditeur, destinataire, contenu, date simulée et état.
- **Contact** : propriétaire du carnet, agent connu, numéro connu et provenance.
- **Post** : auteur, contenu, horodatage, réponses et réactions.
- **Relationship** : agents concernés, indicateurs relationnels et historique.
- **Memory** : propriétaire, contenu, source, confiance et événement d'origine.
- **Goal** : agent, description, état, priorité, origine et progression.
- **Place** : type, propriétaire, position, inventaire ou capacités.
- **Item** : créateur, propriétaire, caractéristiques et valeur.
- **Transaction** : acheteur, vendeur, objets, prix et résultat.
- **Snapshot** : état de simulation à un point donné.
- **LogEntry** : séquence ordonnée d'un événement ou d'une action.

Les identifiants doivent être stables pendant une simulation. Les références entre objets doivent être vérifiées pour éviter les états incohérents.

---

## 15. Sauvegardes, retour arrière et journaux

### 15.1. Journal d'événements

Les événements importants doivent être enregistrés dans un journal ordonné, comprenant notamment :
- pensées générées ;
- décisions et actions ;
- déplacements et téléportations ;
- messages privés ;
- conversations ;
- publications IACHAT ;
- changements de relation ;
- transactions ;
- créations d'objets et de lieux ;
- événements déclenchés par l'utilisateur.

Chaque entrée doit inclure un identifiant, un temps simulé, le type d'événement, les acteurs concernés et les données utiles.

### 15.2. Sauvegarde et restauration

Une sauvegarde capture l'état nécessaire pour restaurer la simulation à un instant précis. Le retour arrière doit restaurer les agents, la ville, les objets, les relations, les messages, les publications, les objectifs, la monnaie, les souvenirs et l'horloge simulée.

Après restauration, les événements postérieurs à la sauvegarde ne doivent pas continuer à modifier le monde restauré. Les journaux peuvent conserver un historique externe des opérations de restauration afin de faciliter le diagnostic.

### 15.3. Export

L'utilisateur peut exporter les journaux dans un format lisible, au minimum JSON ou JSONL, et idéalement CSV pour certains tableaux. L'export doit préciser la version du schéma et l'intervalle temporel concerné.

---

## 16. Exigences de qualité et sécurité technique

- L'application doit fonctionner sur un PC Windows standard avec Python installé.
- Aucune clé d'API payante ne doit être requise.
- Une absence de modèle local doit être signalée clairement ; un mode de simulation simplifié peut permettre de tester l'interface.
- Les réponses du LLM doivent être structurées, parsées et validées avant toute action.
- Les actions impossibles ou non autorisées doivent être refusées proprement.
- Les entrées affichées dans l'interface doivent être échappées pour prévenir l'injection HTML/JavaScript.
- L'API Flask doit être limitée à la machine locale par défaut.
- Le serveur ne doit pas exposer les pensées et messages privés sur le réseau local ou Internet sans action explicite de configuration.
- L'application doit afficher les erreurs du modèle local et continuer autant que possible en mode de repli.
- Le système doit gérer les délais d'attente, les réponses mal formées et l'indisponibilité du modèle.
- Les journaux doivent permettre de comprendre pourquoi une action a été acceptée ou refusée.
- L'interface doit rester utilisable même lorsque le modèle prend plusieurs secondes à répondre.

Les pensées affichées sont des traces de raisonnement générées par le modèle et des résumés internes de la simulation ; elles ne doivent pas être présentées comme une preuve de conscience réelle.

---

## 17. Performances et gestion des coûts

Le nombre initial maximal est de 20 agents. La performance doit être obtenue en évitant de solliciter le LLM pour chaque action triviale.

Mesures prévues :
- déclenchement événementiel des réflexions approfondies ;
- limitation configurable du nombre d'appels LLM simultanés ;
- mise en file d'attente des décisions ;
- détection des actions répétitives pouvant utiliser les règles rapides ;
- mise à jour graphique séparée du moteur ;
- chargement paginé des historiques ;
- journalisation en écriture append-only ;
- configuration de la taille de contexte du modèle.

Le coût d'API visé est de **0 €**. Les ressources consommées sont celles du PC : CPU, mémoire, GPU éventuel et stockage. Le modèle local choisi doit être adapté au matériel disponible. Un modèle trop lourd peut ralentir fortement la simulation.

---

## 18. Tests et critères d'acceptation

### 18.1. Démarrage

- Le serveur Flask démarre via une commande documentée.
- L'interface est accessible dans un navigateur à une adresse locale.
- L'utilisateur peut choisir de 1 à 20 agents.
- La ville et les agents sont générés sans état incohérent.

### 18.2. Autonomie

- Un agent peut commencer sans objectif explicite.
- Un événement ou une expérience peut conduire à la création d'un objectif.
- Un agent peut proposer une activité économique nouvelle.
- Les actions proposées sont validées par le moteur avant application.

### 18.3. Mémoire

- Chaque agent possède une mémoire distincte.
- Une conversation entendue peut être mémorisée par un agent qui n'en est pas participant direct si les règles de portée le permettent.
- Un agent ne connaît pas automatiquement les souvenirs privés des autres.
- Les pensées et actions sont consultables dans l'interface d'administration.
- La réinitialisation crée une simulation neuve.

### 18.4. Communication

- Une conversation locale n'est perceptible que dans sa portée effective.
- Les obstacles et le bruit peuvent réduire l'audibilité.
- Un agent ne peut pas envoyer un message direct à un agent dont il ne connaît pas le numéro.
- Les messages privés sont visibles dans le panneau d'administration, mais ne sont pas automatiquement publiés sur IACHAT.
- Une publication IACHAT est consultable par les agents qui y ont accès selon les règles définies.

### 18.5. Économie et création

- Une transaction ne peut pas créer d'argent ou d'objet sans justification.
- Un agent ne peut pas vendre un objet qu'il ne possède pas.
- La fabrication vérifie les ressources et règles nécessaires.
- La création d'un lieu vérifie l'emplacement et les coûts définis.
- Les transactions modifient les soldes et inventaires de façon cohérente.

### 18.6. Interface et contrôle

- L'utilisateur peut mettre en pause et reprendre la simulation.
- La pause arrête le temps simulé.
- L'utilisateur peut déclencher un événement.
- Une sauvegarde peut être restaurée sans mélanger l'état antérieur et l'état futur.
- Les journaux peuvent être exportés.
- L'utilisateur peut publier sur IACHAT en tant qu'humain.

### 18.7. Robustesse

- Une réponse invalide du LLM n'entraîne pas de corruption de l'état.
- Un appel trop lent ne bloque pas le rendu de la ville.
- Les journaux restent consultables sans charger l'intégralité de l'historique dans le navigateur.
- L'application reste contrôlable en cas d'indisponibilité du modèle local.

---

## 19. Plan de développement proposé

### Phase 1 — Socle jouable

- structure Flask ;
- ville pixel art ;
- génération de 1 à 20 agents ;
- téléportation ;
- horloge, pause et reprise ;
- inspection basique des agents.

**Livrable :** une ville interactive avec des agents visibles et sélectionnables.

### Phase 2 — Agents et mémoire

- état interne des agents ;
- objectifs émergents ;
- décisions rapides ;
- mémoire et journal d'événements ;
- connexion au modèle local ;
- validation des actions.

**Livrable :** des agents capables de prendre des décisions et d'enregistrer leurs expériences.

### Phase 3 — Conversations et relations

- conversations locales ;
- portée, obstacles et bruit ;
- bulles de dialogue ;
- relations, confiance, hostilité et rumeurs ;
- inspection des pensées et souvenirs.

**Livrable :** des agents qui se rencontrent et influencent leurs croyances et relations.

### Phase 4 — Téléphone et IACHAT

- carnet de contacts et numéros ;
- messagerie privée ;
- panneau de supervision des messages ;
- fil public IACHAT ;
- publications, réponses et publications humaines.

**Livrable :** communications en personne, privées et publiques séparées.

### Phase 5 — Économie émergente

- argent et inventaires ;
- achats, ventes et transactions ;
- fabrication d'objets ;
- création de commerces et de lieux ;
- propriété et exploitation.

**Livrable :** des agents capables de lancer des activités et d'échanger des biens.

### Phase 6 — Sauvegardes et robustesse

- snapshots ;
- restauration ;
- export des journaux ;
- tests d'intégrité ;
- gestion des erreurs et performances ;
- documentation d'installation Windows.

**Livrable :** un prototype complet, relançable et extensible.

---

## 20. Paramètres configurables

Les paramètres suivants doivent être centralisés plutôt que dispersés dans le code :

- nombre d'agents au démarrage ;
- graine aléatoire de la simulation ;
- modèle local et adresse du service d'inférence ;
- limites de contexte et d'appels simultanés ;
- vitesse de simulation ;
- fréquence de perception ;
- fréquence de réflexion approfondie ;
- portée de conversation de base ;
- effet du bruit et des obstacles ;
- paramètres économiques initiaux ;
- taille de la carte ;
- fréquence des événements ;
- niveau de journalisation ;
- mode de démonstration sans modèle local.

---

## 21. Décisions retenues et points encore ouverts

### Décisions retenues

- Nom : **IACity**.
- Population initiale : 1 à 20 agents, tous présents au départ.
- Pas de métier ou d'objectif obligatoire au lancement.
- Agents autonomes, avec comportements émergents.
- Modèle d'IA local, sans coût d'API.
- Raisonnement hybride entre règles rapides et LLM.
- Mémoire individuelle et historique détaillé pendant la simulation.
- Réinitialisation complète au redémarrage, sauf restauration depuis une sauvegarde exportée.
- Conversations en personne influencées par distance, bruit et obstacles.
- Messages directs conditionnés par la connaissance du numéro.
- Réseau social public IACHAT.
- Possibilité pour l'humain de publier sur IACHAT et d'incarner un personnage.
- Ville pixel art en 2D vue de dessus, environ 10 à 20 bâtiments.
- Téléportation comme mécanisme de déplacement initial.
- Argent, achats, logement, loisirs et événements collectifs.
- Création et vente d'objets et de lieux par les agents.
- Contrôle de la simulation, événements manuels, sauvegarde, restauration et export.
- Python, Flask et interface web locale sur Windows.

### Points à fixer pendant l'implémentation

1. **Modèle local exact :** dépend du matériel disponible et devra être choisi ou testé au démarrage.
2. **Règles initiales de monnaie et de ressources :** valeurs par défaut à équilibrer.
3. **Règles de propriété des lieux :** achat, location, construction et vente seront précisées dans le système économique.
4. **Portée exacte des conversations :** valeurs de départ configurables, ajustables après essais.
5. **Profondeur des pensées visibles :** interface d'inspection des traces et résumés générés, sans prétendre exposer une conscience ou un raisonnement parfait.
6. **Sauvegardes :** formats et fréquence automatique à définir. La reprise après arrêt du serveur n'est pas garantie dans le périmètre initial.
7. **Style graphique détaillé :** palette, taille des sprites et animations à choisir pendant la réalisation.

---

## 22. Définition de « terminé »

La première version d'IACity sera considérée comme livrée lorsque l'utilisateur pourra lancer le serveur local, ouvrir la ville dans son navigateur, créer de 1 à 20 agents, les observer réfléchir et agir via le moteur hybride, voir des interactions sociales avec une portée locale, consulter les pensées et messages autorisés dans l'interface d'administration, publier sur IACHAT, effectuer des transactions, constater la création d'objets ou de lieux validés par le moteur, mettre la simulation en pause, déclencher un événement, sauvegarder/restaurer un état et exporter les journaux — le tout sans API payante obligatoire.

**Ce document est la spécification de référence initiale.** Toute fonctionnalité non incluse explicitement dans le périmètre initial devra être traitée comme une évolution ou faire l'objet d'une décision complémentaire.
