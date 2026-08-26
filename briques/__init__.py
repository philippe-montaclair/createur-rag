#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
briques/__init__.py — Le catalogue des briques disponibles.
===========================================================
C'est la table de correspondance entre un NOM écrit dans un profil YAML et la
classe Python qui l'implémente.

Ce dictionnaire est le pendant exécutable du REGISTRE.md de la banque d'agents :
là-bas on choisit un agent sur fiche, ici on l'instancie. Ajouter une brique au
projet = une ligne ici, et elle devient utilisable dans n'importe quel profil
sans toucher à l'assembleur.
"""

from briques.constructeur_contexte import ConstructeurContexte
from briques.fusion import Fusion
from briques.agent_llm import AgentLLM
from briques.post_processing import PostProcessing
from briques.prompt_engineering import PromptEngineering
from briques.recherche_bm25 import RechercheBM25
from briques.recherche_vectorielle import RechercheVectorielle
from briques.reranker import Reranker
from briques.routeur import Routeur
from briques.validateur_chunks import ValidateurChunks

CATALOGUE = {
    # N1 — aiguillage
    "routeur": Routeur,
    # N2 — recherche
    "recherche_vectorielle": RechercheVectorielle,
    "recherche_bm25": RechercheBM25,
    "fusion": Fusion,
    # N3 — sélection
    "reranker": Reranker,
    "validateur_chunks": ValidateurChunks,
    "constructeur_contexte": ConstructeurContexte,
    # N4 — génération
    "prompt_engineering": PromptEngineering,
    "agent_llm": AgentLLM,
    "post_processing": PostProcessing,
}

__all__ = ["CATALOGUE"]
