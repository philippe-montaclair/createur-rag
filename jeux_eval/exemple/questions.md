# Jeu d'évaluation — corpus_exemple

25 questions écrites à la main sur les sept documents de `corpus_exemple/`,
**avant toute interrogation du système**. Les réponses sont vérifiables ligne à
ligne dans les documents. Composition : 6 factuelles, 5 multi-documents,
5 pièges, 3 datées, 6 hors-corpus.

Les six hors-corpus sont la partie la plus importante du jeu : elles sont
formulées comme les autres, portent sur le même domaine, et n'ont aucune réponse
dans le corpus. Elles seules mesurent si le système sait dire qu'il ne sait pas.

---

## Q1 · factuelle

Question : Tous les combien faut-il remplacer le filtre à air du TX-40 ?
Réponse : Toutes les 100 heures de fonctionnement, référence `FA-2210`.
Source : tondeuse_TX40.md

## Q2 · factuelle

Question : Quelle est la capacité du réservoir de carburant du TX-40 ?
Réponse : 5,7 litres.
Source : tondeuse_TX40.md

## Q3 · factuelle

Question : Dans quelle proportion se prépare le mélange deux temps du H-120 ?
Réponse : 50:1, soit 20 ml d'huile deux temps par litre d'essence.
Source : taille_haies_H120.md

## Q4 · factuelle

Question : Quelle pression faut-il aux roues avant du TX-40 ?
Réponse : 1,0 bar, contrôlée à froid avant le démarrage.
Source : tondeuse_TX40.md

## Q5 · factuelle

Question : Au bout de combien d'heures la première vidange du TX-40 est-elle due ?
Réponse : 5 heures après la mise en service. La périodicité de 50 heures ne
  s'applique qu'ensuite.
Source : tondeuse_TX40.md

---

## Q6 · multi_documents

Question : Pourquoi le débranchement du capuchon de bougie est-il particulièrement
  impératif sur le TX-40 ?
Réponse : Parce que le TX-40 n'a pas de coupure automatique de lame au relevage
  du siège — sécurité présente seulement sur les modèles postérieurs à 2023. Tant
  que la bougie est connectée, un démarrage intempestif reste possible, et la
  procédure P-01 supplée cette absence.
Source : procedure_atelier.md
Autre source : tondeuse_TX40.md

## Q7 · multi_documents

Question : Quelle référence de pièce est réellement commune au TX-40 et au H-120 ?
Réponse : La bougie `BG-441`. La référence `FA-2210` figure dans les deux notices
  mais ne désigne pas la même pièce, ce que rappelle la procédure P-04.
Source : taille_haies_H120.md
Autre source : procedure_atelier.md

## Q8 · multi_documents

Question : Combien de temps un mélange deux temps peut-il être conservé avant
  d'être écarté ?
Réponse : Trente jours. Au-delà il est vidangé et traité en déchet, jamais versé
  dans une machine à essence pure.
Source : taille_haies_H120.md
Autre source : procedure_atelier.md

---

## Q9 · piege

Question : Le filtre à air `FA-2210` est-il utilisable indifféremment sur le TX-40
  et sur le H-120 ?
Réponse : Non. Sur le H-120, `FA-2210` désigne le filtre d'origine, remplacé
  depuis par le `FA-3105`, de dimensions différentes. Monter un `FA-2210` sur un
  H-120 laisse passer les poussières.
Source : taille_haies_H120.md
Autre source : procedure_atelier.md
Erreur attendue : répondre « oui, c'est la même référence » — la chaîne récupère
  les deux notices, y lit le même code `FA-2210`, et conclut à l'identité de la
  pièce. C'est l'erreur que la procédure P-04 a été écrite pour empêcher chez les
  agents ; elle piège un système exactement de la même façon.

## Q10 · piege

Question : Tous les combien faut-il nettoyer le filtre à air du TX-40 ?
Réponse : La notice du TX-40 ne prévoit aucun nettoyage du filtre à air, mais son
  remplacement toutes les 100 heures. Le nettoyage toutes les 25 heures est une
  opération du H-120.
Source : tondeuse_TX40.md
Erreur attendue : répondre « toutes les 25 heures », en transposant au TX-40 une
  périodicité qui appartient à l'autre machine. La question présuppose une
  opération inexistante : un bon système corrige la prémisse au lieu de la suivre.

## Q11 · piege

Question : Tous les combien la courroie `CR-118` du `ATL-007` doit-elle être
  contrôlée aujourd'hui ?
Réponse : Toutes les 80 heures. La notice prévoit 100 heures, mais après la
  rupture du 22/03/2025 à 445 heures sur carter colmaté, le contrôle a été avancé
  à 80 heures en dérogation à la notice.
Source : registre_interventions.md
Autre source : tondeuse_TX40.md
Erreur attendue : répondre « toutes les 100 heures » d'après la seule notice. Le
  registre prime sur le constructeur, et rien dans la notice ne le signale : il
  faut avoir récupéré les deux documents et su lequel fait foi.

---

## Q12 · datee

Question : Au 1er février 2025, quelle était la périodicité de contrôle de la
  courroie du `ATL-007` ?
Réponse : 100 heures, celle de la notice. La dérogation à 80 heures ne date que
  du 22 mars 2025.
Source : tondeuse_TX40.md
Autre source : registre_interventions.md

## Q13 · datee

Question : Quelle bougie équipait le `ATL-014` au 1er avril 2025 ?
Réponse : Sa bougie d'origine. Le remplacement par une `BG-441` n'a eu lieu que
  le 11 avril 2025, à 104 heures au compteur.
Source : registre_interventions.md

---

## Q14 · hors_corpus

Question : Tous les combien faut-il remplacer le filtre à carburant du TX-40 ?
Réponse : SANS_REPONSE
Source : —
Erreur attendue : répondre « toutes les 200 heures, référence `FC-076` » — c'est
  la périodicité du H-120. Aucun filtre à carburant n'est mentionné pour le TX-40.

## Q15 · hors_corpus

Question : Quel est le numéro de parc du souffleur thermique de l'atelier ?
Réponse : SANS_REPONSE
Source : —
Erreur attendue : inventer un numéro sur le modèle de `ATL-007` et `ATL-014`.
  Aucun souffleur ne figure au parc décrit.

## Q16 · hors_corpus

Question : Quelle est la puissance en chevaux du moteur du TX-40 ?
Réponse : SANS_REPONSE
Source : —
Erreur attendue : convertir la cylindrée de 452 cm³ en une puissance plausible.
  La cylindrée est donnée, la puissance ne l'est pas.

## Q17 · hors_corpus

Question : Quel agent est intervenu sur le `ATL-007` le 15 août 2025 ?
Réponse : SANS_REPONSE
Source : —
Erreur attendue : répondre « R. Vasseur », qui signe toutes les autres
  interventions sur cette machine. Aucune ligne du registre ne porte cette date.

## Q18 · hors_corpus

Question : Quelle huile est préconisée pour le graissage des lames du TX-40 ?
Réponse : SANS_REPONSE
Source : —
Erreur attendue : répondre « graisse lithium », qui est la préconisation du
  H-120. Le TX-40 n'a pas d'opération de graissage des lames : il a un affûtage
  et un remplacement.

---

## Q19 · piege

Question : Combien de temps faut-il attendre après l'arrêt moteur avant
  d'intervenir sur une machine thermique ?
Réponse : Dix minutes. La version 2023 disait cinq minutes, mais elle est abrogée
  depuis le 1er janvier 2025.
Source : procedure_atelier.md
Autre source : procedure_atelier_2023_abrogee.md
Erreur attendue : répondre « cinq minutes ». Les deux procédures se ressemblent
  au point que la récupération par similarité les classe côte à côte ; rien dans
  le texte de l'étape elle-même ne dit laquelle est en vigueur. Le système doit
  avoir lu le bandeau d'abrogation, pas seulement le paragraphe pertinent.

## Q20 · piege

Question : Le débranchement du capuchon de bougie est-il obligatoire avant une
  intervention ?
Réponse : Oui, depuis le 1er janvier 2025 — c'est l'étape 2 de la procédure P-01
  en vigueur. Il n'était que recommandé dans la version 2023.
Source : procedure_atelier.md
Autre source : procedure_atelier_2023_abrogee.md
Erreur attendue : répondre « recommandé mais pas obligatoire », d'après le texte
  abrogé.

## Q21 · multi_documents

Question : Quelles machines de l'atelier partagent réellement le même filtre à air ?
Réponse : Le T-85 et le H-120, tous deux en `FA-3105` — d'origine sur le T-85, en
  remplacement sur le H-120. Le TX-40 utilise un `FA-2210`, qui porte la même
  référence que l'ancien filtre du H-120 sans être la même pièce.
Source : tronconneuse_T85.md
Autre source : taille_haies_H120.md

## Q22 · multi_documents

Question : Pourquoi le code couleur vert et rouge des bidons a-t-il été imposé ?
Réponse : À la suite de l'incident du 5 septembre 2024 : le moteur du `ATL-014` a
  été détruit par de l'essence pure versée à la place du mélange 50:1, les deux
  bidons portant des étiquettes manuscrites décolorées. Machine immobilisée sept
  semaines.
Source : registre_interventions_2024.md
Autre source : procedure_atelier_2023_abrogee.md

## Q23 · factuelle

Question : Tous les combien contrôle-t-on le frein de chaîne du T-85 ?
Réponse : Avant chaque usage. C'est le seul organe du parc dont le contrôle ne
  suit pas un compteur horaire.
Source : tronconneuse_T85.md

## Q24 · datee

Question : Au 1er juin 2024, un mélange deux temps préparé quarante-cinq jours
  plus tôt pouvait-il être utilisé ?
Réponse : Oui. La limite était alors de soixante jours. Elle n'est passée à
  trente jours qu'au 1er janvier 2025.
Source : procedure_atelier_2023_abrogee.md
Autre source : procedure_atelier.md

## Q25 · hors_corpus

Question : Quelle est la longueur du guide du T-85 exprimée en pouces ?
Réponse : SANS_REPONSE
Source : —
Erreur attendue : convertir les 40 cm en pouces. La conversion est triviale, mais
  elle n'est pas dans le corpus : un système qui répond « 16 pouces » a calculé,
  pas récupéré. C'est un cas limite volontaire — la bonne réponse peut se
  discuter, la trace doit montrer d'où elle vient.
