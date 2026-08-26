# Comparaison des profils

Produit par `mesures/comparer_profils.py` à partir des campagnes
enregistrées dans `mesures/runs/` : `minimal`, `moyen`, `complet`.

## Latence

| Profil | médiane | moyenne | écart-type | n |
|---|---|---|---|---|
| `minimal` | **8055 ms** | 8995 ms | 2786 ms | 25 |
| `moyen` | **8980 ms** | 9618 ms | 3089 ms | 25 |
| `complet` | **11806 ms** | 12077 ms | 2372 ms | 25 |

### Écarts contre le plancher `minimal`

- `moyen` − `minimal` : **+623 ms** — **bruit** (0.2× l'écart-type)
- `complet` − `minimal` : **+3082 ms** — **bruit** (1.1× l'écart-type)

Le bruit retenu est le plus grand des deux écarts-types. En deçà de deux
écarts-types, l'écart n'est pas distinguable du hasard : c'est la règle que
`memoire.py` applique aux expériences de réglage, reprise ici telle quelle.

Tout se mesure contre `minimal` et non de proche en proche, parce que c'est
la question qui compte : **chaque brique ajoutée paie-t-elle son coût ?**
Un profil plus fourni qui ne bat pas le plancher ne mérite pas les modèles
qu'il charge.

## Qualité (RAGAS)

| Métrique | `minimal` | `moyen` (écart / `minimal`) | `complet` (écart / `minimal`) |
|---|---|---|---|
| `faithfulness` | 0.821 | 0.826 (+0.004) | 0.826 (+0.004) |
| `answer_relevancy` | 0.663 | 0.639 (-0.024) | 0.645 (-0.019) |
| `context_precision` | 0.982 | 0.977 (-0.006) | 0.977 (-0.006) |
| `context_recall` | 0.921 | 0.921 (+0.000) | 0.921 (+0.000) |
| `answer_correctness` | 0.726 | 0.705 (-0.021) | 0.680 (-0.046) |

> **Une valeur par profil, aucune répétition.** Ces écarts sont des
> indications, pas des verdicts : sans dispersion, on ne peut pas les
> distinguer de la variabilité du juge, qui est lui-même un modèle de
> langue. Conclure « tel profil est meilleur » demanderait de relancer
> chaque campagne plusieurs fois. Ce n'est pas fait, donc ce n'est pas dit.

## Refus sur les hors-corpus

| Profil | hors-corpus sans citation | sur |
|---|---|---|
| `minimal` | 3 | 6 |
| `moyen` | 3 | 6 |
| `complet` | 4 | 6 |

Indice structurel seulement. Le taux de refus qui fait foi est relevé par
lecture humaine, profil par profil, dans le rapport de chaque campagne.

## Ce que la comparaison ne dit pas

Les deux profils sont mesurés sur le **même corpus de 14 chunks**, où la
récupération est facile : `k: 4` en retient 29 %. Les briques de tri du
profil `complet` — routeur en amont, validateur de chunks en aval — sont
faites pour des corpus hétérogènes de plusieurs milliers de chunks, où le
bruit à écarter est le problème. Les juger sur un corpus où il n'y a presque
rien à écarter les dessert par construction.

Autrement dit : un profil `complet` qui n'apporte rien ici ne prouve pas
qu'il n'apporte rien. Il prouve que ce corpus ne pose pas le problème qu'il
résout.
