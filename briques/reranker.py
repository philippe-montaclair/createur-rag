#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reranker.py — Agent N3 « reranker » du REGISTRE.
================================================
Repris de Tuteur.rechercher(), étape 4.

Rôle : reclasser la pile de candidats avec un cross-encoder.

Différence avec la recherche vectorielle, qui est LE point à retenir :
  · le bi-encodeur (recherche) encode la question et le chunk SÉPARÉMENT, puis
    compare deux vecteurs. Rapide, mais il n'a jamais vu les deux textes
    ensemble — il juge une ressemblance globale ;
  · le cross-encoder les lit ENSEMBLE, dans la même passe. Bien plus juste,
    bien plus lent. D'où l'ordre : on récupère large avec le bi-encodeur, on
    affine étroit avec le cross-encoder.

Conséquence pour l'agent régleur : c'est un levier de CLASSEMENT, pas de
RECALL. Il remet dans le bon ordre ce qu'on lui donne — il ne fait pas
apparaître un passage qui n'était pas dans la pile. Si l'évaluateur signale
une réponse incomplète parce que le bon passage n'a jamais été récupéré,
augmenter la qualité du reranker ne changera rien : le levier est en amont
(pool de la fusion, top_k de la recherche, ou le chunking lui-même).
"""

from __future__ import annotations

from contrat import Brique, Contexte
from briques.communs import charger_reranker


class Reranker(Brique):
    nom = "reranker"
    niveau = "N3"

    def run(self, ctx: Contexte) -> Contexte:
        if not ctx.candidats:
            ctx.noter(self.nom, ignoree=True, motif="aucun candidat")
            return ctx

        modele = charger_reranker(self.ressources)
        paires = [[ctx.question, p.texte] for p in ctx.candidats]
        notes = modele.predict(paires)

        ordonnes = sorted(zip(notes, ctx.candidats), key=lambda x: float(x[0]), reverse=True)
        for note, passage in ordonnes:
            passage.score = float(note)

        avant = [p.id for p in ctx.candidats]
        candidats = [p for _, p in ordonnes]

        garde = self.params.get("garde")
        if garde:
            candidats = candidats[: int(garde)]
        ctx.candidats = candidats

        # Mesure utile au régleur : de combien de places le reranker a-t-il
        # bougé les choses ? S'il ne déplace jamais rien, il coûte du temps
        # pour rien et le profil peut s'en passer.
        apres = [p.id for p in candidats]
        deplacement = sum(
            abs(avant.index(cid) - i) for i, cid in enumerate(apres) if cid in avant
        )
        ctx.noter(self.nom, entres=len(avant), sortis=len(apres),
                  deplacement_total=deplacement,
                  meilleur_score=round(float(ordonnes[0][0]), 4))

        if self.params.get("decharger_apres", False):
            libere = self.ressources.decharger("reranker")
            ctx.noter(self.nom, reranker_decharge=libere)

        return ctx
