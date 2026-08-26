#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
observabilite.py — Agent N0 du REGISTRE, sous forme transverse.
===============================================================
Ce n'est pas une brique du pipeline : c'est ce qui ENTOURE chaque brique.

Pourquoi dès la phase 1, alors que le REGISTRE la classe en « total » ?
----------------------------------------------------------------------
Parce que les deux autres agents du système en dépendent entièrement :

  · L'agent ÉVALUATEUR doit pouvoir dire OÙ ça casse. « La réponse est
    mauvaise » ne sert à rien. « Le bon passage n'était pas dans les candidats
    après fusion » désigne le coupable : la recherche, pas la génération.

  · L'agent RÉGLEUR doit voir l'effet d'UNE variable. Sans mesure par
    composant, il ne peut pas savoir si passer top_k de 20 à 40 a amélioré le
    recall ou seulement ralenti le pipeline.

Une trace par brique, une ligne JSON par question. Format volontairement plat
et append-only : lisible par un humain, par pandas, et par un autre agent.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from contrat import Brique, Contexte


class Journal:
    """Chronomètre chaque brique et écrit ce qui s'est passé.

    Actif ou non selon le profil YAML (`observabilite.actif`). Inactif, il ne
    coûte qu'un appel de fonction — on garde donc le même code dans les trois
    profils, sans branche conditionnelle disséminée dans le pipeline.
    """

    def __init__(self, actif: bool = True, fichier: str | Path | None = None):
        self.actif = actif
        self.fichier = Path(fichier) if fichier else None
        if self.actif and self.fichier:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)

    # ── Exécution mesurée d'une brique ──────────────────────────────────────
    def executer(self, brique: Brique, ctx: Contexte) -> Contexte:
        """Lance `brique.run(ctx)` en le chronométrant et en relevant l'état
        du contexte avant/après. C'est le seul endroit du code qui sait
        mesurer — les briques, elles, ignorent qu'on les observe."""
        if not self.actif:
            return brique.run(ctx)

        avant = self._etat(ctx)
        t0 = time.perf_counter()
        erreur = None
        try:
            ctx = brique.run(ctx)
        except Exception as e:
            erreur = f"{type(e).__name__}: {e}"
            raise
        finally:
            duree_ms = round((time.perf_counter() - t0) * 1000, 1)
            trace = {
                "brique": brique.nom,
                "niveau": brique.niveau,
                "params": brique.params,
                "duree_ms": duree_ms,
                "avant": avant,
                "apres": self._etat(ctx),
                "notes": ctx.notes.get(brique.nom, {}),
            }
            if erreur:
                trace["erreur"] = erreur
            ctx.traces.append(trace)
        return ctx

    @staticmethod
    def _etat(ctx: Contexte) -> dict:
        """Photographie compacte du contexte. On garde les IDENTIFIANTS des
        passages retenus, pas leur texte : c'est ce qui permet ensuite de
        répondre à « le bon chunk était-il encore là à cette étape ? »."""
        return {
            "n_candidats": len(ctx.candidats),
            "n_passages": len(ctx.passages),
            "ids_passages": [p.id for p in ctx.passages],
            "route": ctx.route,
            "longueur_reponse": len(ctx.reponse),
        }

    # ── Clôture d'une question ──────────────────────────────────────────────
    def clore(self, ctx: Contexte, profil: str = "") -> dict:
        """Assemble le bilan de la question et l'écrit dans le journal."""
        total = round(sum(t["duree_ms"] for t in ctx.traces), 1)
        bilan = {
            "horodatage": datetime.now().isoformat(timespec="seconds"),
            "profil": profil,
            "question": ctx.question,
            "route": ctx.route,
            "duree_totale_ms": total,
            "goulot": self._goulot(ctx),
            "repartition_ms": {t["brique"]: t["duree_ms"] for t in ctx.traces},
            "sources_citees": [p.citation() for p in ctx.passages],
            "ids_passages": [p.id for p in ctx.passages],
            # Les incidents remontent AU PREMIER NIVEAU du bilan, pas seulement
            # dans les traces des briques : c'est le seul champ qu'un agent de
            # surveillance a besoin de lire pour savoir que le pipeline tourne
            # dégradé. Le repli protège du plantage, pas de l'aveuglement.
            "erreurs": list(ctx.erreurs),
            "traces": ctx.traces,
        }
        if self.actif and self.fichier:
            with self.fichier.open("a", encoding="utf-8") as f:
                f.write(json.dumps(bilan, ensure_ascii=False) + "\n")
        return bilan

    @staticmethod
    def _goulot(ctx: Contexte) -> str:
        """La brique la plus lente. Presque toujours le LLM — mais « presque »
        n'est pas « toujours », et c'est justement ce qu'on veut vérifier
        plutôt que supposer (méthode de rag-production/AGENTS.md §4)."""
        if not ctx.traces:
            return ""
        return max(ctx.traces, key=lambda t: t["duree_ms"])["brique"]


def resumer(bilan: dict) -> str:
    """Rendu lisible d'un bilan, pour l'affichage en ligne de commande."""
    lignes = [f"⏱  {bilan['duree_totale_ms']} ms au total "
              f"(goulot : {bilan['goulot']})"]
    for inc in bilan.get("erreurs", []):
        marque = "⚠️  repli" if inc.get("repli") else "🛑 ARRÊT"
        lignes.append(f"   {marque} sur {inc['brique']} — {inc['erreur']}")
        if inc.get("motif"):
            lignes.append(f"        {inc['motif']}")
    for brique, ms in bilan["repartition_ms"].items():
        part = 100 * ms / bilan["duree_totale_ms"] if bilan["duree_totale_ms"] else 0
        lignes.append(f"   {brique:<24} {ms:>8.1f} ms  {part:4.1f} %")
    return "\n".join(lignes)
