# Créateur de RAG

[![contrôles](https://github.com/philippe-montaclair/createur-rag/actions/workflows/controles.yml/badge.svg)](https://github.com/philippe-montaclair/createur-rag/actions/workflows/controles.yml)

Tu as un dossier de documents et tu veux pouvoir l'interroger en langage naturel,
sur ta machine, sans qu'ils sortent de chez toi. `createur.py --source mon_dossier`
construit la chaîne complète — découpage, index, récupération, génération sourcée —
et te rend un objet avec une méthode `interroger()`.

Le même moteur sert un tuteur de formation, un assistant juridique ou une base
documentaire d'artisan. **Seul le profil change** : la chaîne est une liste ordonnée
de briques dans un fichier YAML, pas du code.

## Pour qui

- **Tu montes un RAG pour un client** et tu ne veux pas réécrire la même chaîne à
  chaque domaine — tu veux partir d'un plancher qui marche et régler à partir de là.
- **Tu veux savoir ce que chaque brique t'apporte réellement.** Le profil `minimal`
  existe pour ça : c'est le niveau contre lequel on mesure les autres. Une brique
  qui ne bat pas le plancher n'a pas à être dans la chaîne.
- **Tes documents ne doivent pas quitter la machine.** Tout tourne en local, via
  Ollama. Aucun appel sortant.

## Les trois profils

| | `minimal` | `moyen` | `total` |
|---|---|---|---|
| Briques | 5 | 8 | 10 |
| Ce que ça ajoute | le plus petit RAG qui réponde | BM25 + fusion RRF + reranking cross-encoder | routeur en amont, validateur de chunks en aval |
| Modèles chargés | l'embeddeur seul (~1 Go en float32) | + un cross-encoder (~211 Mo en float16) | idem `moyen` |
| À quoi ça sert | plancher de comparaison, machines contraintes | **le défaut** — reproduit `tuteur-local` à l'identique, sert de témoin de non-régression | corpus hétérogènes, où trier la question et filtrer les chunks paie |

Une mesure réelle plutôt qu'une promesse : sur `moyen`, décharger le reranker entre
deux questions fait passer le temps total de **12 197 ms à 8 274 ms** — soit
−3 923 ms pour un bruit de 203 ms sur 6 mesures, à réponse identique. Le détail du
format et de la lecture est dans [`MEMOIRE_FORMAT.md`](MEMOIRE_FORMAT.md), et la
ligne brute dans `memoire.exemple.jsonl`. Le fichier de mesures complet n'est pas
publié : il porte le nom du corpus d'un client.

## État

Les 218 assertions de `tests/test_briques.py` et `tests/test_regleur.py` montent
les briques, les trois profils et la mémoire de réglage **sans aucun modèle, sans
Ollama et sans index** — PyYAML est leur seule dépendance, parce que les profils
sont des fichiers YAML. C'est exactement ce que fait la CI :

```bash
pip install pyyaml
python3 tests/test_briques.py     # 179 réussis, 0 échoués, ~1 s
python3 tests/test_regleur.py     #  39 réussis, 0 échoués
```

`tests/test_non_regression.py` est d'une autre nature : il exige `chromadb` et une
collection déjà indexée, donc il ne tourne pas en CI et ne peut pas tourner chez
toi sans corpus. C'est le témoin 7/7, il se lance à la main.

**Phase 1 — local uniquement.** Le déploiement VPS est une étape séparée et
ultérieure. Ce qui manque aussi, et c'est dit franchement : il n'y a pas encore de
`requirements.txt` ni de corpus d'exemple livré, donc l'installation demande encore
de suivre la section ci-dessous à la main.

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
pip install chromadb sentence-transformers rank_bm25 ollama pyyaml --break-system-packages
pip install pdfplumber python-docx --break-system-packages   # selon tes fichiers
ollama serve && ollama pull qwen3:8b
```

## Usage

```bash
# Indexer un dossier et poser des questions
python createur.py --source ./mes_documents --collection mon_corpus --profil moyen

# Réutiliser un index déjà construit
python createur.py --collection mon_corpus --profil total --pas-de-reindex

# Une seule question, avec le détail des temps par brique
python createur.py --collection mon_corpus --question "Ma question ?" --traces
```

En Python — c'est l'usage qui compte, parce que c'est celui des deux autres agents :

```python
from createur import creer_rag

rag = creer_rag("./mes_documents", profil="total", collection="mon_corpus")
r = rag.interroger("Ma question ?")

r["reponse"]    # le texte
r["citations"]  # ['[1] cours.pdf p.12', ...]
r["passages"]   # les chunks retenus — pour l'agent évaluateur
r["bilan"]      # temps par brique, goulot, ids récupérés — pour l'agent régleur
```

## Les trois niveaux

| | minimal | moyen | total |
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

```bash
python tests/test_briques.py            # 179 tests de logique pure, ~1 s, aucun modèle
python tests/test_non_regression.py --lister
python tests/test_non_regression.py --collection <ta_collection> --sans-generation
```

Le second doit tourner sur le Mac : il charge Marsilia, CamemBERT et Chroma.

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
├── profils/           minimal · moyen · total
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
