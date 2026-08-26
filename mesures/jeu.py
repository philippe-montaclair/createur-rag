#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mesures/jeu.py — Lecture d'un jeu d'évaluation au format `jeux_eval/GABARIT.md`.

Logique pure : aucun modèle, aucun index, aucun réseau. C'est délibéré — ce
lecteur est la pièce sur laquelle repose tout chiffre publié, il doit donc être
vérifiable en intégration continue, sur un python nu.

Le format est décrit dans `jeux_eval/GABARIT.md`. Un bloc par question :

    ## Q1 · factuelle

    Question : le texte envoyé au système
    Réponse : la bonne réponse, écrite à la main
    Source : fichier.md
    Autre source : autre.md          (facultatif)
    Erreur attendue : ...            (facultatif, attendu pour les pièges)

Les valeurs peuvent tenir sur plusieurs lignes : toute ligne indentée poursuit
le champ précédent.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

# Types reconnus. Un type inconnu est une erreur et non un avertissement :
# une question mal typée fausse les quotas, donc l'interprétation des scores.
TYPES = {"factuelle", "multi_documents", "piege", "figure", "hors_corpus", "datee"}

# Marqueur de réponse absente du corpus.
SANS_REPONSE = "SANS_REPONSE"

_ENTETE = re.compile(r"^##\s+(Q\d+)\s*[·.\-]\s*(\w+)\s*$")
_CHAMP = re.compile(r"^(Question|Réponse|Reponse|Source|Autre source|Erreur attendue)\s*:\s*(.*)$")

_CLES = {
    "Question": "question",
    "Réponse": "reponse",
    "Reponse": "reponse",
    "Source": "source",
    "Autre source": "autre_source",
    "Erreur attendue": "erreur_attendue",
}


def lire_jeu(chemin: str | Path) -> List[Dict[str, Any]]:
    """Lit un fichier de jeu et renvoie la liste des questions.

    Lève ValueError sur un jeu mal formé — jamais de tolérance silencieuse :
    une question avalée sans bruit se traduirait par un score calculé sur
    moins de cas que ce que le rapport annonce.
    """
    texte = Path(chemin).read_text(encoding="utf-8")
    questions: List[Dict[str, Any]] = []
    courante: Dict[str, Any] | None = None
    dernier_champ: str | None = None

    for numero, ligne in enumerate(texte.splitlines(), start=1):
        entete = _ENTETE.match(ligne)
        if entete:
            if courante is not None:
                questions.append(_clore(courante, numero))
            identifiant, type_ = entete.group(1), entete.group(2)
            if type_ not in TYPES:
                raise ValueError(
                    f"ligne {numero} : type '{type_}' inconnu pour {identifiant}. "
                    f"Attendu l'un de : {', '.join(sorted(TYPES))}"
                )
            courante = {"id": identifiant, "type": type_}
            dernier_champ = None
            continue

        if courante is None:
            continue                      # préambule du fichier : ignoré

        if ligne.startswith("## ") or ligne.strip() == "---":
            questions.append(_clore(courante, numero))
            courante, dernier_champ = None, None
            continue

        champ = _CHAMP.match(ligne)
        if champ:
            cle = _CLES[champ.group(1)]
            courante[cle] = champ.group(2).strip()
            dernier_champ = cle
            continue

        # Ligne indentée non vide : suite du champ précédent.
        if dernier_champ and ligne.startswith("  ") and ligne.strip():
            courante[dernier_champ] = (courante[dernier_champ] + " " + ligne.strip()).strip()

    if courante is not None:
        questions.append(_clore(courante, len(texte.splitlines())))

    if not questions:
        raise ValueError(f"{chemin} ne contient aucune question exploitable.")
    return questions


def _clore(q: Dict[str, Any], numero: int) -> Dict[str, Any]:
    """Contrôle qu'une question est complète, et normalise ses champs."""
    for obligatoire in ("question", "reponse"):
        if not q.get(obligatoire):
            raise ValueError(
                f"{q['id']} (avant la ligne {numero}) : champ '{obligatoire}' manquant ou vide."
            )

    q["sans_reponse"] = q["reponse"].strip().upper().startswith(SANS_REPONSE)

    # Une hors_corpus dont la réponse n'est pas SANS_REPONSE est une
    # contradiction : soit le type est faux, soit la réponse l'est. Dans les
    # deux cas le taux de refus calculé plus loin serait faux.
    if q["type"] == "hors_corpus" and not q["sans_reponse"]:
        raise ValueError(
            f"{q['id']} est de type 'hors_corpus' mais sa réponse n'est pas {SANS_REPONSE}."
        )
    if q["type"] != "hors_corpus" and q["sans_reponse"]:
        raise ValueError(
            f"{q['id']} porte {SANS_REPONSE} mais n'est pas de type 'hors_corpus'."
        )

    q.setdefault("source", "")
    q.setdefault("autre_source", "")
    q.setdefault("erreur_attendue", "")
    return q


def composition(questions: List[Dict[str, Any]]) -> Dict[str, int]:
    """Compte les questions par type. Sert au rapport et aux contrôles."""
    compte: Dict[str, int] = {}
    for q in questions:
        compte[q["type"]] = compte.get(q["type"], 0) + 1
    return compte


def separer(questions: List[Dict[str, Any]]) -> tuple[list, list]:
    """Sépare les questions notables des hors-corpus.

    C'est le point de méthode central de ce fichier. RAGAS mesure la fidélité
    d'une réponse à des passages récupérés ; sur une question sans réponse dans
    le corpus, cette mesure n'a pas de sens — la bonne réponse est justement de
    ne rien affirmer. Mélanger les deux populations produit un score moyen qui
    ne veut rien dire, et qui monte quand le système se met à inventer.

    Les hors-corpus sont donc mesurées à part, sur une autre grandeur : le taux
    de refus.
    """
    notables = [q for q in questions if not q["sans_reponse"]]
    hors = [q for q in questions if q["sans_reponse"]]
    return notables, hors


if __name__ == "__main__":
    import sys
    chemin = sys.argv[1] if len(sys.argv) > 1 else "jeux_eval/exemple/questions.md"
    qs = lire_jeu(chemin)
    notables, hors = separer(qs)
    print(f"{len(qs)} questions lues dans {chemin}")
    for type_, n in sorted(composition(qs).items()):
        print(f"  {type_:16s} {n}")
    print(f"\n  notables (RAGAS)  : {len(notables)}")
    print(f"  hors-corpus (refus) : {len(hors)}")
