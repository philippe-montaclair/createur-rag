#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backends/ollama.py — Le moteur de génération.
=============================================
Repris de tuteur.py (`ollama.chat`, temperature 0, think=False).

Pourquoi Ollama plutôt que LM Studio (décision du 25/07/2026) :
  · déjà installé et déjà utilisé par tuteur-local et web-scraping ;
  · `ollama serve` est un vrai démon sans interface — indispensable le jour où
    l'agent régleur tournera sans personne devant l'écran ;
  · déchargement automatique du modèle après inactivité, ce qui rend la RAM.

LM Studio reste le bon outil pour COMPARER des modèles (son interface montre la
RAM et les tokens/s en direct) ; il n'est pas le bon outil pour faire tourner un
pipeline en autonomie. D'où cette indirection : le jour où le besoin change, on
ajoute backends/lmstudio.py avec la même méthode `generer()`, sans toucher aux
briques.

Attention : les EMBEDDINGS et le RERANKER ne passent pas par ici. Ils restent
sur sentence-transformers/MPS, parce que ni Ollama ni LM Studio ne servent
Marsilia-FR ni un cross-encoder CamemBERT.
"""

from __future__ import annotations


class BackendOllama:
    """Interface minimale : une méthode, `generer()`."""

    nom = "ollama"

    def __init__(self, hote: str = "http://localhost:11434", garder_en_vie: str = "5m"):
        self.hote = hote
        self.garder_en_vie = garder_en_vie
        self._client = None

    def _client_ollama(self):
        if self._client is None:
            import ollama
            self._client = ollama.Client(host=self.hote)
        return self._client

    def generer(self, prompt: str, modele: str = "qwen3:8b",
                temperature: float = 0.0, **options) -> str:
        """Renvoie le texte généré.

        `think=False` désactive le mode raisonnement des modèles qwen3 : sans
        lui, la réponse arrive encapsulée dans des balises de réflexion et le
        temps de génération explose. Repris tel quel de tuteur.py.
        """
        reponse = self._client_ollama().chat(
            model=modele,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": temperature, **options},
            keep_alive=self.garder_en_vie,
            think=False,
        )
        return reponse["message"]["content"]

    def disponible(self) -> tuple[bool, str]:
        """Vérifie que le démon répond — message d'erreur utile plutôt qu'une
        pile d'exceptions au milieu d'une indexation."""
        try:
            modeles = self._client_ollama().list().get("models", [])
            noms = [m.get("model", m.get("name", "?")) for m in modeles]
            return True, f"{len(noms)} modèle(s) : {', '.join(noms[:6])}"
        except Exception as e:
            return False, f"Ollama injoignable sur {self.hote} ({e}). Lance `ollama serve`."
