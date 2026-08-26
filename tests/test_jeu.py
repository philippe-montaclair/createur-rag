#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_jeu.py — Tests du lecteur de jeux d'évaluation (mesures/jeu.py).
==========================================================================
Logique pure : ni modèle, ni index, ni réseau. Ces tests tournent en CI.

Pourquoi ils comptent plus qu'ils n'en ont l'air : tout chiffre publié dans
MESURES.md est calculé sur ce que ce lecteur a lu. Un bloc avalé en silence,
une hors-corpus classée avec les autres, et le score annoncé porte sur une
population qui n'est pas celle qu'il prétend décrire. Ce fichier vérifie donc
surtout que le lecteur REFUSE ce qui est ambigu, au lieu de l'interpréter.

    python tests/test_jeu.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from mesures.jeu import lire_jeu, composition, separer   # noqa: E402

REUSSIS, ECHOUES = [], []


def verifier(nom: str, condition: bool, detail: str = "") -> None:
    (REUSSIS if condition else ECHOUES).append(nom)
    print(f"  {'✅' if condition else '❌'} {nom}{f'  — {detail}' if detail else ''}")


def ecrire(contenu: str) -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(contenu)
    f.close()
    return f.name


def refuse(contenu: str) -> bool:
    """Vrai si le lecteur lève ValueError sur ce contenu."""
    try:
        lire_jeu(ecrire(contenu))
        return False
    except ValueError:
        return True


print("\n1) Lecture du format")

BASE = """# préambule ignoré

## Q1 · factuelle

Question : Quelle est la capacité du réservoir ?
Réponse : 5,7 litres.
Source : notice.md

---

## Q2 · hors_corpus

Question : Quelle est la puissance en chevaux ?
Réponse : SANS_REPONSE
Source : —
"""

qs = lire_jeu(ecrire(BASE))
verifier("lit les deux questions", len(qs) == 2, f"{len(qs)} lues")
verifier("le préambule n'est pas pris pour une question", qs[0]["id"] == "Q1")
verifier("le type est relevé", qs[0]["type"] == "factuelle")
verifier("la question est relevée", qs[0]["question"].startswith("Quelle est la capacité"))
verifier("la réponse est relevée", qs[0]["reponse"] == "5,7 litres.")
verifier("les champs absents valent la chaîne vide", qs[0]["autre_source"] == "")

print("\n2) Valeurs sur plusieurs lignes")

MULTILIGNE = """## Q1 · piege

Question : Le filtre est-il commun aux deux machines ?
Réponse : Non. La référence figure dans les deux notices
  mais ne désigne pas la même pièce.
Source : notice.md
Erreur attendue : répondre oui, parce que le code
  est identique dans les deux documents.
"""
q = lire_jeu(ecrire(MULTILIGNE))[0]
verifier("une valeur indentée poursuit le champ",
         q["reponse"].endswith("la même pièce."), q["reponse"][-30:])
verifier("le champ suivant n'absorbe pas le précédent", q["source"] == "notice.md")
verifier("l'erreur attendue est complète",
         q["erreur_attendue"].endswith("dans les deux documents."))

print("\n3) Ce que le lecteur doit REFUSER")

verifier("un type inconnu est refusé",
         refuse("## Q1 · devinette\n\nQuestion : x ?\nRéponse : y\n"))
verifier("une question sans réponse écrite est refusée",
         refuse("## Q1 · factuelle\n\nQuestion : x ?\n"))
verifier("une réponse vide est refusée",
         refuse("## Q1 · factuelle\n\nQuestion : x ?\nRéponse :\n"))
verifier("une hors_corpus avec une vraie réponse est refusée",
         refuse("## Q1 · hors_corpus\n\nQuestion : x ?\nRéponse : 5,7 litres.\n"),
         "sinon le taux de refus porterait sur une population fausse")
verifier("un SANS_REPONSE sur un autre type est refusé",
         refuse("## Q1 · factuelle\n\nQuestion : x ?\nRéponse : SANS_REPONSE\n"))
verifier("un fichier sans aucune question est refusé", refuse("# rien\n\ndu texte\n"))

print("\n4) Séparation des populations")

qs = lire_jeu(ecrire(BASE))
notables, hors = separer(qs)
verifier("les notables excluent les hors-corpus", len(notables) == 1)
verifier("les hors-corpus sont isolées", len(hors) == 1 and hors[0]["id"] == "Q2")
verifier("aucune question n'est perdue dans la séparation",
         len(notables) + len(hors) == len(qs))
verifier("le drapeau sans_reponse est posé", hors[0]["sans_reponse"] is True)
verifier("et pas posé à tort", notables[0]["sans_reponse"] is False)

print("\n5) Le jeu livré avec le dépôt")

livre = RACINE / "jeux_eval" / "exemple" / "questions.md"
if livre.exists():
    qs = lire_jeu(livre)
    comp = composition(qs)
    notables, hors = separer(qs)
    verifier("le jeu d'exemple se lit sans erreur", len(qs) == 25, f"{len(qs)} questions")
    verifier("composition conforme au README",
             comp == {"factuelle": 6, "multi_documents": 5, "piege": 5,
                      "datee": 3, "hors_corpus": 6},
             str(dict(sorted(comp.items()))))
    verifier("au moins quatre hors-corpus, seuil du GABARIT", len(hors) >= 4, f"{len(hors)}")
    verifier("chaque piège annonce l'erreur attendue",
             all(q["erreur_attendue"] for q in qs if q["type"] == "piege"))
    verifier("chaque question notable cite une source",
             all(q["source"] and q["source"] != "—" for q in notables))
else:
    verifier("le jeu d'exemple est présent", False, "jeux_eval/exemple/questions.md absent")

print("\n" + "─" * 60)
print(f"{len(REUSSIS)} réussis, {len(ECHOUES)} échoués")
if ECHOUES:
    for nom in ECHOUES:
        print(f"  ❌ {nom}")
    sys.exit(1)
print("Tout est vert.")
