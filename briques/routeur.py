#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
routeur.py — Agent N1 « routeur » du REGISTRE. BRIQUE NEUVE.
============================================================
Absent de tuteur-local : c'est l'une des deux seules briques réellement écrites
de zéro.

Rôle : décider, AVANT de chercher, quels moteurs de recherche interroger.

Choix d'implémentation : des RÈGLES, pas un modèle
--------------------------------------------------
La fiche du REGISTRE prévoit « un modèle léger ». On commence pourtant par de
simples règles, pour trois raisons :
  · un appel LLM au routage ajouterait plusieurs secondes AVANT même de
    chercher, sur le poste le plus contraint de la chaîne ;
  · une règle est déterministe, donc mesurable : l'agent régleur peut isoler
    son effet, ce qu'il ne pourrait pas faire avec un modèle qui varie ;
  · on ne sait pas encore si le routage apporte quoi que ce soit. La règle
    permet de le mesurer pour un coût nul avant d'investir dans mieux.

Par défaut, le routeur renvoie « hybride » — c'est-à-dire qu'il ne coupe rien.
C'est délibéré : couper un moteur, c'est risquer que le bon passage ne soit
jamais récupéré, et AUCUNE brique en aval ne rattrape un passage absent. Le
routeur ne se permet d'écarter un moteur que sur un signal franc.
"""

from __future__ import annotations

import re

from contrat import Brique, Contexte

# Signaux d'une recherche par termes littéraux, que la sémantique dilue :
# références d'articles, codes, montants, dates précises, sigles, guillemets.
MOTIFS_LITTERAUX = [
    re.compile(r'"[^"]{2,}"'),                    # expression entre guillemets
    re.compile(r"\b[A-Z]{2,}[-\s]?\d+\b"),        # référence type "RGPD 32", "ISO-9001"
    re.compile(r"\bart(?:icle)?\.?\s*[LRD]?\.?\s*\d+", re.I),   # article L.123-4
    re.compile(r"\b\d{1,3}(?:[ .,]\d{3})*\s?(?:€|EUR|%)\b"),    # montants, pourcentages
    re.compile(r"\b\d{2}/\d{2}/\d{2,4}\b"),       # date précise
]


class Routeur(Brique):
    nom = "routeur"
    niveau = "N1"

    def run(self, ctx: Contexte) -> Contexte:
        defaut = self.params.get("defaut", "hybride")
        if not self.params.get("regles_actives", True):
            ctx.route = defaut
            ctx.noter(self.nom, route=defaut, motif="règles désactivées")
            return ctx

        question = ctx.question.strip()
        mots = question.split()
        raisons = []

        motifs_trouves = [m.pattern for m in MOTIFS_LITTERAUX if m.search(question)]
        if motifs_trouves:
            raisons.append("termes littéraux détectés")

        # Requête très courte sans verbe : plutôt un mot-clé qu'une question.
        if len(mots) <= int(self.params.get("seuil_mots_courts", 3)):
            raisons.append("requête courte, type mot-clé")

        # Décision. On n'écarte JAMAIS le vectoriel : les signaux ci-dessus
        # indiquent que BM25 sera utile, pas que la sémantique sera inutile.
        # L'asymétrie est voulue — un moteur en trop coûte du temps, un moteur
        # en moins coûte un passage introuvable.
        route = defaut
        if raisons and defaut != "bm25":
            route = "hybride"

        ctx.route = route
        ctx.noter(self.nom, route=route, raisons=raisons,
                  motifs=motifs_trouves, n_mots=len(mots))

        # Phase 2 — l'ouverture du coffre de données personnelles ne se décide
        # pas ici. Elle restera une escalade explicite de l'utilisateur, jamais
        # une inférence du routeur : « le modèle a décidé seul d'ouvrir le
        # dossier patient » n'est pas une gouvernance tenable.
        ctx.ouvrir_coffre = False
        return ctx
