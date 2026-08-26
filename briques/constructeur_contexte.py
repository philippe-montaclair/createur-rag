#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
constructeur_contexte.py — Agent N3 « constructeur-contexte » du REGISTRE.
==========================================================================
Extrait de Tuteur.repondre() (la partie qui assemblait le bloc `contexte`).

Rôle : choisir combien de passages entrent dans le prompt, et les mettre en
forme avec leur provenance.

C'est ici que la pile de candidats devient la SÉLECTION FINALE. Toutes les
briques amont ne travaillent que sur `ctx.candidats` ; celle-ci fixe
`ctx.passages`. Un seul endroit décide, donc un seul bouton (`k`) pour le
régleur — et le pipeline fonctionne quel que soit le sous-ensemble de briques
activées avant lui.

La numérotation [1], [2]… posée ici est celle que le modèle devra citer, et
celle que le post-traitement vérifiera. Les trois briques doivent rester
d'accord sur cette convention.
"""

from __future__ import annotations

from contrat import Brique, Contexte


class ConstructeurContexte(Brique):
    nom = "constructeur_contexte"
    niveau = "N3"

    def run(self, ctx: Contexte) -> Contexte:
        k = int(self.params.get("k", 4))
        ctx.passages = ctx.candidats[:k]

        gabarit = self.params.get(
            "gabarit_passage",
            "[{n}] (source : {citation})\n{texte}"
        )
        separateur = self.params.get("separateur", "\n\n")

        ctx.bloc_contexte = separateur.join(
            gabarit.format(n=i, citation=p.citation(), texte=p.texte)
            for i, p in enumerate(ctx.passages, 1)
        )

        ctx.noter(self.nom, k=k, retenus=len(ctx.passages),
                  longueur_bloc=len(ctx.bloc_contexte),
                  sources=[p.citation() for p in ctx.passages])
        return ctx
