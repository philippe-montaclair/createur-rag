# Corpus d'exemple — atelier municipal fictif

Sept documents décrivant le parc de matériel d'un atelier municipal **qui
n'existe pas**. Ils sont écrits pour ce dépôt, sans source extérieure, et sont
couverts par la licence MIT du projet.

## Pourquoi un corpus inventé, et pas des documents libres de droits

Ce n'est pas une commodité juridique, c'est une nécessité de mesure.

Sur un corpus de documents réels — une notice de matériel du commerce, un texte
de loi, un article encyclopédique — un modèle de langue peut répondre
correctement **sans avoir rien récupéré**, parce qu'il a déjà rencontré ces
informations pendant son entraînement. Une évaluation menée sur un tel corpus ne
mesure pas la récupération : elle mesure la mémoire du modèle, et attribue au RAG
un mérite qui ne lui revient pas.

Ici, aucune référence — `TX-40`, `H-120`, les numéros de pièces, les dates du
registre — n'existe hors de ces quatre fichiers. Une réponse juste ne peut venir
que d'un passage effectivement retrouvé. C'est la condition pour que les scores
publiés veuillent dire quelque chose.

Le même raisonnement s'applique au corpus d'un client : il est inconnu du modèle,
donc il mesure la chaîne. Le corpus d'exemple reproduit cette propriété sans
exposer de matériel de tiers.

## Les sept documents

| Fichier | Ce qu'il apporte à l'évaluation |
|---|---|
| `tondeuse_TX40.md` | faits chiffrés isolés — questions factuelles simples |
| `taille_haies_H120.md` | **valeurs volontairement proches de celles du TX-40** : de quoi construire des pièges où le système doit distinguer deux machines |
| `tronconneuse_T85.md` | une troisième machine qui partage réellement une pièce avec la deuxième et pas avec la première — la question « qu'est-ce qui est commun ? » cesse d'être triviale |
| `procedure_atelier.md` | règles transverses renvoyant aux machines — questions multi-documents |
| `procedure_atelier_2023_abrogee.md` | **la version périmée de ces mêmes règles**, avec d'autres valeurs. Un système qui récupère par similarité la trouvera tout aussi pertinente : c'est le piège le plus réaliste du jeu |
| `registre_interventions.md` | entrées datées de 2025, dont une dérogation qui prime sur la notice constructeur |
| `registre_interventions_2024.md` | l'année précédente, et les deux incidents qui expliquent les révisions de procédure |

**Taille et portée.** Sept documents font 14 chunks : avec `k: 4`, une question
en récupère 29 %. C'est assez pour que la récupération discrimine, pas assez pour
en faire un banc de mesure. Ce corpus sert à faire tourner la chaîne de bout en
bout et à exercer les pièges — il ne prétend pas produire des scores
généralisables.

Le jeu d'évaluation correspondant est dans `jeux_eval/exemple/questions.md`.

## Utilisation

```bash
python createur.py --source corpus_exemple --collection demo --profil moyen \
    --question "Tous les combien faut-il changer le filtre à air du TX-40 ?"
```
