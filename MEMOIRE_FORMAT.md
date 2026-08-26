# Mémoire d'expériences de réglage — format

`memoire.jsonl` est le fichier qui distingue ce moteur d'un assemblage de briques :
il garde la trace de **chaque réglage essayé, avec sa mesure et son bruit**. Le
fichier réel n'est pas publié — il porte le nom du corpus et les questions d'un
client. `memoire.exemple.jsonl` en contient une ligne réelle, corpus et question
retirés : **les chiffres, eux, sont ceux qui ont été mesurés.**

Une ligne = une expérience : un paramètre changé, tout le reste égal.

## Champs

| Champ | Rôle |
|---|---|
| `horodatage` | ISO 8601. Une mesure sans date ne vaut rien : le matériel et les modèles bougent |
| `corpus`, `version_jeu_eval` | sur quoi la mesure a été prise. Deux lignes ne se comparent que si ces deux champs sont identiques |
| `parametre` | le seul paramètre modifié, en notation `brique.parametre` |
| `avant`, `apres` | sa valeur des deux côtés |
| `grandeur`, `sens` | ce qu'on mesure et dans quel sens c'est meilleur (`plus_petit_est_mieux`) |
| `moyenne_reference_ms`, `moyenne_variante_ms`, `ecart_ms` | les deux moyennes et leur différence |
| **`bruit`** | l'écart-type des mesures de référence. **Sans lui, `ecart_ms` n'est pas un résultat** |
| **`n_mesures`** | combien de répétitions. Un écart sur n = 1 est une anecdote |
| `repartition_reference`, `repartition_variante` | le temps par brique des deux côtés — c'est là qu'on lit *où* le gain a eu lieu |
| `sorties_identiques` | **le garde-fou** : un gain de latence qui change la réponse n'est pas un gain, c'est une régression |
| `verdict` | `gain`, `perte` ou `bruit` |
| `signature` | empreinte de la configuration complète, pour retrouver les lignes comparables |

## Comment se lit une ligne

L'exemple publié dit ceci : décharger le reranker de la mémoire entre deux
questions fait passer le temps total de **12 197 ms à 8 274 ms**, soit −3 923 ms,
pour un bruit de **203 ms** sur **6 mesures**, et `sorties_identiques: true`.

L'écart vaut dix-neuf fois le bruit et la réponse n'a pas changé : c'est un gain,
pas une impression. La répartition montre où : `reranker` passe de 3 814 ms à
205 ms, `agent_llm` ne bouge quasiment pas — le coût n'était pas le calcul du
reranker, c'était son chargement.

**La règle qu'on en tire** : un écart inférieur à deux ou trois fois le bruit se
note `verdict: "bruit"` et ne se garde pas comme réglage. Une mémoire qui
n'enregistre que les gains est une mémoire qui ment.
