#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contrat.py — Le contrat commun à toutes les briques du créateur de RAG.
=======================================================================
Tout repose sur ce fichier. Une brique = un agent du REGISTRE de la banque
(routeur, recherche-vectorielle, fusion, reranker...). Elles ne se connaissent
pas entre elles : elles partagent seulement ce contrat.

Pourquoi un contexte PARTAGÉ plutôt que des entrées/sorties typées par brique ?
------------------------------------------------------------------------------
L'alternative « chaque brique a sa signature propre » est plus propre sur le
papier et colle mieux aux fiches de la banque. Elle a été écartée pour une
raison précise : l'agent RÉGLEUR doit pouvoir retirer, ajouter ou réordonner
une brique sans réécrire de code. Avec des signatures différentes, enlever la
fusion casserait le chaînage. Avec un contexte partagé, chaque brique lit ce
dont elle a besoin, écrit son résultat, et passe la main — le pipeline reste
recomposable à chaud depuis un simple fichier YAML.

Trois objets seulement :
  Passage    un morceau de document récupéré (+ sa provenance)
  Contexte   l'état d'UNE question qui traverse le pipeline
  Ressources les objets lourds partagés (modèles, index) — chargés une fois
  Brique     la classe de base que tout agent implémente
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# 1) Le passage — l'unité qui circule
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Passage:
    """Un chunk récupéré, avec de quoi le citer.

    `id` est l'IDENTIFIANT STABLE du chunk, de la forme "source::locator::n"
    (repris tel quel d'ingest_tuteur.py). Sa stabilité n'est pas un détail :
    c'est la clé qui permettra, en phase 2, de relier ce passage pseudonymisé
    à sa version en clair dans le coffre, sans réindexer quoi que ce soit.
    """
    id: str
    texte: str
    source: str = ""
    locator: str = ""
    score: float | None = None          # score de la dernière brique qui l'a noté

    # ── Phase 2 (pré-traitement / RGPD) — réservé, non utilisé en phase 1 ────
    # Ces deux champs existent DÈS MAINTENANT à dessein. Les ajouter plus tard
    # imposerait de reconstruire tout l'index : les métadonnées d'un chunk sont
    # figées au moment de l'indexation.
    entites: list[str] = field(default_factory=list)   # ["PERSONNE_3", "IBAN_1"]
    texte_clair: str | None = None                     # rempli à la ré-hydratation

    def citation(self) -> str:
        return f"{self.source} {self.locator}".strip()


# ─────────────────────────────────────────────────────────────────────────────
# 2) Le contexte — l'état d'une question qui traverse le pipeline
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Contexte:
    """Ce que les briques se passent de main en main.

    Chaque brique remplit sa part. Une brique absente du profil laisse
    simplement son champ vide — les suivantes doivent en tenir compte.
    """
    question: str

    # N1 — routage
    route: str = "hybride"              # "vectorielle" | "bm25" | "hybride"

    # Filtre par métadonnées, appliqué à TOUS les moteurs de recherche.
    # Dans le contexte et non dans les params d'une brique : filtrer le vectoriel
    # sans filtrer BM25 laisserait la fusion réintroduire des chunks hors
    # périmètre — une fuite silencieuse, et la pire espèce de bug ici.
    filtre: dict | None = None

    # N2 — recherche : chaque moteur dépose sa liste d'ids classés sous son nom.
    # La fusion lit ce dictionnaire ; sans fusion, la dernière recherche fait foi.
    listes: dict[str, list[str]] = field(default_factory=dict)

    # Scores BRUTS de chaque moteur : {"vectorielle": {id: 0.83}, "bm25": {...}}.
    # Ajouté le 31/07/2026 pour la fusion pondérée. Les listes ne portaient que
    # des RANGS, ce qui suffisait à la RRF — mais rendait toute fusion par score
    # impossible, et rendait surtout invisible la distribution réelle des scores.
    # C'est de cette invisibilité que vient le point ouvert de la phase 1 sur
    # `validateur_chunks.score_min` : on ne peut pas régler un seuil sur des
    # valeurs qu'on ne voit pas.
    #
    # Convention : PLUS GRAND = MEILLEUR, quel que soit le moteur. Le vectoriel
    # convertit donc sa distance en similarité avant de déposer.
    scores: dict[str, dict[str, float]] = field(default_factory=dict)

    candidats: list[Passage] = field(default_factory=list)

    # N3 — sélection finale (après rerank / validation)
    passages: list[Passage] = field(default_factory=list)
    bloc_contexte: str = ""

    # N4 — génération
    prompt: str = ""
    reponse: str = ""
    citations: list[str] = field(default_factory=list)

    # N0 — observabilité
    traces: list[dict] = field(default_factory=list)
    notes: dict[str, dict] = field(default_factory=dict)

    # Incidents survenus pendant cette question (briques tombées, repliées ou non).
    # Volontairement DANS le contexte et non dans le journal : une brique en aval
    # doit pouvoir savoir qu'une brique amont a sauté.
    erreurs: list[dict] = field(default_factory=list)

    # Phase 2 — l'accès au clair est une ESCALADE EXPLICITE, jamais un défaut.
    ouvrir_coffre: bool = False

    def noter(self, brique: str, **valeurs: Any) -> None:
        """Une brique dépose ici ce qu'elle veut voir apparaître dans sa trace."""
        self.notes.setdefault(brique, {}).update(valeurs)

    # ── Repli sur erreur : instantané / restauration ─────────────────────────
    # Une brique modifie le contexte EN PLACE. Si elle vide `passages` puis lève
    # une exception avant de les remplir, attraper l'exception ne rétablit rien :
    # le pipeline continuerait sur un état à moitié détruit, et le symptôme
    # apparaîtrait trois briques plus loin, dans une brique innocente.
    #
    # D'où l'instantané : « ignorer une brique » doit vouloir dire « comme si elle
    # n'avait pas tourné », pas « comme si elle avait tourné à moitié ».
    def instantane(self) -> dict:
        """Copie des champs de travail, avant l'exécution d'une brique.

        Copie SUPERFICIELLE des listes : on duplique les listes, pas les Passage
        qu'elles contiennent. Limite assumée — une brique qui modifie un Passage
        en place (le reranker y pose un `score`) laisse cette trace même après
        restauration. Copier en profondeur coûterait plus cher que le repli ne
        rapporte, et le score d'un passage écarté n'est jamais relu.
        """
        return {
            "route": self.route,
            "filtre": self.filtre,
            "listes": {moteur: list(ids) for moteur, ids in self.listes.items()},
            "scores": {moteur: dict(v) for moteur, v in self.scores.items()},
            "candidats": list(self.candidats),
            "passages": list(self.passages),
            "bloc_contexte": self.bloc_contexte,
            "prompt": self.prompt,
            "reponse": self.reponse,
            "citations": list(self.citations),
            "ouvrir_coffre": self.ouvrir_coffre,
        }

    def restaurer(self, instantane: dict) -> None:
        """Remet l'état d'avant la brique.

        `traces`, `notes` et `erreurs` sont volontairement absents de
        l'instantané : la mémoire de l'incident doit SURVIVRE au repli. Un repli
        qui efface aussi la trace de ce qu'il a rattrapé serait un mensonge.
        """
        for champ, valeur in instantane.items():
            setattr(self, champ, valeur)


# ─────────────────────────────────────────────────────────────────────────────
# 3) Les ressources — les objets lourds, chargés une seule fois
# ─────────────────────────────────────────────────────────────────────────────
class Ressources:
    """Modèles et index partagés par toutes les briques.

    Séparés du Contexte parce qu'ils ne dépendent pas de la question : on les
    charge une fois pour tout le corpus, pas à chaque interrogation.

    Chargement PARESSEUX (à la première demande) : un profil « minimal » ne
    doit pas payer le chargement du reranker. Sur 16 Go de RAM unifiée, chaque
    modèle non chargé est de la RAM rendue au LLM.
    """

    def __init__(self, config: dict):
        self.config = config
        self._objets: dict[str, Any] = {}

    def obtenir(self, nom: str, fabrique) -> Any:
        """Renvoie l'objet `nom`, en le construisant à la première demande."""
        if nom not in self._objets:
            self._objets[nom] = fabrique()
        return self._objets[nom]

    def decharger(self, nom: str) -> bool:
        """Libère un objet et rend sa RAM. Renvoie True s'il y avait quelque chose.

        Utilisé pour le reranker CamemBERT juste avant l'appel au LLM : les deux
        ensemble tiennent mal à côté d'un qwen3:8b sur 16 Go partagés.
        """
        if nom not in self._objets:
            return False
        del self._objets[nom]
        try:
            import gc
            import torch
            gc.collect()
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
        except Exception:
            pass
        return True

    def charges(self) -> list[str]:
        return sorted(self._objets)


# ─────────────────────────────────────────────────────────────────────────────
# 4) La brique — la classe de base de tout agent
# ─────────────────────────────────────────────────────────────────────────────
class Brique:
    """Un agent du REGISTRE, sous forme exécutable.

    Une brique fait UNE chose (principe d'AGENTS.md §2.2). Elle ne connaît ni
    celle d'avant ni celle d'après : elle lit le contexte, le modifie, le rend.

    Pour en écrire une :
        class MaBrique(Brique):
            nom = "ma_brique"
            niveau = "N2"
            def run(self, ctx: Contexte) -> Contexte:
                ...
                ctx.noter(self.nom, ce_qui_compte=42)
                return ctx
    """

    nom: str = "brique"
    niveau: str = ""          # N0..N5, tel qu'inscrit dans REGISTRE.md

    # ── Repli sur erreur (principe du PDF : « si le reranker plante, on utilise
    # les chunks bruts »). Réglé par brique dans le profil YAML :
    #     - reranker: {garde: 8, sur_erreur: ignorer}
    #
    # Défaut « arreter » à dessein : en développement on veut voir ses erreurs,
    # pas les avaler, et le témoin de non-régression doit rester intact. C'est le
    # profil `total`, destiné au h24, qui déclare ses replis explicitement.
    POLITIQUES = ("arreter", "ignorer")
    MAX_ECHECS_DEFAUT = 3

    def __init__(self, params: dict | None = None, ressources: Ressources | None = None):
        self.params = params or {}
        self.ressources = ressources

        self.sur_erreur = str(self.params.get("sur_erreur", "arreter")).lower()
        if self.sur_erreur not in self.POLITIQUES:
            # Refus explicite plutôt que retour silencieux au défaut : une faute
            # de frappe (`ignore` pour `ignorer`) donnerait un pipeline qui
            # s'arrête alors qu'on le croit protégé — exactement le genre de
            # panne qu'on cherche à éviter.
            raise ValueError(
                f"Brique '{self.nom}' : sur_erreur={self.sur_erreur!r} inconnu. "
                f"Valeurs admises : {' | '.join(self.POLITIQUES)}.")

        # Le repli couvre l'incident passager, pas la panne installée. Au-delà de
        # `max_echecs` échecs CONSÉCUTIFS, la brique repasse en 'arreter' : sans
        # ce compteur, un reranker mort le lundi dégraderait silencieusement la
        # qualité jusqu'au vendredi, traces au vert.
        self.max_echecs = int(self.params.get("max_echecs", self.MAX_ECHECS_DEFAUT))
        self.echecs_consecutifs = 0

    def run(self, ctx: Contexte) -> Contexte:      # pragma: no cover
        raise NotImplementedError(
            f"La brique '{self.nom}' n'implémente pas run(ctx)."
        )

    def __repr__(self) -> str:
        return f"<{self.niveau} {self.nom} {self.params}>"
