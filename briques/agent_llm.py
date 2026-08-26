#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_llm.py — Agent N4 « agent-llm » du REGISTRE.
==================================================
Repris de Tuteur.repondre() (l'appel Ollama).

Rôle : générer la réponse à partir du prompt augmenté.

Deux choses à savoir :

1. Température 0 par défaut. Sur un RAG, la créativité est un défaut : on veut
   que la même question sur le même contexte donne la même réponse. C'est aussi
   la condition pour que l'agent régleur puisse mesurer quoi que ce soit — avec
   une température élevée, il attribuerait au réglage des écarts qui ne sont
   que du hasard d'échantillonnage.

2. C'est le goulot de latence, et de loin. Le journal le confirmera à chaque
   question. C'est pourquoi cette brique sait décharger le reranker juste avant
   de générer : sur 16 Go de RAM unifiée, CamemBERT (~0,5 Go) + Marsilia
   (~0,5 Go) + qwen3:8b en Q4 (~5 Go) + macOS, la marge est mince, et une
   machine qui swappe multiplie le temps de génération.
"""

from __future__ import annotations

from contrat import Brique, Contexte
from briques.communs import charger_backend


class AgentLLM(Brique):
    nom = "agent_llm"
    niveau = "N4"

    def run(self, ctx: Contexte) -> Contexte:
        if not ctx.prompt:
            ctx.reponse = ("Je n'ai trouvé aucun extrait pertinent pour répondre "
                           "à cette question.")
            ctx.noter(self.nom, ignoree=True, motif="prompt vide")
            return ctx

        if self.params.get("decharger_reranker", True):
            if self.ressources.decharger("reranker"):
                ctx.noter(self.nom, reranker_decharge=True)

        import catalogue

        backend = charger_backend(self.ressources, self.params.get("backend", "ollama"))
        # Le profil peut écrire un alias du catalogue ('qwen3-8b') ou
        # directement le tag Ollama ('qwen3:8b') — les deux fonctionnent.
        fiche = catalogue.resoudre("llm", self.params.get("modele", "qwen3:8b"))
        modele = fiche["nom"]
        temperature = float(self.params.get("temperature", 0.0))

        ctx.reponse = backend.generer(ctx.prompt, modele=modele, temperature=temperature)

        ctx.noter(self.nom, backend=backend.nom, modele=modele,
                  alias=fiche.get("alias"),
                  temperature=temperature,
                  longueur_reponse=len(ctx.reponse),
                  modeles_en_ram=self.ressources.charges())
        return ctx
