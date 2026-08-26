#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recherche_vectorielle.py — Agent N2 « recherche-vectorielle » du REGISTRE.
==========================================================================
Repris de Tuteur.rechercher(), étapes 1.

Rôle : vectorise la question avec le MÊME modèle que celui de l'ingestion, puis
demande à Chroma les chunks les plus proches (recherche ANN).

Paramètre `top_k` :
  · un entier  → on ne demande que ce nombre de résultats (profil minimal) ;
  · null       → on demande TOUT le corpus classé.
Pourquoi « tout » ? Parce que la fusion RRF qui suit travaille sur des RANGS :
pour que le rang d'un chunk soit comparable entre les deux moteurs, il faut que
les deux aient classé le même ensemble. C'est le comportement de tuteur.py, et
c'est ce que le profil « moyen » doit reproduire à l'identique.
"""

from __future__ import annotations

from contrat import Brique, Contexte
from briques.communs import (charger_collection, charger_corpus, charger_embed,
                             fiche_embeddeur, passages_depuis_ids)


class RechercheVectorielle(Brique):
    nom = "recherche_vectorielle"
    niveau = "N2"

    def run(self, ctx: Contexte) -> Contexte:
        # Le routeur peut avoir décidé de se passer de ce moteur.
        if ctx.route not in ("vectorielle", "hybride"):
            ctx.noter(self.nom, ignoree=True, motif=f"route={ctx.route}")
            return ctx

        res = self.ressources
        embed = charger_embed(res)
        corpus = charger_corpus(res)
        collection = charger_collection(res)

        demande = self.params.get("top_k") or len(corpus["ids"])
        demande = min(int(demande), len(corpus["ids"]))

        # Certains modèles (famille e5) exigent un préfixe côté requête. Sans
        # lui, la qualité chute sans aucune erreur visible — c'est pour ce
        # genre de piège muet que le catalogue porte les champs prefixe_*.
        prefixe = fiche_embeddeur(res).get("prefixe_requete", "") or ""
        vecteur = embed.encode([prefixe + ctx.question]).tolist()
        # Filtre par métadonnées : Chroma le fait nativement, donc à l'intérieur
        # de la recherche ANN et non après coup. Un `where` qui ne laisse rien
        # passer rend une liste VIDE — et c'est le comportement voulu : un filtre
        # est une contrainte, pas une préférence. Se rabattre sur une recherche
        # non filtrée reviendrait à répondre depuis l'extérieur du périmètre
        # demandé, ce qui, dès qu'un filtre sert à cloisonner deux clients ou
        # deux niveaux de confidentialité, est une fuite.
        requete = {"query_embeddings": vecteur, "n_results": demande,
                   "include": ["distances"]}
        if ctx.filtre:
            requete["where"] = ctx.filtre
        reponse = collection.query(**requete)
        ids = reponse["ids"][0]
        distances = (reponse.get("distances") or [[None] * len(ids)])[0]

        ctx.listes["vectorielle"] = ids
        # Convention du contrat : plus grand = meilleur. Chroma rend une
        # DISTANCE (plus petit = plus proche), d'où la conversion. Sans elle, une
        # fusion par score classerait le corpus à l'envers — silencieusement.
        if distances and distances[0] is not None:
            ctx.scores["vectorielle"] = {
                cid: 1.0 - float(d) for cid, d in zip(ids, distances)}
        # Sans fusion derrière (profil minimal), c'est cette liste qui fait foi.
        ctx.candidats = passages_depuis_ids(res, ids, scores=distances)

        ctx.noter(self.nom, demandes=demande, obtenus=len(ids),
                  filtre=ctx.filtre, premiers=ids[:3])
        return ctx
