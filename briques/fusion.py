#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fusion.py — Agent N2 « fusion » du REGISTRE (Reciprocal Rank Fusion).
=====================================================================
Repris de la fonction rrf() de tuteur.py, à l'identique.

Rôle : combiner les listes du vectoriel et de BM25 en une seule.

Le point à comprendre : la RRF fusionne des RANGS, pas des scores. C'est
délibéré — un score de similarité cosinus et un score BM25 ne sont pas
comparables (échelles et distributions différentes), les additionner n'aurait
aucun sens. Le rang, lui, est universel : être 3e est comparable d'un moteur à
l'autre. La constante k=60 amortit le poids des premières places, de sorte
qu'un chunk trouvé honorablement par les DEUX moteurs passe devant un chunk
trouvé 1er par un seul.

C'est un levier de RECALL (faire entrer le bon passage dans la pile), pas de
classement. Distinction décisive pour le futur agent régleur : si le bon
passage n'est pas dans la pile, améliorer le reranker n'y changera rien.

Deuxième stratégie, ajoutée le 31/07/2026 : la FUSION PAR SCORE PONDÉRÉ
----------------------------------------------------------------------
Le PDF source donne les deux méthodes ; seule la RRF avait été reprise.
`strategie: rrf | score` rend le choix mesurable au lieu d'implicite.

Attention : tout ce qui est écrit plus haut sur l'incomparabilité des échelles
reste vrai. Additionner une similarité cosinus et un score BM25 n'a aucun sens.
C'est pourquoi la stratégie `score` NORMALISE d'abord chaque liste en min-max
sur [0,1] — le meilleur de la liste vaut 1, le pire vaut 0 — avant de pondérer.

Ce que la normalisation min-max fait payer, et qu'il faut savoir : elle est
RELATIVE à la liste. Si les dix candidats d'un moteur ont des scores presque
identiques, le min-max étire ces écarts insignifiants jusqu'à occuper tout
l'intervalle [0,1] — il transforme du bruit en signal. La RRF, qui ne regarde
que les rangs, a exactement le même défaut sous une autre forme. Aucune des
deux ne connaît la différence entre « premier de loin » et « premier de peu ».

Quelle stratégie est la meilleure ? Personne ici ne le sait, et c'est le but :
la question est désormais posée sous une forme mesurable.
"""

from __future__ import annotations

from contrat import Brique, Contexte
from briques.communs import passages_depuis_ids


def minmax(scores: dict[str, float]) -> dict[str, float]:
    """Ramène une liste de scores sur [0,1]. Le meilleur vaut 1, le pire 0.

    Cas particulier des scores tous égaux : on rend 0,5 à tout le monde. C'est
    le seul choix neutre — 1,0 déclarerait la liste entière excellente, 0,0 la
    déclarerait nulle, et dans les deux cas on inventerait une information que
    la mesure ne contient pas.
    """
    if not scores:
        return {}
    valeurs = list(scores.values())
    bas, haut = min(valeurs), max(valeurs)
    if haut == bas:
        return {cid: 0.5 for cid in scores}
    return {cid: (v - bas) / (haut - bas) for cid, v in scores.items()}


def fusion_ponderee(scores_par_moteur: dict[str, dict[str, float]],
                    poids: dict[str, float] | None = None) -> list[str]:
    """Fusion par score pondéré, après normalisation min-max de chaque moteur.

    Un chunk absent de la liste d'un moteur reçoit 0 pour ce moteur — c'est-à-dire
    « ce moteur ne l'a pas retenu », et non « ce moteur l'a mal noté ». La nuance
    est réelle : avec des listes tronquées (top_k, top_n), un chunk classé 11e sur
    10 demandés est traité comme le pire du corpus. Tant que les profils livrés
    demandent tout le corpus (top_k: null), le cas ne se présente pas — mais le
    régleur, lui, tronquera.
    """
    poids = poids or {}
    normalises = {m: minmax(s) for m, s in scores_par_moteur.items() if s}
    total: dict[str, float] = {}
    for moteur, s in normalises.items():
        p = float(poids.get(moteur, 0.5))
        for cid, v in s.items():
            total[cid] = total.get(cid, 0.0) + p * v
    return sorted(total, key=lambda c: total[c], reverse=True)


def rrf(listes_ids: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion — identique à l'implémentation de tuteur.py."""
    scores: dict[str, float] = {}
    for ids in listes_ids:
        for rang, cid in enumerate(ids, 1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rang)
    return sorted(scores, key=lambda c: scores[c], reverse=True)


class Fusion(Brique):
    nom = "fusion"
    niveau = "N2"

    def run(self, ctx: Contexte) -> Contexte:
        listes = [ids for ids in ctx.listes.values() if ids]
        if not listes:
            ctx.noter(self.nom, ignoree=True, motif="aucune liste en entrée")
            return ctx
        if len(listes) == 1:
            # Un seul moteur a produit quelque chose : rien à fusionner. Mais on
            # ne se contente PAS de « laisser passer » comme avant le 31/07/2026.
            # Laisser passer supposait qu'une brique amont avait rempli
            # ctx.candidats — supposition fausse dès qu'un filtre vide la liste
            # du vectoriel : la clé "vectorielle" existe, BM25 croit donc que le
            # vectoriel s'en charge, et le pipeline sortait ZÉRO passage avec des
            # résultats sous la main. On garantit ici l'invariant plutôt que de
            # l'espérer : à la sortie de la fusion, les candidats reflètent ce
            # qui a été trouvé.
            pool_1 = int(self.params.get("pool", 10))
            if not ctx.candidats:
                ctx.candidats = passages_depuis_ids(self.ressources, listes[0][:pool_1])
            ctx.noter(self.nom, ignoree=True, motif="une seule liste non vide",
                      retenus=len(ctx.candidats))
            return ctx

        k = int(self.params.get("k", 60))
        pool = int(self.params.get("pool", 10))
        strategie = str(self.params.get("strategie", "rrf")).lower()
        if strategie not in ("rrf", "score"):
            raise ValueError(
                f"fusion : strategie={strategie!r} inconnue (rrf | score).")

        if strategie == "score":
            dispo = {m: s for m, s in ctx.scores.items() if s}
            if len(dispo) < 2:
                # Repli EXPLICITE et tracé : sans les scores des deux moteurs, la
                # pondération n'a rien à pondérer. On revient à la RRF plutôt que
                # de fusionner un seul moteur avec lui-même — mais on le DIT,
                # sinon le régleur croirait mesurer une stratégie qui n'a pas
                # tourné, et conclurait « aucune différence ».
                ctx.noter(self.nom, strategie_demandee="score",
                          strategie_appliquee="rrf",
                          motif=f"scores disponibles pour {sorted(dispo)} seulement")
                strategie = "rrf"
            else:
                poids = self.params.get("poids") or {}
                ids_fusionnes = fusion_ponderee(dispo, poids)[:pool]
                ctx.candidats = passages_depuis_ids(self.ressources, ids_fusionnes)
                ctx.noter(self.nom, strategie="score", poids=poids, pool=pool,
                          moteurs=sorted(dispo), retenus=len(ids_fusionnes))
                return ctx

        ids_fusionnes = rrf(listes, k=k)[:pool]
        ctx.candidats = passages_depuis_ids(self.ressources, ids_fusionnes)

        ctx.noter(self.nom, strategie="rrf", listes_fusionnees=list(ctx.listes),
                  k=k, pool=pool, retenus=len(ids_fusionnes))
        return ctx
