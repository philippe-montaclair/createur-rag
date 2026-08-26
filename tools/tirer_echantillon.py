#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tirer_echantillon.py — Tire les chunks sur lesquels les juges écriront des questions.

POURQUOI UN SCRIPT PLUTÔT QU'UNE SÉLECTION À LA MAIN
----------------------------------------------------
Le tirage doit être REPRODUCTIBLE. Si les deux juges ne travaillent pas sur
exactement les mêmes chunks, leur comparaison ne mesure plus rien : on ne saurait
pas si l'écart vient du juge ou du texte qu'on lui a donné. La graine fixe garantit
que deux exécutions produisent le même échantillon.

CE QUE LE TIRAGE ÉVITE
----------------------
- Les chunks impropres à ENGENDRER une question, marqués `source_de_questions`
  dans l'inventaire : trop courts, ou pauvres en mots-outils français — donc des
  planches anatomiques légendées, pas de la prose. Les inclure fabriquerait des
  questions creuses qu'aucun système ne pourrait honorer : on mesurerait alors la
  qualité du jeu, pas celle du RAG. Ces chunks restent interrogeables et restent
  dans le pool ; ils ne servent simplement pas de point de départ.
- Le déséquilibre thématique : sans stratification, un tirage uniforme sur 123
  chunks donnerait surtout du "général" (48 chunks) et pourrait ne rien tirer du
  membre inférieur (3 chunks).

Seuls les chunks du jeu DEV sont éligibles. Le jeu test reste intact.

USAGE
    python tools/tirer_echantillon.py --n 20
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "jeux_eval" / "corpus_demo"
SEUIL_MOTS = 40
GRAINE = 20260801


def n_mots(t: str) -> int:
    return len(re.sub(r"\s+", " ", t).split())


def repartir(quotas_bruts: dict[str, float], total: int) -> dict[str, int]:
    """Arrondit des quotas fractionnaires en garantissant au moins 1 par thème.

    L'arrondi naïf (int(x)) supprimerait les thèmes minoritaires : le membre
    inférieur pèse 3 chunks sur 123, soit un quota de 0,49 — donc zéro question.
    Un thème absent de l'échantillon ne sera jamais évalué.
    """
    base = {t: max(1, round(v)) for t, v in quotas_bruts.items()}
    while sum(base.values()) > total:            # trop : on rogne le plus gros
        t = max(base, key=lambda k: (base[k], quotas_bruts[k]))
        if base[t] == 1:
            break
        base[t] -= 1
    while sum(base.values()) < total:            # pas assez : on donne au plus gros
        t = max(quotas_bruts, key=lambda k: quotas_bruts[k] - base[k])
        base[t] += 1
    return base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20, help="Nombre de chunks à tirer.")
    ap.add_argument("--inventaire", default=str(DOSSIER / "inventaire.json"))
    ap.add_argument("--sortie", default=str(DOSSIER / "echantillon.json"))
    args = ap.parse_args()

    inv = json.loads(Path(args.inventaire).read_text(encoding="utf-8"))
    canon = {g["canonique"]: g for g in inv["groupes"]}
    dev = [c for c in inv["chunks"]
           if c["source"] in canon and canon[c["source"]]["jeu"] == "dev"]

    eligibles = [c for c in dev if c.get("source_de_questions")]
    ecartes = len(dev) - len(eligibles)

    par_theme: dict[str, list] = defaultdict(list)
    for c in eligibles:
        par_theme[canon[c["source"]]["theme"]].append(c)

    quotas = repartir({t: len(v) / len(eligibles) * args.n for t, v in par_theme.items()},
                      args.n)

    rng = random.Random(GRAINE)
    tirage = []
    for theme, q in sorted(quotas.items()):
        pool = sorted(par_theme[theme], key=lambda c: c["id"])
        pris = rng.sample(pool, min(q, len(pool)))
        for c in pris:
            tirage.append({"id": c["id"], "theme": theme,
                           "source": c["source"], "texte": c["texte"],
                           "n_mots": n_mots(c["texte"])})
    tirage.sort(key=lambda c: (c["theme"], c["id"]))

    print(f"dev éligible : {len(eligibles)} chunks "
          f"({ecartes} écartés : trop courts ou non rédigés)")
    for t in sorted(quotas):
        print(f"  {t:<12} {quotas[t]:>2} tirés sur {len(par_theme[t]):>3} disponibles")
    print(f"\n{len(tirage)} chunks tirés — graine {GRAINE}")

    Path(args.sortie).write_text(
        json.dumps({"graine": GRAINE, "seuil_mots": SEUIL_MOTS,
                    "quotas": quotas, "chunks": tirage},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"écrit : {args.sortie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
