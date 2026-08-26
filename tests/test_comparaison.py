#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_comparaison.py — Tests du comparateur de profils. Logique pure.
===========================================================================
Ce que ces tests protègent : la règle qui refuse d'appeler « gain » un écart
qu'on ne sait pas distinguer du bruit. C'est la règle centrale de `memoire.py`,
reprise dans le comparateur, et c'est exactement celle qu'on a envie de
contourner le jour où un profil qu'on aime bien passe devant de trois
millisecondes.

    python tests/test_comparaison.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from mesures.comparer_profils import (qualifier, rapport, latences,        # noqa: E402
                                      moyennes_ragas, ordonner, reference)

REUSSIS, ECHOUES = [], []


def verifier(nom: str, condition: bool, detail: str = "") -> None:
    (REUSSIS if condition else ECHOUES).append(nom)
    print(f"  {'✅' if condition else '❌'} {nom}{f'  — {detail}' if detail else ''}")


def faux_run(profil: str, durees, scores=None, hors_sans_citation=0):
    """Les hors-corpus reprennent les mêmes latences que les notables : leur
    donner une valeur fixe différente fabriquerait un écart-type qui n'existe
    pas, et le test mesurerait alors le jeu d'essai au lieu du comparateur."""
    n_hors = 6
    return {
        "profil": profil,
        "notables": [{"id": f"Q{i}", "duree_ms": d, "citations": ["[1] x"]}
                     for i, d in enumerate(durees)],
        "hors_corpus": [{"id": f"H{i}", "duree_ms": durees[i % len(durees)],
                         "citations": [] if i < hors_sans_citation else ["[1] x"]}
                        for i in range(n_hors)],
        "ragas": {"averages": scores} if scores else None,
    }


# Latences resserrées autour d'une valeur : un écart-type réaliste (~15 ms),
# de quoi distinguer un vrai écart d'une fluctuation.
def autour(centre: float, n: int = 10):
    return [centre - 20 + (40 * i) / (n - 1) for i in range(n)]


print("\n1) Qualification d'un écart contre le bruit")

verifier("un écart inférieur à 2σ est du bruit", "bruit" in qualifier(100, 80))
verifier("un écart de 1,9σ est encore du bruit", "bruit" in qualifier(190, 100))
verifier("un écart de 2,0σ ne l'est plus", "significatif" in qualifier(200, 100))
verifier("un gros écart est significatif", "significatif" in qualifier(4000, 200))
verifier("le signe ne change rien", qualifier(-4000, 200) == qualifier(4000, 200))
verifier("un bruit inconnu n'est jamais déclaré significatif",
         "significatif" not in qualifier(9999, 0),
         "l'absence de bruit mesuré est une ignorance, pas une certitude")

print("\n2) Lecture des campagnes")

r = faux_run("moyen", [100.0, 200.0, 300.0])
verifier("les latences des deux populations sont réunies", len(latences(r)) == 3 + 6)
verifier("les moyennes RAGAS sont vides quand rien n'est noté", moyennes_ragas(r) == {})
verifier("et lues sous 'averages' quand elles existent",
         moyennes_ragas(faux_run("m", [1.0], {"faithfulness": 0.5}))["faithfulness"] == 0.5)

print("\n3) Ordre des profils et choix du plancher")

verifier("l'ordre suit la chaîne, pas l'alphabet",
         ordonner(["complet", "minimal", "moyen"]) == ["minimal", "moyen", "complet"],
         "alphabétiquement on aurait complet · minimal · moyen")
verifier("un profil inconnu est placé après les connus",
         ordonner(["maison", "minimal"]) == ["minimal", "maison"])
verifier("le plancher est 'minimal' quand il a été mesuré",
         reference(["minimal", "moyen", "complet"]) == "minimal")
verifier("à défaut, c'est le premier de la chaîne",
         reference(["moyen", "complet"]) == "moyen")

print("\n4) Rapport produit")

a = faux_run("moyen",   autour(1000), {"faithfulness": 0.80, "answer_relevancy": 0.60})
b = faux_run("complet", autour(1005), {"faithfulness": 0.82, "answer_relevancy": 0.58})
texte = rapport({"moyen": a, "complet": b})

verifier("les deux profils figurent au rapport",
         "`moyen`" in texte and "`complet`" in texte)
verifier("un écart minuscule sur des mesures stables est dit du bruit",
         "bruit" in texte.split("## Qualité")[0],
         "5 ms d'écart ne doit jamais passer pour un résultat")
verifier("les métriques RAGAS sont tabulées", "faithfulness" in texte)
verifier("l'écart de score est signé", "+0.020" in texte or "-0.020" in texte)
verifier("l'avertissement sur l'absence de répétition est présent",
         "aucune répétition" in texte,
         "sans dispersion, un écart de score n'est pas un verdict")
# « est meilleur » ne doit apparaître QUE dans la mise en garde, jamais dans une
# affirmation du rapport. Le test le vérifie ligne à ligne : une citation en bloc
# commence par '>', une conclusion non.
affirmations = [l for l in texte.splitlines()
                if "meilleur" in l and not l.lstrip().startswith(">")]
verifier("aucun profil n'est déclaré meilleur hors mise en garde",
         not affirmations, "; ".join(affirmations)[:80] or "aucune affirmation")
verifier("et la mise en garde, elle, est bien là",
         any("meilleur" in l and l.lstrip().startswith(">") for l in texte.splitlines()))
verifier("la limite du corpus est rappelée", "14 chunks" in texte)

c = faux_run("minimal", autour(900),  {"faithfulness": 0.70, "answer_relevancy": 0.55})
texte3 = rapport({"complet": b, "minimal": c, "moyen": a})   # volontairement désordonné
verifier("trois profils tiennent dans le rapport",
         all(f"`{n}`" in texte3 for n in ("minimal", "moyen", "complet")))
verifier("le plancher est nommé comme tel", "plancher `minimal`" in texte3)
verifier("les écarts se lisent contre le plancher, pas de proche en proche",
         "écart / `minimal`" in texte3)
verifier("les deux autres profils ont chacun leur écart de latence",
         texte3.count("− `minimal` :") == 2)
verifier("un écart de latence important est dit significatif",
         "significatif" in texte3.split("## Qualité")[0],
         "100 ms d'écart pour un bruit d'environ 12 ms")
verifier("les écarts de score sont signés contre le plancher",
         "+0.100" in texte3, "faithfulness 0,70 → 0,80")

d = faux_run("maison", autour(900))       # sans RAGAS
texte4 = rapport({"minimal": c, "maison": d})
verifier("un profil non noté n'efface pas les autres", "—" in texte4)

print("\n" + "─" * 60)
print(f"{len(REUSSIS)} réussis, {len(ECHOUES)} échoués")
if ECHOUES:
    for nom in ECHOUES:
        print(f"  ❌ {nom}")
    sys.exit(1)
print("Tout est vert.")
