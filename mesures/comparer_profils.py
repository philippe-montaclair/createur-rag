#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mesures/comparer_profils.py — Compare les campagnes de plusieurs profils.

    python mesures/comparer_profils.py                      # tous les profils mesurés
    python mesures/comparer_profils.py --profils moyen,complet
    python mesures/comparer_profils.py --sortie COMPARAISON.md

Lit `mesures/runs/<profil>.json` — rien d'autre. Aucun modèle, aucun réseau,
aucune réinterrogation : logique pure, donc vérifiable en intégration continue.

CE QU'UNE COMPARAISON PEUT DIRE, ET CE QU'ELLE NE PEUT PAS
-----------------------------------------------------------
Deux profils mesurés une fois chacun sur le même jeu, ce sont deux nombres.
Sans dispersion, un écart n'est pas un résultat : c'est la règle que
`memoire.py` impose déjà aux expériences de réglage, et il n'y a aucune raison
de s'en affranchir ici.

Ce fichier applique donc le même garde-fou. Sur la latence, dont on a 25
mesures par profil, l'écart est comparé au bruit et qualifié. Sur les scores
RAGAS, dont on n'a qu'UNE valeur par profil, aucun seuil n'est appliqué et
c'est écrit noir sur blanc : ce sont des indications, pas des verdicts. Les
transformer en « le profil X est meilleur » demanderait de relancer chaque
campagne plusieurs fois.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "mesures" / "runs"

METRIQUES = ["faithfulness", "answer_relevancy", "context_precision",
             "context_recall", "answer_correctness"]

# Ordre de la CHAÎNE, pas de l'alphabet. Trié alphabétiquement, on obtiendrait
# complet · minimal · moyen, et l'écart se lirait du plus fourni au plus pauvre
# — l'inverse de ce qu'on cherche. Les profils inconnus suivent, par ordre
# alphabétique, après ceux-là.
ORDRE = ["minimal", "moyen", "moyen_e5", "complet"]


def ordonner(noms):
    connus = [n for n in ORDRE if n in noms]
    return connus + sorted(n for n in noms if n not in ORDRE)


def reference(noms):
    """Le plancher. `minimal` s'il a été mesuré — c'est sa raison d'être :
    une brique qui ne bat pas le plancher n'a rien à faire dans la chaîne.
    À défaut, le premier profil de la chaîne."""
    return "minimal" if "minimal" in noms else (noms[0] if noms else None)


def charger(profils: List[str] | None = None) -> Dict[str, Any]:
    if not DOSSIER.exists():
        return {}
    runs = {}
    for f in sorted(DOSSIER.glob("*.json")):
        if profils and f.stem not in profils:
            continue
        runs[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    return runs


def latences(run: Dict[str, Any]) -> List[float]:
    return [r["duree_ms"] for r in run.get("notables", []) + run.get("hors_corpus", [])]


def moyennes_ragas(run: Dict[str, Any]) -> Dict[str, float]:
    return (run.get("ragas") or {}).get("averages") or {}


def refus_structurels(run: Dict[str, Any]) -> int:
    """Nombre de hors-corpus sans aucune citation. Indice, pas verdict —
    le taux de refus qui fait foi est relevé à la main dans MESURES.md."""
    return sum(1 for r in run.get("hors_corpus", [])
               if not r.get("citations"))


def qualifier(ecart: float, bruit: float) -> str:
    """Même règle que memoire.py : en deçà de deux écarts-types, c'est du bruit."""
    if bruit <= 0:
        return "bruit inconnu"
    rapport = abs(ecart) / bruit
    if rapport < 2:
        return f"**bruit** ({rapport:.1f}× l'écart-type)"
    return f"significatif ({rapport:.1f}× l'écart-type)"


def rapport(runs: Dict[str, Any]) -> str:
    noms = ordonner(list(runs))
    ref = reference(noms)
    lignes = ["# Comparaison des profils", "",
              "Produit par `mesures/comparer_profils.py` à partir des campagnes",
              f"enregistrées dans `mesures/runs/` : {', '.join(f'`{n}`' for n in noms)}.",
              "", "## Latence", "",
              "| Profil | médiane | moyenne | écart-type | n |", "|---|---|---|---|---|"]

    stats = {}
    for nom in noms:
        d = latences(runs[nom])
        if not d:
            continue
        stats[nom] = {"med": statistics.median(d), "moy": statistics.mean(d),
                      "sd": statistics.pstdev(d) if len(d) > 1 else 0.0, "n": len(d)}
        s = stats[nom]
        lignes.append(f"| `{nom}` | **{s['med']:.0f} ms** | {s['moy']:.0f} ms | "
                      f"{s['sd']:.0f} ms | {s['n']} |")

    autres = [n for n in noms if n != ref and n in stats]
    if ref in stats and autres:
        lignes += ["", f"### Écarts contre le plancher `{ref}`", ""]
        for n in autres:
            ecart = stats[n]["moy"] - stats[ref]["moy"]
            bruit = max(stats[ref]["sd"], stats[n]["sd"])
            lignes.append(f"- `{n}` − `{ref}` : **{ecart:+.0f} ms** — {qualifier(ecart, bruit)}")
        lignes += ["",
                   "Le bruit retenu est le plus grand des deux écarts-types. En deçà de deux",
                   "écarts-types, l'écart n'est pas distinguable du hasard : c'est la règle que",
                   "`memoire.py` applique aux expériences de réglage, reprise ici telle quelle.",
                   "",
                   f"Tout se mesure contre `{ref}` et non de proche en proche, parce que c'est",
                   "la question qui compte : **chaque brique ajoutée paie-t-elle son coût ?**",
                   "Un profil plus fourni qui ne bat pas le plancher ne mérite pas les modèles",
                   "qu'il charge."]

    lignes += ["", "## Qualité (RAGAS)", ""]
    mesures = {n: moyennes_ragas(runs[n]) for n in noms}
    if any(mesures.values()):
        entetes = [f"`{n}`" + ("" if n == ref else f" (écart / `{ref}`)") for n in noms]
        lignes += ["| Métrique | " + " | ".join(entetes) + " |",
                   "|---" * (len(noms) + 1) + "|"]
        for m in METRIQUES:
            cases = []
            for n in noms:
                v = mesures[n].get(m)
                if not isinstance(v, (int, float)):
                    cases.append("—")
                elif n == ref:
                    cases.append(f"{v:.3f}")
                else:
                    base = mesures.get(ref, {}).get(m)
                    cases.append(f"{v:.3f} ({v - base:+.3f})"
                                 if isinstance(base, (int, float)) else f"{v:.3f}")
            lignes.append(f"| `{m}` | " + " | ".join(cases) + " |")
        lignes += ["",
                   "> **Une valeur par profil, aucune répétition.** Ces écarts sont des",
                   "> indications, pas des verdicts : sans dispersion, on ne peut pas les",
                   "> distinguer de la variabilité du juge, qui est lui-même un modèle de",
                   "> langue. Conclure « tel profil est meilleur » demanderait de relancer",
                   "> chaque campagne plusieurs fois. Ce n'est pas fait, donc ce n'est pas dit.",
                   ""]
    else:
        lignes += ["Aucune notation RAGAS enregistrée. Voir `mesures/noter_ragas.py`.", ""]

    lignes += ["## Refus sur les hors-corpus", "",
               "| Profil | hors-corpus sans citation | sur |", "|---|---|---|"]
    for n in noms:
        h = runs[n].get("hors_corpus", [])
        lignes.append(f"| `{n}` | {refus_structurels(runs[n])} | {len(h)} |")
    lignes += ["",
               "Indice structurel seulement. Le taux de refus qui fait foi est relevé par",
               "lecture humaine, profil par profil, dans le rapport de chaque campagne.", ""]

    lignes += ["## Ce que la comparaison ne dit pas", "",
               "Les deux profils sont mesurés sur le **même corpus de 14 chunks**, où la",
               "récupération est facile : `k: 4` en retient 29 %. Les briques de tri du",
               "profil `complet` — routeur en amont, validateur de chunks en aval — sont",
               "faites pour des corpus hétérogènes de plusieurs milliers de chunks, où le",
               "bruit à écarter est le problème. Les juger sur un corpus où il n'y a presque",
               "rien à écarter les dessert par construction.",
               "",
               "Autrement dit : un profil `complet` qui n'apporte rien ici ne prouve pas",
               "qu'il n'apporte rien. Il prouve que ce corpus ne pose pas le problème qu'il",
               "résout.", ""]
    return "\n".join(lignes)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profils", default=None,
                    help="liste séparée par des virgules ; par défaut, toutes les campagnes")
    ap.add_argument("--sortie", default="COMPARAISON.md")
    args = ap.parse_args()

    demandes = [p.strip() for p in args.profils.split(",")] if args.profils else None
    runs = charger(demandes)
    if len(runs) < 2:
        print(f"⛔ {len(runs)} campagne(s) trouvée(s) dans {DOSSIER.relative_to(RACINE)} :"
              f" {', '.join(runs) or 'aucune'}")
        print("   Une comparaison demande au moins deux profils mesurés.")
        return 1

    (RACINE / args.sortie).write_text(rapport(runs), encoding="utf-8")
    print(f"✅ {args.sortie} écrit — {len(runs)} profils : {', '.join(runs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
