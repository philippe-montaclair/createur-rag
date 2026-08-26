#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
communs.py — Ce que plusieurs briques partagent (modèles, corpus, tokenisation).
================================================================================
Tout ce qui est ici est repris à l'identique de tuteur-local (ingest_tuteur.py et
tuteur.py). Rien n'a été réécrit : on déplace du code déjà éprouvé.

Les fonctions `charger_*` passent par Ressources.obtenir(), donc un objet lourd
n'est construit qu'UNE fois, à la première brique qui le réclame. Un profil
« minimal » ne charge jamais le reranker — sur 16 Go de RAM unifiée, c'est
exactement la RAM qu'on veut laisser au LLM.
"""

from __future__ import annotations

import re
from pathlib import Path

from contrat import Ressources

RACINE = Path(__file__).resolve().parent.parent      # createur-rag/
PROJETS = RACINE.parent                              # Projects/

# Modèles FR déjà téléchargés dans les autres projets — on ne re-télécharge pas.
# (liste reprise de tuteur.py, élargie à createur-rag/)
CACHES_MODELES = [
    RACINE / "models_cache",
    PROJETS / "tuteur-local" / "models_cache",
    PROJETS / "rag-finance" / "models_cache",
    PROJETS / "rag_lici" / "models_cache",
    PROJETS / "rag_juridique" / "models_cache",
    PROJETS / "assistant-gestion-locative-public" / "models_cache",
]

MODELE_EMBED_DEFAUT = "sujet-ai/Marsilia-Embeddings-FR-Base"
MODELE_RERANK_DEFAUT = "antoinelouis/crossencoder-camembert-base-mmarcoFR"


def cache_modeles() -> str | None:
    for p in CACHES_MODELES:
        if p.exists():
            return str(p)
    return None


def tokenize(texte: str) -> list[str]:
    """Tokenisation BM25 — identique à tuteur.py."""
    return re.findall(r"\w+", texte.lower())


# ─────────────────────────────────────────────────────────────────────────────
# Objets lourds, chargés paresseusement
# ─────────────────────────────────────────────────────────────────────────────
def appliquer_precision(modele, precision: str | None):
    """Bascule un modèle en demi-précision si le profil le demande.

    Mesuré le 25/07/2026 : les deux modèles chargent en float32 sur MPS et
    occupent 1 483 Mo à eux deux (Marsilia 278 M paramètres = 1 061 Mo,
    CamemBERT 110,6 M = 422 Mo). En float16 ils tombent à ~740 Mo — près de
    750 Mo rendus, sur une machine où la marge avant swap se compte en
    centaines de Mo.

    Ce n'est PAS gratuit : la demi-précision peut modifier les scores en
    dernières décimales, donc l'ordre de deux chunks très proches. D'où la
    règle : on ne l'active qu'après avoir vérifié avec
    tests/test_non_regression.py que la récupération est inchangée.
    """
    if not precision or precision == "float32":
        return modele
    if precision not in ("float16", "half"):
        raise ValueError(f"Précision inconnue : {precision!r} "
                         "(attendu : float32 | float16)")
    cible = getattr(modele, "model", modele)
    cible.half()
    return modele


def fiche_embeddeur(res: Ressources) -> dict:
    """Fiche catalogue de l'embeddeur du profil (alias résolu, préfixes, etc.)."""
    def _fab():
        import catalogue
        conf = res.config.get("embeddings", {})
        return catalogue.resoudre("embeddeurs", conf.get("modele", MODELE_EMBED_DEFAUT))
    return res.obtenir("fiche_embeddeur", _fab)


def charger_embed(res: Ressources):
    """Le bi-encodeur qui vectorise. Sert à l'ingestion ET à la recherche —
    c'est forcément LE MÊME modèle des deux côtés, sinon les vecteurs de la
    question et ceux du corpus ne vivent pas dans le même espace."""
    def _fab():
        from sentence_transformers import SentenceTransformer
        conf = res.config.get("embeddings", {})
        modele = SentenceTransformer(fiche_embeddeur(res)["nom"],
                                     cache_folder=cache_modeles())
        return appliquer_precision(modele, conf.get("precision"))
    return res.obtenir("embed", _fab)


def charger_collection(res: Ressources):
    """La collection ChromaDB déjà indexée."""
    def _fab():
        import chromadb
        dossier = str(res.config["chroma_dir"])
        nom = res.config["collection"]
        client = chromadb.PersistentClient(path=dossier)
        try:
            return client.get_collection(nom)
        except Exception as e:
            # Message utile plutôt qu'une pile d'exceptions : l'oubli du bon
            # --chroma-dir est l'erreur la plus fréquente, et la trace brute de
            # Chroma ne la désigne pas.
            dispo = [c.name for c in client.list_collections()]
            raise SystemExit(
                f"\nCollection '{nom}' introuvable dans {dossier}\n"
                + (f"  Collections présentes ici : {', '.join(dispo)}\n"
                   if dispo else "  Ce dossier ne contient aucune collection.\n")
                + "  → vérifie --collection, ou pointe le bon dossier avec "
                  "--chroma-dir (ex. ../tuteur-local/chroma_db).\n"
            ) from e
    return res.obtenir("collection", _fab)


def charger_corpus(res: Ressources) -> dict:
    """Lit une fois tout le corpus depuis Chroma et prépare les index dérivés.

    Repris de Tuteur.__init__ : l'index BM25 est construit UNE fois sur tout le
    corpus, pas à chaque question.
    """
    def _fab():
        from rank_bm25 import BM25Okapi
        col = charger_collection(res)
        data = col.get(include=["documents", "metadatas"])
        ids = data["ids"]
        return {
            "ids": ids,
            "texte_par_id": dict(zip(ids, data["documents"])),
            "meta_par_id": dict(zip(ids, data["metadatas"])),
            "bm25": BM25Okapi([tokenize(t) for t in data["documents"]]),
        }
    return res.obtenir("corpus", _fab)


def charger_reranker(res: Ressources):
    """Le cross-encoder FR. Lourd : ne se charge que si le profil l'active."""
    def _fab():
        import catalogue
        from sentence_transformers import CrossEncoder
        conf = res.config.get("reranker", {})
        fiche = catalogue.resoudre("rerankers", conf.get("modele", MODELE_RERANK_DEFAUT))
        return appliquer_precision(CrossEncoder(fiche["nom"]), conf.get("precision"))
    return res.obtenir("reranker", _fab)


def charger_backend(res: Ressources, nom: str = "ollama"):
    """Le moteur de génération. Une seule implémentation aujourd'hui (Ollama) ;
    l'indirection existe pour que le choix reste réversible."""
    def _fab():
        if nom == "ollama":
            from backends.ollama import BackendOllama
            return BackendOllama(**res.config.get("backend", {}))
        raise ValueError(f"Backend inconnu : {nom!r} (attendu : 'ollama').")
    return res.obtenir(f"backend:{nom}", _fab)


# ─────────────────────────────────────────────────────────────────────────────
# Filtres par métadonnées
# ─────────────────────────────────────────────────────────────────────────────
# Chroma sait filtrer nativement (`where=`). BM25, non : rank_bm25 ne connaît
# que du texte. Il faut donc réappliquer le MÊME filtre à la main sur sa sortie.
#
# Le risque, si on ne le fait pas : le vectoriel respecte le périmètre, BM25
# l'ignore, et la fusion réintroduit tranquillement des chunks exclus. Le
# système paraît filtré et ne l'est pas.
OPERATEURS = ("$eq", "$ne", "$in", "$nin")


def correspond(meta: dict, filtre: dict | None) -> bool:
    """Le chunk satisfait-il le filtre ? Sous-ensemble volontaire de la syntaxe Chroma.

    Un opérateur reconnu par Chroma mais pas réimplémenté ici lève une erreur au
    lieu d'être ignoré. C'est délibéré : le laisser passer donnerait deux moteurs
    qui appliquent deux filtres différents, donc un périmètre respecté à moitié —
    exactement la faute silencieuse qu'on cherche à rendre impossible.
    """
    if not filtre:
        return True
    meta = meta or {}
    for cle, attendu in filtre.items():
        if cle.startswith("$"):
            if cle == "$and":
                if not all(correspond(meta, sous) for sous in attendu):
                    return False
                continue
            if cle == "$or":
                if not any(correspond(meta, sous) for sous in attendu):
                    return False
                continue
            raise ValueError(
                f"Filtre : opérateur {cle!r} non réimplémenté pour BM25. "
                f"Admis : $and, $or, {', '.join(OPERATEURS)}. "
                "Un filtre que les deux moteurs n'appliquent pas à l'identique "
                "est refusé plutôt qu'appliqué à moitié.")

        valeur = meta.get(cle)
        if isinstance(attendu, dict):
            for op, ref in attendu.items():
                if op not in OPERATEURS:
                    raise ValueError(
                        f"Filtre : opérateur {op!r} non réimplémenté pour BM25 "
                        f"(admis : {', '.join(OPERATEURS)}).")
                if op == "$eq" and valeur != ref:
                    return False
                if op == "$ne" and valeur == ref:
                    return False
                if op == "$in" and valeur not in ref:
                    return False
                if op == "$nin" and valeur in ref:
                    return False
        elif valeur != attendu:
            return False
    return True


def passages_depuis_ids(res: Ressources, ids: list[str], scores=None) -> list:
    """Transforme une liste d'identifiants en objets Passage (texte + provenance)."""
    from contrat import Passage
    corpus = charger_corpus(res)
    sortie = []
    for i, cid in enumerate(ids):
        meta = corpus["meta_par_id"].get(cid) or {}
        sortie.append(Passage(
            id=cid,
            texte=corpus["texte_par_id"].get(cid, ""),
            source=meta.get("source", "?"),
            locator=meta.get("locator", ""),
            score=(scores[i] if scores is not None else None),
            entites=(meta.get("entites") or "").split("|") if meta.get("entites") else [],
        ))
    return sortie
