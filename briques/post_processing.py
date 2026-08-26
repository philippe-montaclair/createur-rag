#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
post_processing.py — Agent N4 « post-processing » du REGISTRE.
==============================================================
Repris de la boucle d'affichage de tuteur.py, et étendu.

Rôle : nettoyer la réponse et RÉSOUDRE les citations.

L'ajout par rapport à tuteur.py : la vérification des citations. On relève les
[n] réellement présents dans la réponse et on les confronte aux passages
fournis. Deux anomalies deviennent visibles :

  · citation ORPHELINE — le modèle cite [7] alors qu'on ne lui a donné que 4
    extraits. Signe qu'il fabule ses sources ;
  · passage IGNORÉ — un extrait fourni n'est jamais cité. Pas une faute en soi,
    mais si ça se produit systématiquement, c'est que le `k` du constructeur de
    contexte est trop large : on paie des tokens pour du contexte inutile.

Ces deux compteurs sont exactement ce que l'agent évaluateur lira pour juger la
fidélité, et l'agent régleur pour ajuster `k`. Une brique « cosmétique » sur le
papier qui produit, en réalité, deux des signaux les plus utiles du pipeline.
"""

from __future__ import annotations

import re

from contrat import Brique, Contexte

MOTIF_CITATION = re.compile(r"\[(\d{1,2})\]")


class PostProcessing(Brique):
    nom = "post_processing"
    niveau = "N4"

    def run(self, ctx: Contexte) -> Contexte:
        texte = ctx.reponse.strip()

        # Certains modèles laissent traîner un bloc de raisonnement même avec
        # think=False. On le retire plutôt que de l'afficher à l'utilisateur.
        if self.params.get("retirer_raisonnement", True):
            texte = re.sub(r"<think>.*?</think>", "", texte, flags=re.DOTALL).strip()

        indices_cites = sorted({int(n) for n in MOTIF_CITATION.findall(texte)})
        n_passages = len(ctx.passages)

        valides = [i for i in indices_cites if 1 <= i <= n_passages]
        orphelines = [i for i in indices_cites if i > n_passages or i < 1]
        ignores = [i for i in range(1, n_passages + 1) if i not in valides]

        ctx.reponse = texte
        ctx.citations = [
            f"[{i}] {ctx.passages[i - 1].citation()}" for i in valides
        ]

        ctx.noter(self.nom,
                  citations_valides=valides,
                  citations_orphelines=orphelines,
                  passages_ignores=ignores,
                  taux_citation=round(len(valides) / n_passages, 2) if n_passages else 0.0)
        return ctx
