#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recherche_bm25.py — Agent N2 « recherche-bm25 » du REGISTRE.
============================================================
Repris de Tuteur.rechercher(), étape 2.

Rôle : recherche par mots-clés, sur les termes LITTÉRAUX de la question.

Pourquoi la garder alors qu'on a déjà le vectoriel ? Parce que les deux ratent
des choses différentes. L'embedding dilue les termes rares : un numéro d'article,
un nom de molécule, une référence de norme se noient dans la sémantique
générale du passage. BM25, lui, ne comprend rien mais retrouve le mot exact.
C'est la complémentarité qui fait le gain, pas la qualité individuelle.
"""

from __future__ import annotations

from contrat import Brique, Contexte
from briques.communs import (charger_corpus, correspond, passages_depuis_ids,
                             tokenize)


class RechercheBM25(Brique):
    nom = "recherche_bm25"
    niveau = "N2"

    def run(self, ctx: Contexte) -> Contexte:
        if ctx.route not in ("bm25", "hybride"):
            ctx.noter(self.nom, ignoree=True, motif=f"route={ctx.route}")
            return ctx

        res = self.ressources
        corpus = charger_corpus(res)
        ids_corpus = corpus["ids"]

        scores = corpus["bm25"].get_scores(tokenize(ctx.question))
        ordre = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        # Même filtre que le vectoriel, réappliqué ici parce que BM25 ne sait pas
        # filtrer. L'ordre compte : on filtre AVANT de tronquer à top_n, sinon on
        # tronquerait sur des candidats déjà voués à disparaître et la liste
        # finale serait plus courte que demandée, sans que rien ne le signale.
        if ctx.filtre:
            metas = corpus["meta_par_id"]
            ordre = [i for i in ordre
                     if correspond(metas.get(ids_corpus[i]), ctx.filtre)]

        limite = self.params.get("top_n") or len(ids_corpus)
        ordre = ordre[:int(limite)]
        ids = [ids_corpus[i] for i in ordre]

        ctx.listes["bm25"] = ids
        # BM25 est déjà « plus grand = meilleur » : rien à convertir. L'échelle,
        # elle, n'a rien à voir avec celle du vectoriel — c'est la fusion qui
        # normalise, pas la recherche. Chaque brique dépose ce qu'elle sait.
        ctx.scores["bm25"] = {ids_corpus[i]: float(scores[i]) for i in ordre}
        # Sans fusion derrière, cette liste devient les candidats.
        # Test sur le CONTENU et non sur la présence de la clé : depuis les
        # filtres par métadonnées, le vectoriel peut déposer une liste VIDE. La
        # clé existe alors, et la condition d'origine concluait « le vectoriel
        # s'en occupe » — alors qu'il n'avait rien à donner. Résultat : zéro
        # passage en sortie, avec des résultats BM25 disponibles.
        if not ctx.listes.get("vectorielle"):
            ctx.candidats = passages_depuis_ids(res, ids, scores=[scores[i] for i in ordre])

        ctx.noter(self.nom, obtenus=len(ids), filtre=ctx.filtre,
                  meilleur_score=round(float(scores[ordre[0]]), 3) if ordre else 0.0,
                  premiers=ids[:3])
        return ctx
