# Créateur de RAG

[![contrôles](https://github.com/philippe-montaclair/createur-rag/actions/workflows/controles.yml/badge.svg)](https://github.com/philippe-montaclair/createur-rag/actions/workflows/controles.yml)

Interroger un dossier de documents en langage naturel, sur sa propre machine, sans
que rien n'en sorte. `createur.py --source mon_dossier` construit la chaîne complète
— découpage, index, récupération, génération sourcée — et rend un objet muni d'une
méthode `interroger()`.

Le même moteur sert un tuteur de formation, un assistant juridique ou une base
documentaire d'artisan. **Seul le profil change** : la chaîne est une liste ordonnée
de briques dans un fichier YAML, pas du code.

**En une minute**

| | |
|---|---|
| **Ce que c'est** | Un moteur de RAG local générique. La chaîne est une liste ordonnée de briques dans un fichier YAML : on change de profil, pas de code. |
| **Pour qui** | Monter un RAG sur les documents d'un métier sans réécrire la chaîne à chaque fois — et savoir ce que chaque brique apporte vraiment. |
| **État** | **Actif.** C'est le dépôt courant ; les deux RAG de domaine publiés avant lui en sont les prototypes. |
| **Ce qui est mesuré** | Trois profils × 25 questions sur le corpus d'exemple livré : RAGAS en local, latences, refus hors-corpus. Daté et rejouable (`COMPARAISON.md`). 271 assertions en intégration continue. |
| **Ce que ça ne fait pas** | Rien à distance : Ollama et les modèles tournent sur votre machine. Pas d'orchestration autonome — la phase 3 est conçue, pas implémentée. |

## Pour qui

- **Monter un RAG pour un client sans réécrire la même chaîne à chaque domaine** :
  partir d'un plancher qui fonctionne, puis régler à partir de là.
- **Savoir ce que chaque brique apporte réellement.** Le profil `minimal` existe pour
  cela : c'est le niveau contre lequel les autres se mesurent. Une brique qui ne bat
  pas le plancher n'a rien à faire dans la chaîne.
- **Garder les documents sur la machine.** Tout tourne en local, via Ollama. Aucun
  appel sortant.

## Une vraie sortie, telle qu'enregistrée

Deux questions de la campagne du 26/08/2026, profil `minimal`, corpus `corpus_exemple` (notices d'un atelier d'espaces verts), modèle `qwen3-8b` en local. Relevé brut dans `mesures/runs/minimal.json`, ni retouché ni reformulé.

**La question à laquelle le système doit répondre :**

```
Question   Tous les combien faut-il remplacer le filtre à air du TX-40 ?

Réponse    Il faut remplacer le filtre à air du TX-40 toutes les
           100 heures [2].
Citations  [2] tondeuse_TX40.md
Attendu    Toutes les 100 heures de fonctionnement, référence FA-2210.   ✔
```

**La question à laquelle il doit refuser de répondre :**

```
Question   Tous les combien faut-il remplacer le filtre à carburant
           du TX-40 ?

Piège      la notice du H-120 donne « toutes les 200 heures, réf. FC-076 ».
           Le TX-40 n'a aucun filtre à carburant documenté. Un modèle qui
           répond de mémoire attrape la périodicité du mauvais engin.

Réponse    La notice d'entretien du TX-40 ne mentionne pas la périodicité
           de remplacement du filtre à carburant [2]. Par conséquent, il
           n'est pas possible de répondre à cette question en se basant
           uniquement sur les extraits fournis.
Citations  [2] tondeuse_TX40.md
Attendu    SANS_REPONSE                                                  ✔
```

Sur les 25 questions du jeu, 6 sont de ce type — des pièges où la réponse plausible se trouve dans le corpus mais concerne un autre matériel. Les trois profils les refusent 6 fois sur 6. C'est la propriété qui décide si un tel système est utilisable en atelier ou non : le coût d'une réponse fausse et fluide est plus élevé que celui d'une absence de réponse.

Le détail des 25 questions, les scores RAGAS et les latences des trois profils sont dans `MESURES_minimal.md`, `MESURES_moyen.md`, `MESURES_complet.md` et `COMPARAISON.md`.

## Les trois profils

| | `minimal` | `moyen` | `complet` |
|---|---|---|---|
| Briques | 5 | 8 | 10 |
| Ce que ça ajoute | le plus petit RAG qui réponde | BM25 + fusion RRF + reranking cross-encoder | routeur en amont, validateur de chunks en aval |
| Modèles chargés | l'embeddeur seul (~1 Go en float32) | + un cross-encoder (~211 Mo en float16) | idem `moyen` |
| À quoi ça sert | plancher de comparaison, machines contraintes | **le défaut** — reproduit `tuteur-local` à l'identique, sert de témoin de non-régression | corpus hétérogènes, où trier la question et filtrer les chunks paie |

Des mesures plutôt que des promesses. Les trois profils ont été mesurés sur le
corpus d'exemple livré, 25 questions chacun, avec RAGAS sur backend Ollama local
([`COMPARAISON.md`](COMPARAISON.md), daté et reproductible) :

| | `minimal` | `moyen` | `complet` |
|---|---|---|---|
| Briques | 5 | 8 | 10 |
| Latence médiane | **8 055 ms** | 8 980 ms | 11 806 ms |
| `answer_correctness` | **0,726** | 0,705 | 0,680 |
| `answer_relevancy` | **0,663** | 0,639 | 0,645 |
| `context_recall` | 0,921 | 0,921 | 0,921 |
| `faithfulness` | 0,821 | **0,826** | **0,826** |
| Hors-corpus refusées | 6/6 | 6/6 | 6/6 |
| Pièges évités | 4/5 | 4/5 | 4/5 |

**Sur ce corpus, le plancher gagne.** BM25, la fusion RRF et le reranker ne font
bouger aucune métrique au-delà du bruit, et coûtent une à quatre secondes par
question. C'est précisément ce que le profil `minimal` existe pour rendre
visible : une brique qui ne bat pas le plancher n'a rien à faire dans la chaîne.

Le résultat inverse existe et il est publié : sur le corpus de droit locatif d'[`assistant-gestion-locative`](https://github.com/philippe-montaclair/assistant-gestion-locative) — textes de loi denses, 22 questions — le même reranking fait passer le bon passage en tête de 10/22 à 17/22. Le levier décisif là-bas ne sert à rien ici. C'est la raison d'être du profil `minimal` : sans plancher de comparaison, on aurait embarqué le reranker sur la foi de la mesure précédente.

**Et c'est un résultat sur ce corpus, pas une conclusion sur la méthode.** Sept
documents font 14 chunks : `k: 4` en retient 29 %, il n'y a presque rien à
écarter, donc les briques qui trient n'ont rien à faire. Elles sont conçues pour
des corpus hétérogènes de plusieurs milliers de chunks, où le bruit est le
problème. Un profil qui n'apporte rien ici ne prouve pas qu'il n'apporte rien —
il prouve que ce corpus ne pose pas le problème qu'il résout. La conclusion utile
est ailleurs : **il faut mesurer sur SON corpus avant de charger des modèles**,
et c'est exactement ce que cet outillage permet de faire.

Et sur le réglage, une expérience conservée en mémoire : décharger le reranker
entre deux questions fait passer le temps total de **12 197 ms à 8 274 ms** — soit
−3 923 ms pour un bruit de 203 ms sur 6 mesures, à réponse identique. Format et
lecture dans [`MEMOIRE_FORMAT.md`](MEMOIRE_FORMAT.md), ligne brute dans
`memoire.exemple.jsonl`. Le fichier de mesures complet n'est pas publié : il porte
le nom du corpus d'un client.

## État

Les 271 assertions de quatre fichiers montent les briques, les trois profils, la
mémoire de réglage et le lecteur de jeux d'évaluation **sans aucun modèle, sans
Ollama et sans index** — PyYAML est leur seule dépendance, parce que les profils
sont des fichiers YAML. C'est exactement ce que fait la CI :

```bash
pip install pyyaml
python3 tests/test_briques.py     # 179 réussis, 0 échoués, ~1 s
python3 tests/test_regleur.py     #  39 réussis, 0 échoués
python3 tests/test_jeu.py         #  25 réussis, 0 échoués
python3 tests/test_comparaison.py #  28 réussis, 0 échoués
```

`tests/test_non_regression.py` est d'une autre nature : il exige `chromadb` et une
collection déjà indexée, donc il ne tourne ni en CI ni sur une machine dépourvue de
corpus. C'est le témoin 7/7, et il se lance à la main.

Un corpus d'exemple est livré. Il décrit le parc de matériel d'un atelier
municipal **inventé pour ce dépôt** — sept documents, 14 chunks — et cette
invention est délibérée : sur des documents réels, un modèle de langue peut
répondre juste sans avoir rien récupéré, et l'évaluation mesure alors sa mémoire
plutôt que la chaîne. Ici, aucune référence n'existe hors du corpus.

```bash
python createur.py --source corpus_exemple --collection demo --profil moyen \
    --question "Tous les combien faut-il changer le filtre à air du TX-40 ?"
```

## Mesurer

En trois temps, chacun dans l'environnement qui lui convient :

```bash
# 1. produire les réponses — environnement de createur-rag
python mesures/mesurer.py --profil moyen --sans-ragas

# 2. les noter — environnement de rag-evaluation-agent
python mesures/noter_ragas.py --agent-eval ../agent_evaluation_rag

# 3. écrire le rapport — n'importe quel python
python mesures/mesurer.py --depuis-json \
    --refus-valides tous --pieges-reussis Q9,Q11,Q19,Q20
```

`mesures/runs/<profil>.json` est le seul contrat entre les étapes, et un fichier
par profil : mesurer `complet` n'efface pas la campagne `moyen`, sans quoi toute
comparaison coûterait de tout relancer — dont une demi-heure de notation. Les
étapes 3 et 4 ne réinterrogent rien : intégrer un verdict humain ou comparer
deux profils ne coûte pas une nouvelle campagne.

**Pourquoi trois environnements et pas un.** `createur-rag` a besoin de
chromadb, sentence-transformers et torch ; [`rag-evaluation-agent`](https://github.com/philippe-montaclair/rag-evaluation-agent)
a besoin de ragas, datasets et d'un `langchain-community` verrouillé sous 0.4
— au-dessus, `import ragas` casse. Les fondre dans un seul environnement, c'est
se donner un conflit de dépendances à arbitrer à chaque mise à jour de l'un ou
de l'autre. La notation tourne sur Ollama en local : **aucun appel sortant**.

L'étape 2 refuse d'écrire si RAGAS n'est pas installé dans l'environnement
courant. L'agent d'évaluation s'importe très bien sans lui — il se dégrade en
silence — et un rapport qui annoncerait une notation sans le moindre score
serait pire que pas de rapport du tout.

**Le point de méthode qui vaut le détour.** Les questions dont la réponse est
dans le corpus et les questions hors-corpus sont mesurées **séparément**, sur
deux grandeurs différentes : les premières par RAGAS (fidélité aux passages
récupérés), les secondes par le taux de refus. Les mélanger produirait un score
moyen qui *monte* quand le système se met à inventer sur les hors-corpus. C'est
`mesures/jeu.separer()` qui impose la séparation, et `tests/test_jeu.py` refuse
un jeu où une hors-corpus porterait une vraie réponse.

Le refus, lui, n'est pas automatisable honnêtement : il est approché par deux
indices structurels — absence de citation, présence d'un marqueur d'ignorance —
dont aucun n'est une preuve. Le rapport recopie donc les réponses hors-corpus
intégralement et marque le chiffre « à confirmer » tant qu'un humain n'a pas
tranché. Un taux de refus calculé par mots-clés mesurerait la liste de mots-clés.

`jeux_eval/exemple/questions.md` en donne 25 questions avec leurs réponses,
écrites avant toute interrogation du système : 6 factuelles, 5 multi-documents,
5 pièges, 3 datées et **6 hors-corpus**, ces dernières étant les seules à mesurer
si le système sait dire qu'il ne sait pas. Détail dans
[`CORPUS_EXEMPLE.md`](CORPUS_EXEMPLE.md).

**Phase 1 — local uniquement.** Le déploiement VPS est une étape séparée et
ultérieure.

## Ce que c'est vraiment

Pas du code neuf. C'est `tuteur-local/` démonté en briques indépendantes, plus deux
briques écrites de zéro. Conforme au principe d'`banque-agents/AGENTS.md` : *« on adopte
des agents existants et on les adapte — on n'écrit du neuf que si rien d'adaptable
n'existe »*.

| Brique | Niveau | Origine |
|---|---|---|
| `ingestion` (chunking, dédup, index) | N0 | `tuteur-local/ingest_tuteur.py` |
| `recherche_vectorielle` | N2 | `tuteur-local/tuteur.py` |
| `recherche_bm25` | N2 | `tuteur-local/tuteur.py` |
| `fusion` (RRF) | N2 | `tuteur-local/tuteur.py` |
| `reranker` (cross-encoder FR) | N3 | `tuteur-local/tuteur.py` |
| `constructeur_contexte` | N3 | extrait de `Tuteur.repondre()` |
| `prompt_engineering` | N4 | extrait de `Tuteur.repondre()` |
| `agent_llm` | N4 | `tuteur-local/tuteur.py` |
| `post_processing` | N4 | étendu (vérification des citations) |
| `routeur` | N1 | **neuf** |
| `validateur_chunks` | N3 | **neuf** |
| `memoire` (expériences de réglage) | N5 | **neuf** (31/07) |

9 briques déplacées, 2 écrites.

## Installation

```bash
pip install -r requirements.txt
ollama serve && ollama pull qwen3:8b
```

Les bornes de `requirements.txt` sont relevées sur un environnement où le projet
tourne — Python 3.11.15, chromadb 1.5.9, sentence-transformers 5.5.0 — et non
déduites d'une documentation. Les lecteurs de `.pdf` et `.docx` y sont commentés :
leurs imports sont paresseux, un corpus en `.txt` et `.md` n'en a pas besoin.

Il faut compter le téléchargement des modèles au premier lancement : environ 1 Go
pour l'embeddeur, 400 Mo pour le reranker du profil `moyen`, et 5 Go pour
`qwen3:8b`. Le profil `minimal` n'a besoin que du premier.

## Usage

```bash
# Indexer un dossier et poser des questions
python createur.py --source ./mes_documents --collection mon_corpus --profil moyen

# Réutiliser un index déjà construit
python createur.py --collection mon_corpus --profil complet --pas-de-reindex

# Une seule question, avec le détail des temps par brique
python createur.py --collection mon_corpus --question "Ma question ?" --traces
```

En Python — c'est l'usage qui compte, parce que c'est celui des deux autres agents :

```python
from createur import creer_rag

rag = creer_rag("./mes_documents", profil="complet", collection="mon_corpus")
r = rag.interroger("Ma question ?")

r["reponse"]    # le texte
r["citations"]  # ['[1] cours.pdf p.12', ...]
r["passages"]   # les chunks retenus — pour l'agent évaluateur
r["bilan"]      # temps par brique, goulot, ids récupérés — pour l'agent régleur
```

## Les trois niveaux

| | minimal | moyen | complet |
|---|---|---|---|
| recherche vectorielle | ✅ | ✅ | ✅ |
| BM25 + fusion RRF | | ✅ | ✅ |
| reranking cross-encoder | | ✅ | ✅ |
| routeur | | | ✅ |
| validateur de chunks | | | ✅ |
| génération sourcée | ✅ | ✅ | ✅ |
| observabilité | ✅ | ✅ | ✅ |

`moyen` reproduit exactement `tuteur-local/tuteur.py` : c'est le témoin de non-régression.
Toute option ajoutée depuis est **désactivée par défaut**, précisément pour que ce témoin
garde sa valeur : un profil `moyen` dont le comportement changerait parce qu'on a ajouté
une option ailleurs ferait perdre au projet sa seule référence fiable.

L'observabilité est active dès `minimal`, contrairement à ce que laissait entendre le
REGISTRE. Sans mesure par composant, ni l'agent évaluateur ne peut dire *où* ça casse,
ni l'agent régleur ne peut isoler l'effet d'une variable.

## Robustesse et périmètre (ajouts du 31/07/2026)

### Repli sur erreur — `sur_erreur`

Une brique qui lève une exception arrêtait tout le pipeline. Intenable pour un
fonctionnement h24 sans surveillance : une panne du reranker à 3 h du matin laissait le
système mort jusqu'au lendemain.

```yaml
  - reranker:
      garde: 8
      sur_erreur: ignorer     # arreter (défaut) | ignorer
      max_echecs: 3           # au-delà, retour forcé à 'arreter'
```

Trois choses à savoir avant de l'activer :

1. **Le contexte est restauré.** Une brique modifie le contexte en place ; si elle vide les
   passages puis échoue, attraper l'exception ne rétablit rien. Un instantané est repris
   avant chaque brique repliable, de sorte qu'une brique en échec soit *comme si elle
   n'avait pas tourné* — et non « comme si elle avait tourné à moitié ».
2. **Le vrai danger n'est pas l'erreur, c'est le silence.** Un repli transforme une panne
   bruyante en dégradation invisible. D'où le compteur : au-delà de `max_echecs` échecs
   **consécutifs**, la brique repasse d'office en `arreter`. Le repli couvre l'incident
   passager, jamais la panne installée.
3. **Seules les briques dégradables sont repliables.** Les deux recherches, le constructeur
   de contexte et `agent_llm` restent en `arreter` : sans passage ou sans modèle, il n'y a
   pas de réponse à dégrader — seulement à inventer.

Les incidents remontent au premier niveau du bilan (`bilan["erreurs"]`) et s'affichent
avec `--traces`.

### Fusion par score pondéré — `strategie`

```yaml
  - fusion:
      strategie: score        # rrf (défaut) | score
      poids: {vectorielle: 0.6, bm25: 0.4}
```

La RRF fusionne des **rangs**, la stratégie `score` fusionne des **scores normalisés**.
Tout ce que dit `fusion.py` sur l'incomparabilité des échelles reste vrai : une similarité
cosinus et un score BM25 ne s'additionnent pas. La stratégie `score` normalise donc chaque
liste en min-max sur [0,1] avant de pondérer.

Ce que cela a exigé : les scores bruts n'existaient nulle part dans le contexte — les
moteurs les calculaient et les jetaient, la RRF n'ayant besoin que des rangs. Ils sont
désormais transportés dans `ctx.scores`. Effet de bord utile : la distribution réelle des
scores devient visible dans les traces, ce qui est la condition pour enfin régler
`validateur_chunks.score_min`, désactivé depuis la phase 1 faute de pouvoir l'observer.

Laquelle des deux stratégies est la meilleure ? Personne ne le sait ici, et c'est le but :
la question est posée sous une forme mesurable.

### Filtres par métadonnées

```python
rag.interroger("Ma question ?", filtre={"domaine": "anatomie"})
```

ou `filtre:` au premier niveau du profil, comme périmètre par défaut. Le filtre de l'appel
**remplace** celui du profil (il ne s'y ajoute pas : un périmètre effectif que personne ne
peut lire quelque part est un périmètre qu'on ne contrôle pas).

Deux points de conception qui ne sont pas des détails :

- **Le filtre s'applique aux DEUX moteurs.** Chroma filtre nativement ; BM25 ne sait pas
  filtrer, le même filtre lui est donc réappliqué à la main. Ne filtrer que le vectoriel
  laisserait la fusion réintroduire les chunks exclus : le système paraîtrait cloisonné
  sans l'être. Un opérateur reconnu par Chroma mais non réimplémenté côté BM25 est
  **refusé** plutôt qu'appliqué à moitié.
- **Un filtre qui ne ramène rien ramène zéro passage.** Pas de repli sur une recherche non
  filtrée. Un filtre est une contrainte, pas une préférence — dès qu'il sert à séparer deux
  clients ou deux niveaux de confidentialité, se rabattre serait une fuite.

### Mémoire d'expériences — `memoire.py`

Agent N5 `memoire-experiences` : retient ce que l'agent a **essayé** et ce que ça a donné.
À ne pas confondre avec `feedback`, qui retient ce que l'**utilisateur** pense des réponses.

```python
from memoire import Memoire, ecart_type
mem = Memoire("memoire.jsonl")
mem.consulter(config, corpus="corpus_demo", version_jeu_eval="v1")
mem.enregistrer(corpus="corpus_demo", version_jeu_eval="v1",
                parametre="fusion.pool", avant=10, apres=20,
                score=0.90, reference=0.80, bruit=ecart_type(refs), config=config)
mem.a_priori("fusion.pool")          # ce que ce paramètre a donné sur TOUS les corpus
```

JSONL append-only. Chroma a été écarté pour une raison de fond : « cette configuration
a-t-elle déjà été testée ? » est une question d'**égalité**, pas de similarité — une réponse
« à peu près » y serait pire que pas de réponse.

Deux garde-fous portés par le code lui-même :

- **`version_jeu_eval` est obligatoire**, l'écriture est refusée sans elle. Si le jeu d'éval
  change, les scores antérieurs cessent d'être comparables ; une mémoire qui l'ignorerait
  accumulerait des certitudes fausses — et une erreur qu'on prend pour un acquis ne se
  corrige jamais.
- **Un gain n'existe qu'au-delà de 2 écarts-types du bruit.** Comparer deux scores sans
  connaître leur dispersion, c'est lire du hasard. Bruit inconnu → verdict `indetermine`,
  jamais `gain` : l'absence de bruit mesuré n'est pas une certitude, c'est une ignorance.

La mémoire ne décide rien. Elle répond « déjà vu, voici le résultat » ou « inédit » ; le
régleur choisit, la mesure tranche.

### Identité de l'index

Le nom de l'embeddeur, sa précision, le chunking et la date sont désormais inscrits dans
les métadonnées de la collection à l'indexation. C'est le **vrai** verrou : le contrôle de
dimension ne distinguait pas deux modèles de même taille de vecteur, et 768 est si répandu
que la coïncidence est la règle. Un index construit avant le 31/07/2026 démarre quand même,
avec un avertissement — seule une réindexation peut le mettre en règle.


## Régler le pipeline

Tout se règle dans `profils/*.yaml`. La clé `pipeline` est une **liste ordonnée** : on
retire une brique, on en ajoute une, on change un paramètre — sans toucher au code.
C'est la prise de l'agent régleur.

```yaml
pipeline:
  - recherche_vectorielle: {top_k: null}
  - fusion: {k: 60, pool: 10}
  - reranker: {garde: null}
  - constructeur_contexte: {k: 4}
```

**Le levier n'est pas là où on croit.** La fusion et le `top_k` agissent sur le *recall*
(faire entrer le bon passage dans la pile). Le reranker agit sur le *classement*
(remettre en ordre ce qu'on lui a donné). Si le bon passage n'a jamais été récupéré,
aucun reranker ne le fera apparaître — le levier est en amont.

## Catalogue de modèles

Les profils référencent un **alias** (`fr-finance`, `qwen3-8b`) décrit dans `modeles.yaml`,
pas un chemin Hugging Face. Le catalogue porte langue, domaine d'entraînement, paramètres,
empreinte, dimension des vecteurs, licence, disponibilité — et les **préfixes obligatoires**
de certains modèles.

```bash
python createur.py --modeles                      # tout le catalogue
python createur.py --recommander embeddeurs --langue fr --ram-max 600
python createur.py --recommander llm --environnement local
```

Le catalogue **propose, il ne choisit pas** — même principe que le routeur : une règle qui
décide en silence ne peut être ni auditée, ni réglée.

Deux pièges qu'il neutralise :

- **Les préfixes muets.** La famille e5 exige `query: ` et `passage: `. Sans eux, la qualité
  chute sans le moindre message d'erreur. Le créateur les applique automatiquement d'après
  la fiche du modèle.
- **L'index incompatible.** Interroger un index avec un autre embeddeur que celui qui l'a
  construit renvoie du bruit — silencieusement, si les dimensions coïncident par hasard
  (768 est très répandu). Le créateur compare la dimension réelle du modèle à celle réellement
  stockée dans la collection et **refuse de démarrer** plutôt que de répondre n'importe quoi.

## Tests

**Les quatre que la CI exécute** — logique pure, aucun modèle, aucun index, `pyyaml` pour seule dépendance. Ils tournent en quelques secondes sur n'importe quelle machine :

```bash
python tests/test_briques.py       # 179 — montage des briques et des trois profils
python tests/test_regleur.py       #  39 — mémoire de réglage, comparabilité des mesures
python tests/test_jeu.py           #  25 — lecteur des jeux d'évaluation
python tests/test_comparaison.py   #  28 — règle du bruit du comparateur de profils
                                   # ─── 271 assertions au total
```

**Celui que la CI n'exécute pas**, et pourquoi : `test_non_regression.py` charge Chroma, Marsilia et CamemBERT sur un index déjà construit. Il ne peut pas tourner sur un exécuteur GitHub sans modèle ni collection — l'y mettre le ferait échouer en permanence, ou obligerait à installer des gigaoctets de dépendances pour un contrôle qui n'en a pas besoin. Il se lance à la main, sur la machine qui porte l'index :

```bash
python tests/test_non_regression.py --lister
python tests/test_non_regression.py --collection <nom_de_la_collection> --sans-generation
```

Ce que le badge vert prouve donc : les briques tiennent leur contrat et les profils se montent. Ce qu'il ne prouve pas : qu'une installation complète démarre, ni qu'un index existant répond toujours pareil. Ces deux-là s'éprouvent à la main.

## Structure

```
createur-rag/
├── createur.py        assembleur + ligne de commande
├── contrat.py         Passage · Contexte · Ressources · Brique
├── catalogue.py       résolution d'alias, recommandation, garde-fou d'index
├── modeles.yaml       catalogue : embeddeurs · rerankers · LLM
├── observabilite.py   agent N0, transverse
├── memoire.py         agent N5 — expériences de réglage (JSONL append-only)
├── ingestion.py       lecture, découpage, vectorisation, index
├── backends/ollama.py moteur de génération
├── briques/           une brique = un agent du REGISTRE
├── profils/           minimal · moyen · complet
└── tests/
```

## Phase 2 — pré-traitement (conçue, non implémentée)

Nettoyage, tri, métadonnées, détection de données personnelles avec politique de
rétention déclarative. Deux points sont **déjà** posés en phase 1 parce qu'ils seraient
impossibles à rattraper :

- `Passage.id` est stable (`source::locator::n`) — clé de la ré-hydratation ;
- `Passage.entites` et `Contexte.ouvrir_coffre` existent dans le contrat.

Principe retenu : pas deux corpus séparés, mais **deux vues du même chunk**. L'index
principal ne contient que du texte pseudonymisé ; un coffre chiffré garde
`chunk_id → texte en clair`. La recherche se fait toujours sur la version pseudonymisée
(la sémantique est intacte), et la ré-identification n'a lieu qu'à l'affichage, après le
LLM. Conséquence : **la donnée personnelle n'entre jamais dans le contexte du modèle**.

Briques à reprendre, déjà écrites ailleurs :
`outil-anonymisation/anonymiser_dossier.py` (regex + LLM + mapping Fernet),
`tuteur-local/audit_corpus.py` (texte inversé, chunks pauvres, doublons),
`web-scraping/src/extractor.py` + `schema_loader.py` (métadonnées à schéma déclaratif).

## Cadre

Local, RGPD par défaut : rien ne sort de la machine hors le serveur Ollama local.
Modèles FR (Marsilia, CamemBERT) sur `sentence-transformers`/MPS ; génération sur Ollama.
Sur Mac M4 / 16 Go, le reranker est déchargé avant l'appel LLM.
