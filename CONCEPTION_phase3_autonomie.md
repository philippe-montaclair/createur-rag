# Conception — phase 3 : options du profil « total », autonomie, mémoire

> Note de conception rédigée le 26/07/2026. **Les six décisions ont été tranchées le 31/07/2026**
> (§5). Le corps de la note est conservé tel quel : il porte les arguments qui ont servi à
> décider, et une décision sans ses attendus est inauditable six mois plus tard.

---

## 1. Ce que dit le PDF `RAG pro les agents.pdf`

Constat d'abord : ce document est la **source de `banque-agents/REGISTRE.md`**. L'architecture
N0→N5, les noms d'agents, la répartition par niveau — tout y était déjà. Le REGISTRE en est
la transcription, et la phase 1 du créateur en a instancié 11 agents sur les 16 du pipeline.

Il n'y a donc presque rien de *nouveau* à intégrer, mais trois choses à récupérer.

### 1.1 Agents du PDF encore à l'état concept

| Agent | Niveau | Ce que le PDF en dit | Statut REGISTRE |
|---|---|---|---|
| `reformulateur` | N1 | expansion de requête, correction orthographique, décomposition en sous-questions | ⚪ concept |
| `cache` | N1 | sert les requêtes récurrentes (Redis ou clé-valeur) | ⚪ concept |
| `feedback` | N5 | collecte ✅/❌, met à jour les scores de pertinence | ⚪ concept |
| `apprentissage` | N5 | ajuste embeddings et prompts (A/B testing) | ⚪ concept |
| `maintenance` | N5 | surveille les dépendances, déclenche des alertes | ⚪ concept |

### 1.2 Une lacune du REGISTRE révélée par le PDF

Le PDF place au **niveau 0** un **agent d'interface** (sessions, historique utilisateur,
conversion voix/image → texte). Le REGISTRE ne l'a jamais repris : son N0 ne contient que
le monitoring. C'est la deuxième lacune trouvée après `ingestion-chunking`.

Ce n'est pas un détail : c'est lui qui porte l'**historique de conversation**, dont le
`reformulateur` a besoin pour résoudre les questions de suite (« et pour le coccyx ? »).
Sans lui, chaque question est orpheline.

### 1.3 Détails techniques du PDF non repris en phase 1

- **Filtres par métadonnées sur la recherche vectorielle** (« Optimisation : filtres par
  métadonnées — domaine, date »). Pas implémenté, peu coûteux, et directement utile :
  restreindre la recherche à un sous-ensemble de sources. Chroma le sait faire nativement.
- **Fusion par score pondéré**, en alternative à la RRF. Le PDF donne les deux. Un
  paramètre `strategie: rrf | score` dans la brique `fusion` rendrait le choix mesurable.
- **Principe de repli** (« si le reranker plante, on utilise les chunks bruts »). Aujourd'hui
  une brique qui lève une exception arrête tout le pipeline. Un mode `sur_erreur:
  arreter | ignorer` par brique rendrait le pipeline robuste — et c'est **indispensable**
  pour un fonctionnement h24 sans surveillance.
- **Variantes** listées par le PDF, hors périmètre pour l'instant : traduction (nllb-200),
  streaming, chiffrement homomorphe, multimodal (CLIP), agent d'outils (function calling).

---

## 2. Ce que demande le mainteneur en plus (26/07)

### 2.1 Un agent mémoire / apprentissage

> « se souviendrait du travail de l'agent et de la pertinence des choix faits, une mémoire
> pour ne pas refaire les mêmes erreurs et affiner l'agent au fil du temps »

**Attention, ce n'est pas le `feedback` du PDF.** Deux mémoires différentes :

- `feedback` (N5, PDF) mémorise ce que l'**utilisateur** pense des **réponses**.
- Ce que le mainteneur décrit mémorise ce que l'**agent** a **essayé** et ce que ça a donné.

C'est une mémoire d'**expériences**, pas de réponses. Un agent nouveau, absent du PDF
comme du REGISTRE. Nom proposé : `memoire-experiences` (N5).

Ce qu'elle doit retenir, par expérience : le paramètre touché, sa valeur avant/après, le
score obtenu, l'écart-type du bruit à ce moment-là, le verdict (gain / neutre / régression),
et le corpus concerné. Trois usages qui en découlent :

1. **Ne pas refaire.** Avant de tester une configuration, vérifier si elle a déjà été
   évaluée sur ce corpus. Sur une boucle h24, c'est le premier poste d'économie.
2. **Transférer.** « Sur les trois derniers corpus, `pool: 20` a battu `pool: 10` » devient
   un a priori pour le corpus suivant. C'est là que l'agent « s'affine au fil du temps ».
3. **Rendre compte.** Un historique lisible de *pourquoi* la configuration actuelle est
   celle-là. Sans ça, personne — pas même le mainteneur — ne peut auditer six mois de réglages.

Point de vigilance : une mémoire d'expériences est aussi une mémoire d'**erreurs de
mesure**. Si le jeu d'éval change, les scores anciens ne sont plus comparables. Chaque
entrée doit donc porter la **version du jeu d'éval** qui l'a produite, sinon la mémoire
deviendra une source de fausses certitudes.

### 2.2 Un agent suggestif

> « un agent géré par le modèle qui serait suggestif en proposant des améliorations à son
> fonctionnement »

Un agent qui lit les traces, la mémoire d'expériences et les échecs, et **formule des
hypothèses en langage naturel** : « les citations orphelines augmentent depuis 3 jours,
le `k` du constructeur de contexte est peut-être trop large ».

C'est le seul endroit du système où un LLM est justifié pour raisonner *sur* le système.
Nom proposé : `suggestion-amelioration` (N5).

**Garde-fou non négociable** : il propose, il n'applique **jamais**. Un agent qui modifie
sa propre configuration sur la base de son propre raisonnement, sans mesure, est exactement
ce que la méthode du projet interdit (« mesurer, pas supposer »). Sa sortie est une file de
propositions ; le régleur les **teste** ; la mesure décide.

---

## 3. Le problème de fond : autonomie sur VPS

> « l'agent créateur itère sur lui-même jusqu'à ce que le gain de l'itération approche de 0 »

### 3.1 Le piège du critère d'arrêt

« Je m'arrête quand le gain passe sous ε » suppose que la mesure est stable. Elle ne l'est
pas : deux exécutions de la **même** configuration, jugées par un LLM sur 7 questions, ne
donnent pas le même score.

**Il faut donc mesurer le bruit avant de mesurer un gain.** Exécuter la configuration de
référence 3 à 5 fois, relever la dispersion. Tout écart inférieur à cette dispersion n'est
pas un gain — c'est du hasard. C'est la leçon de `tools/mesurer_ram.py` (v1 non
reproductible, remplacée) transposée à l'évaluation.

Et le critère doit porter sur un **balayage complet**, pas sur un pas isolé :

> arrêt quand une passe entière sur tous les paramètres n'a produit aucun gain
> supérieur à 2 écarts-types du bruit.

Un pas peut échouer par malchance. Une passe complète qui ne trouve rien est un vrai plateau.

### 3.2 Le second piège : le surapprentissage sur le jeu d'éval

Avec 7 questions et des centaines d'itérations, l'agent trouvera une configuration excellente
**sur ces 7 questions** et pas ailleurs. Parade classique, que le mainteneur connaît (`identite.md`,
« Évaluation RAG (RAG Triad, dev/test) 8/10 ») : régler sur **dev**, ne confirmer que sur
**test**, et ne toucher au test qu'au moment de promouvoir.

### 3.3 L'évaluation à deux vitesses

Un juge LLM coûte une génération par question : 5 à 10 minutes pour 7 questions. Une boucle
h24 qui ferait ça à chaque essai plafonnerait à ~100 essais par jour. Trop peu.

- **Boucle interne, sans LLM** : recall@k, MRR contre un jeu de référence
  question → passages attendus. Déterministe, quelques secondes, des milliers d'essais par
  jour. Couvre tout ce qui touche au recall et au classement, soit la majorité des paramètres.
- **Barrière de promotion, avec LLM** : la triade RAG par `agent-evaluation-rag`, déclenchée
  seulement quand un candidat prétend battre le champion.
- **Comparaison différentielle** : ne juger que les questions où deux configurations
  divergent. Si A et B renvoient les mêmes passages sur 5 questions sur 7, le juge n'en
  traite que 2. Sur des réglages fins, souvent 80 % du coût en moins.

**Obstacle réel** : il n'existe aucun jeu de référence étiqueté. `questions_tuteur.json` a
ses champs `reponse_or` vides. Trois voies, ✅ tranchées le 31/07 en faveur de la deuxième,
corrigée — *le juge propose, le mainteneur relit et corrige, puis on gèle et on versionne* : annotation manuelle d'un petit
dev+test (fiable, quelques heures) ; génération par le juge LLM puis relecture et gel
(rapide, faillible — les erreurs du juge deviendraient la vérité optimisée pendant des
semaines) ; consensus entre configurations validées (aucun travail manuel, mais conservateur
par construction : l'agent ne découvrira jamais un bon passage qu'aucune config actuelle
ne trouve).

### 3.4 Stratégie de recherche

- **Descente par coordonnées, en passes** — une variable à la fois, balayage répété. C'est
  la méthode que le mainteneur a validée à la main le 25/07. Interprétable (on peut dire *pourquoi*
  un paramètre a changé), et elle donne le critère d'arrêt du §3.1. Risque : optima locaux,
  interactions manquées.
- Grille ou aléatoire — plus large, parallélisable, mais coûteux et sans explication.
- Optimisation bayésienne — économe en essais, mais boîte noire : incompatible avec la règle
  de gate (« le mainteneur doit pouvoir expliquer chaque composant »).

Recommandation : descente par coordonnées, avec la mémoire d'expériences pour éviter de
réessayer ce qui a déjà été mesuré.

### 3.5 Enveloppe d'autonomie — ✅ tranché le 31/07

Trois classes de paramètres, à coût très inégal :

| Classe | Exemples | Coût d'un essai |
|---|---|---|
| Libre | `top_k`, `pool`, `k`, `garde`, `seuil_doublon`, RRF `k`, `temperature` | secondes, réversible |
| Réindexation | `max_mots`, `overlap`, `precision` de l'embeddeur | minutes à heures |
| Humain | modèle d'embedding, licence, politique RGPD, promotion en production | irréversible ou contractuel |

**Décision : autonomie totale sur la classe « libre » uniquement.** Réindexation et
changement de modèle : l'agent propose, le mainteneur tranche.

Raison : un essai de la classe libre coûte des secondes et est réversible, donc une erreur
de l'agent ne coûte rien. Un essai avec réindexation coûte des minutes à des heures **et
rend les mesures antérieures non comparables** — c'est le second coût, le plus cher, et
celui qu'on oublie. Réserve assumée : `max_mots` et `overlap` sont probablement parmi les
paramètres les plus déterminants du pipeline, et ils restent hors d'atteinte de l'agent.
On s'interdit volontairement le levier le plus fort tant qu'on ne sait pas mesurer proprement.

### 3.6 Garde-fous h24 (indispensables, non négociables)

- Budget : nombre d'itérations, réindexations par jour, temps machine.
- Champion toujours conservé ; promotion uniquement si le jeu **test** confirme.
- Retour arrière automatique sur régression.
- Journal append-only de chaque essai.
- **Interrupteur** : la présence d'un fichier `STOP` arrête la boucle proprement.
- Mode `sur_erreur: ignorer` par brique (§1.3) : sans repli, une exception à 3 h du matin
  laisse le système mort jusqu'au lendemain.

---

## 4. Point d'architecture — où vit la boucle — ✅ tranché le 31/07

Ce que le mainteneur décrit (« itère sur lui-même ») est **l'agent régleur**, son groupe D. Pas le
créateur.

Mettre la boucle dans le créateur lui ôterait sa qualité de brique stable : plus rien ne
pourrait s'appuyer dessus, puisqu'il se modifierait seul. `AGENTS.md` §2.2 : un agent, une
responsabilité.

En revanche, un **mode automatique appartient bien au créateur** : face à un corpus neuf,
analyser (langue, volume, longueur moyenne des documents), consulter `modeles.yaml`, et poser
un **profil de départ justifié** — puis laisser le régleur l'affiner. C'est le
« recommander, puis choisir seul » côté créateur, et il reste déterministe donc auditable.

---

## 5. Décisions — ✅ arbitrées le 31/07/2026

| # | Décision | Arbitrage | Écarté, et pourquoi |
|---|---|---|---|
| 1 | Où vit la boucle h24 | **Régleur séparé** (groupe D) + **mode automatique** dans le créateur | Tout dans le créateur : il deviendrait une cible mouvante, et le témoin de non-régression 7/7 perdrait son sens |
| 2 | Mode d'évaluation | **Deux étages** : recall@k / MRR sans LLM en boucle interne, triade RAG à la barrière de promotion | Triade partout : ~100 essais/jour, et le juge étant bruité il faudrait 3-5 répétitions, soit ~20 essais utiles |
| 3 | Jeu de référence | **Le juge propose, le mainteneur relit et corrige, on gèle et on versionne** — dev et test séparés dès la v1 | Annotation intégrale : plusieurs heures sur le chemin critique. Consensus : conservateur par construction, l'agent optimiserait vers son propre point de départ |
| 4 | Enveloppe d'autonomie | **Classe « libre » seulement** — aucune réindexation sans validation humaine | Tout sous quota : un essai coûte des heures et invalide les mesures antérieures |
| 5 | Options du profil `total` | **Repli sur erreur · filtres par métadonnées · fusion pondérée** dans cette phase ; **reformulateur + agent d'interface** retenus mais reportés | Rien d'écarté : le lot 6 est différé, pas abandonné (voir la réserve ci-dessous) |
| 6 | Support de la mémoire | **JSONL append-only** | Chroma : « déjà testé ? » est une égalité, pas une similarité — une réponse « à peu près » serait pire que pas de réponse. SQLite : binaire, mal versionné, illisible à l'œil |

### Réserves consignées le 31/07

**Le jeu de référence est le vrai chemin critique.** La décision 2 ne fonctionne pas sans
lui. Tant qu'il n'existe pas, chaque lot de code est écrit à l'aveugle : on saura que le
code tourne, pas qu'il sert. Session dédiée, avec `agent-evaluation-rag`, **à tenir après**
la première trace complète (`createur.py --traces`, jamais lancée) — le juge doit proposer à
partir des passages réellement remontés, pas dans le vide.

**Toute nouvelle option est désactivée par défaut.** C'est la condition pour que la
non-régression 7/7 garde sa valeur de témoin. Un profil `moyen` dont le comportement change
parce qu'on a ajouté une option ailleurs, et le projet perd sa seule référence fiable.

**Le lot 6 (reformulateur + agent d'interface) est reporté, pas annulé.** Deux agents
entiers, un appel LLM de plus par requête sur une machine où le LLM est déjà le goulot, et
surtout : non mesurable tant que le jeu de référence n'existe pas. L'écrire maintenant
reviendrait à l'ajouter sans jamais pouvoir dire s'il sert.

### Ordre d'exécution retenu

1. Repli sur erreur (`sur_erreur: arreter | ignorer` par brique)
2. Fusion par score pondéré (`strategie: rrf | score`)
3. Filtres par métadonnées
4. Mémoire d'expériences en JSONL
5. Mode automatique du créateur
6. Points ouverts de la phase 1 (`total.yaml` en float16 ; nom de l'embeddeur en métadonnées)
7. Vérification : tests de logique pure + non-régression 7/7 intacte
8. Mise à jour de `banque-agents/` et du handoff
