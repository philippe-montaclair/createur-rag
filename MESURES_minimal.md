# Mesures

Relevé le 26/08/2026 à 20:48, profil `minimal`, corpus `corpus_exemple`,
jeu `jeux_eval/exemple/questions.md`.

Ce fichier est produit par `mesures/mesurer.py`. Il n'est pas écrit à la
main : le rejouer sur la même machine avec le même corpus doit redonner
les mêmes ordres de grandeur.

## Conditions

| | |
|---|---|
| Profil | `minimal` |
| Corpus | `corpus_exemple` — 7 documents |
| Jeu d'évaluation | `jeux_eval/exemple/questions.md` — 25 questions |
| Modèle de génération | `qwen3-8b` |
| Modèle juge (RAGAS) | `qwen3:8b` |
| Machine | Linux aarch64, Python 3.10.12 |

Composition du jeu : 3 datee, 6 factuelle, 6 hors_corpus, 5 multi_documents, 5 piege.

## Latence

- médiane : **8055 ms**
- moyenne : 8995 ms
- écart-type : 2786 ms
- min / max : 4681 / 16374 ms

L'écart-type est donné parce qu'une moyenne sans dispersion ne permet
aucune comparaison : c'est la règle que `memoire.py` impose déjà aux
expériences de réglage.

## Qualité — questions dont la réponse est dans le corpus

| Métrique | Score |
|---|---|
| `answer_correctness` | 0.726 |
| `answer_relevancy` | 0.663 |
| `context_precision` | 0.982 |
| `context_recall` | 0.921 |
| `faithfulness` | 0.821 |

Calculé par RAGAS sur les 19 questions notables,
backend Ollama local — aucun appel sortant.

Les hors-corpus sont exclues de ce calcul : « fidélité aux passages
récupérés » n'a pas de sens quand la bonne réponse est de ne rien
affirmer. Leur mesure est la section suivante.

## Refus — questions sans réponse dans le corpus

Sur 6 questions hors-corpus :

### Taux de refus : **6/6** (100%)

**Relevé par lecture humaine des réponses**, question par question. C'est
ce chiffre-là qui fait foi, et lui seul.

Les deux indices automatiques sont donnés à titre de comparaison, et
l'écart est le point intéressant :

- marqueur d'ignorance détecté : 3/6
- aucune citation produite : 3/6

> **L'heuristique se trompe de 3 cas sur 6.**
> Elle rate des refus parfaitement formulés — « la réponse ne se trouve pas
> dans les extraits fournis » n'emploie aucun des marqueurs de la liste.
> Publier le chiffre automatique aurait donné un taux faux, et allonger la
> liste de marqueurs pour le corriger reviendrait à mesurer la liste.
> C'est la raison pour laquelle ce taux est relevé à la main.

Les six réponses sont recopiées ci-dessous : un lecteur doit pouvoir
refaire le jugement sans relancer la campagne.

**Q14** ✅ refus valable — Tous les combien faut-il remplacer le filtre à carburant du TX-40 ?

> La notice d'entretien du TX-40 ne mentionne pas la périodicité de remplacement du filtre à carburant [2]. Par conséquent, il n'est pas possible de répondre à cette question en se basant uniquement sur les extraits fournis.

citations : ['[2] tondeuse_TX40.md'] · marqueur : non

**Q15** ✅ refus valable — Quel est le numéro de parc du souffleur thermique de l'atelier ?

> La question ne peut pas être répondue car aucun des extraits ne mentionne le numéro de parc d'un souffleur thermique.

citations : aucune · marqueur : non

**Q16** ✅ refus valable — Quelle est la puissance en chevaux du moteur du TX-40 ?

> La puissance en chevaux du moteur du TX-40 n'est pas mentionnée dans les extraits fournis [1], [2], [3], [4].

citations : ['[1] tondeuse_TX40.md', '[2] tronconneuse_T85.md', '[3] tondeuse_TX40.md', '[4] taille_haies_H120.md'] · marqueur : oui

**Q17** ✅ refus valable — Quel agent est intervenu sur le `ATL-007` le 15 août 2025 ?

> La question ne peut pas être répondue à partir des extraits fournis. Aucune information n'est disponible sur les interventions du `ATL-007` le 15 août 2025.

citations : aucune · marqueur : oui

**Q18** ✅ refus valable — Quelle huile est préconisée pour le graissage des lames du TX-40 ?

> La question ne se trouve pas dans les extraits fournis.

citations : aucune · marqueur : non

**Q25** ✅ refus valable — Quelle est la longueur du guide du T-85 exprimée en pouces ?

> La longueur du guide du T-85 est de 40 cm. Pour convertir cette mesure en pouces, il faut savoir que 1 pouce équivaut à 2,54 cm. Ainsi, 40 cm équivaut à environ 15,75 pouces. Cependant, cette conversion n'est pas mentionnée explicitement dans les extraits fournis. La longueur du guide est indiquée en centimètres dans l'extrait [1], mais pas en pouces. Donc, la réponse ne se trouve pas dans les extraits.

citations : ['[1] tronconneuse_T85.md'] · marqueur : oui

## Pièges — les questions écrites pour faire échouer la chaîne

### 4/5 évités

Relevé à la main. Chaque piège a été écrit **avec l'erreur attendue**,
avant toute interrogation : c'est ce qui distingue un piège d'une
question difficile. Une erreur prédite qui se produit n'est pas une
surprise, c'est une mesure.

**Q9** ✅ évité — Le filtre à air `FA-2210` est-il utilisable indifféremment sur le TX-40 et sur le H-120 ?

*Erreur attendue :* répondre « oui, c'est la même référence » — la chaîne récupère les deux notices, y lit le même code `FA-2210`, et conclut à l'identité de la pièce. C'est l'erreur que la procédure P-04 a été écrite pour empêcher chez les agents ; elle piège un système exactement de la même façon.

> Non, le filtre à air `FA-2210` n'est pas utilisable indifféremment sur le TX-40 et sur le H-120. En effet, la référence `FA-2210` **ne l'est pas** sur le H-120 — sur ce modèle, elle désigne le filtre d'origine, remplacé depuis par le `FA-3105`, de dimensions différentes. Monter un `FA-2210` sur un H-120 après remplacement laisse passer les poussières [1].

**Q10** ❌ **l'erreur attendue s'est produite** — Tous les combien faut-il nettoyer le filtre à air du TX-40 ?

*Erreur attendue :* répondre « toutes les 25 heures », en transposant au TX-40 une périodicité qui appartient à l'autre machine. La question présuppose une opération inexistante : un bon système corrige la prémisse au lieu de la suivre.

> Tous les 25 heures, il faut nettoyer le filtre à air du TX-40 [2].

**Q11** ✅ évité — Tous les combien la courroie `CR-118` du `ATL-007` doit-elle être contrôlée aujourd'hui ?

*Erreur attendue :* répondre « toutes les 100 heures » d'après la seule notice. Le registre prime sur le constructeur, et rien dans la notice ne le signale : il faut avoir récupéré les deux documents et su lequel fait foi.

> La courroie `CR-118` du `ATL-007` doit être contrôlée toutes les 100 heures [3]. Cependant, selon les observations du 22/03/2025, le contrôle a été avancé à toutes les 80 heures sur cette machine, en dérogation à la notice [1].

**Q19** ✅ évité — Combien de temps faut-il attendre après l'arrêt moteur avant d'intervenir sur une machine thermique ?

*Erreur attendue :* répondre « cinq minutes ». Les deux procédures se ressemblent au point que la récupération par similarité les classe côte à côte ; rien dans le texte de l'étape elle-même ne dit laquelle est en vigueur. Le système doit avoir lu le bandeau d'abrogation, pas seulement le paragraphe pertinent.

> La durée d'attente après l'arrêt moteur avant d'intervenir sur une machine thermique dépend de la version des procédures en vigueur. 
> 
> Selon la procédure en vigueur [1], il faut attendre **dix minutes** pour le refroidissement de l'échappement. 
> 
> En revanche, selon la version 2023 (abrogée) [2], l'attente est de **cinq minutes**. 
> 
> Cependant, comme indiqué dans [1], la version en vigueur est celle de `procedure_atelier.md`, donc **dix minutes** est la durée correcte [1].

**Q20** ✅ évité — Le débranchement du capuchon de bougie est-il obligatoire avant une intervention ?

*Erreur attendue :* répondre « recommandé mais pas obligatoire », d'après le texte abrogé.

> Oui, le débranchement du capuchon de bougie est **obligatoire** avant une intervention. Cette mesure a été rendue obligatoire à partir du 1er janvier 2025, suite à un incident de démarrage intempestif sur le `ATL-007` en mars 2024 [3]. La procédure en vigueur indique clairement que le débranchement du capuchon de bougie est une étape obligatoire [2].

## Ce que ces chiffres ne disent pas

Le corpus d'exemple fait 14 chunks : `k: 4` en récupère 29 %. Les scores
ci-dessus décrivent le comportement de la chaîne sur ce corpus-là, et ne
se transposent pas à un corpus de production de plusieurs milliers de
chunks, où la récupération devient le facteur limitant.
