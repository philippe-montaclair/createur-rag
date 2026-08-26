#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validateur_chunks.py — Agent N3 « validateur-chunks » du REGISTRE. BRIQUE NEUVE.
================================================================================
Deuxième et dernière brique écrite de zéro.

Rôle : avant que les passages n'entrent dans le prompt, vérifier trois choses —
pertinence, dédoublonnage, couverture (les trois de la fiche du REGISTRE).

Pourquoi ça compte plus qu'il n'y paraît : chaque place du top-k est chère. Un
quasi-doublon occupe une place avec un contenu déjà présent, et il ne se
contente pas d'être inutile — il évince un passage qui aurait pu apporter autre
chose. `ingest_tuteur.py` dédoublonne déjà à l'indexation, mais uniquement les
doublons EXACTS. Deux chunks qui se recouvrent à 90 % (effet du recouvrement
volontaire du découpage, ou même protocole recopié avec une phrase de
différence) passent au travers.

Le contrôle de couverture, lui, n'écarte rien : il SIGNALE. Si après filtrage
il reste moins de passages que demandé, c'est une information pour l'agent
évaluateur — la réponse sera peut-être incomplète, et la cause est en amont
(recall), pas dans la génération.
"""

from __future__ import annotations

from contrat import Brique, Contexte
from briques.communs import tokenize


def jaccard(a: set, b: set) -> float:
    """Recouvrement de deux ensembles de mots. 1.0 = identiques, 0.0 = disjoints."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class ValidateurChunks(Brique):
    nom = "validateur_chunks"
    niveau = "N3"

    def run(self, ctx: Contexte) -> Contexte:
        if not ctx.candidats:
            ctx.noter(self.nom, ignoree=True, motif="aucun candidat")
            return ctx

        seuil_doublon = float(self.params.get("seuil_doublon", 0.85))
        score_min = self.params.get("score_min")          # None = désactivé
        mots_min = int(self.params.get("mots_min", 0))
        couverture_min = int(self.params.get("couverture_min", 0))

        gardes, jetes = [], []
        empreintes: list[set] = []

        for passage in ctx.candidats:
            mots = set(tokenize(passage.texte))

            # 1) Pertinence — seuil sur le score. Désactivé par défaut : les
            # scores n'ont pas la même échelle selon la brique qui les a posés
            # (distance cosinus, BM25, cross-encoder). Un seuil n'a de sens
            # qu'après avoir observé la distribution réelle, ce que le journal
            # permet justement de faire. « Mesurer, pas supposer. »
            if score_min is not None and passage.score is not None \
                    and float(passage.score) < float(score_min):
                jetes.append((passage.id, "score"))
                continue

            # 2) Chunk trop court pour porter une information utile.
            if mots_min and len(mots) < mots_min:
                jetes.append((passage.id, "trop court"))
                continue

            # 3) Quasi-doublon d'un passage déjà retenu (mieux classé).
            if any(jaccard(mots, deja) >= seuil_doublon for deja in empreintes):
                jetes.append((passage.id, "quasi-doublon"))
                continue

            gardes.append(passage)
            empreintes.append(mots)

        ctx.candidats = gardes

        # 4) Couverture — on ne filtre pas, on alerte.
        alerte = ""
        if couverture_min and len(gardes) < couverture_min:
            alerte = (f"couverture faible : {len(gardes)} passage(s) valides "
                      f"pour {couverture_min} attendu(s)")

        ctx.noter(self.nom, entres=len(gardes) + len(jetes), gardes=len(gardes),
                  jetes=[{"id": i, "motif": m} for i, m in jetes],
                  seuil_doublon=seuil_doublon, alerte=alerte)
        return ctx
