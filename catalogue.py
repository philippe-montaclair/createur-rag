#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
catalogue.py — Choisir un modèle en connaissance de cause, et refuser l'absurde.
================================================================================
Deux services, l'un confortable, l'autre indispensable :

1. RÉSOUDRE et RECOMMANDER. Les profils écrivent un alias (`fr-generaliste`)
   au lieu d'un chemin Hugging Face. `recommander()` filtre le catalogue par
   langue, domaine et budget mémoire. Il PROPOSE, il ne choisit jamais seul —
   même principe que le routeur : une règle qui décide en silence est une règle
   qu'on ne peut ni auditer, ni régler.

2. VÉRIFIER LA COMPATIBILITÉ INDEX / EMBEDDEUR. C'est le vrai garde-fou.
   Interroger un index avec un embeddeur autre que celui qui l'a construit est
   une faute silencieuse : si les dimensions diffèrent, Chroma proteste ; si
   elles coïncident par hasard (768 est très courant), **la recherche renvoie
   du bruit sans le moindre message d'erreur**. On préfère refuser de démarrer.

Note sur les chiffres du catalogue : `dimension` y est DÉCLARÉE, donc faillible.
La vérification, elle, compare la dimension RÉELLE du modèle chargé à celle
réellement stockée dans la collection. Le déclaratif sert à choisir, l'observé
sert à valider — on ne fait jamais confiance au premier pour décider du second.
"""

from __future__ import annotations

from pathlib import Path

RACINE = Path(__file__).resolve().parent
CATALOGUE_DEFAUT = RACINE / "modeles.yaml"

CATEGORIES = ("embeddeurs", "rerankers", "llm")
_cache: dict = {}


def charger(chemin: str | Path | None = None) -> dict:
    import yaml
    chemin = Path(chemin or CATALOGUE_DEFAUT)
    cle = str(chemin)
    if cle not in _cache:
        _cache[cle] = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    return _cache[cle]


# ─────────────────────────────────────────────────────────────────────────────
# Résolution
# ─────────────────────────────────────────────────────────────────────────────
def resoudre(categorie: str, reference: str, chemin: str | Path | None = None) -> dict:
    """alias OU nom complet → fiche du modèle.

    Un nom hors catalogue reste accepté (on ne bloque pas l'expérimentation),
    mais renvoyé avec `hors_catalogue: True` pour que l'appelant puisse le
    signaler plutôt que de le traiter comme validé.
    """
    if categorie not in CATEGORIES:
        raise ValueError(f"Catégorie inconnue : {categorie!r} (attendu : {', '.join(CATEGORIES)})")
    section = charger(chemin).get(categorie, {}) or {}

    if reference in section:
        return {"alias": reference, **section[reference]}

    for alias, fiche in section.items():
        if fiche.get("nom") == reference:
            return {"alias": alias, **fiche}

    return {"alias": None, "nom": reference, "hors_catalogue": True}


def recommander(categorie: str, langue: str | None = None, domaine: str | None = None,
                ram_max_mo: int | None = None, environnement: str | None = None,
                precision: str = "float32", chemin: str | Path | None = None) -> list[dict]:
    """Filtre le catalogue. Renvoie les candidats, du plus léger au plus lourd."""
    section = charger(chemin).get(categorie, {}) or {}
    champ = ("empreinte_mo" if categorie == "llm"
             else f"empreinte_{precision}_mo")

    retenus = []
    for alias, fiche in section.items():
        if langue and fiche.get("langue") not in (langue, "multilingue"):
            continue
        if domaine and fiche.get("domaine") not in (domaine, "generaliste"):
            continue
        if environnement and fiche.get("disponible") not in (environnement, "les deux"):
            continue
        poids = fiche.get(champ) or fiche.get("empreinte_float32_mo") or 0
        if ram_max_mo and poids > ram_max_mo:
            continue
        retenus.append({"alias": alias, "poids_mo": poids, **fiche})

    return sorted(retenus, key=lambda f: f["poids_mo"])


# ─────────────────────────────────────────────────────────────────────────────
# Garde-fou : l'index et l'embeddeur doivent se correspondre
# ─────────────────────────────────────────────────────────────────────────────
class IncompatibiliteIndex(RuntimeError):
    """Levée quand l'embeddeur demandé ne peut pas avoir produit cet index."""


def dimension_index(collection) -> int | None:
    """Dimension réellement stockée dans la collection Chroma."""
    try:
        echantillon = collection.get(limit=1, include=["embeddings"])
        vecteurs = echantillon.get("embeddings")
        if vecteurs is not None and len(vecteurs) > 0 and vecteurs[0] is not None:
            return len(vecteurs[0])
    except Exception:
        pass
    return None


def dimension_modele(modele) -> int | None:
    """Dimension réellement produite par le modèle chargé.

    Le nom de la méthode a changé côté sentence-transformers
    (`get_sentence_embedding_dimension` → `get_embedding_dimension`). On essaie
    le nouveau d'abord, puis l'ancien : la version installée sur le Mac n'est pas
    forcément celle du VPS, et une dépréciation ne doit pas arrêter un pipeline
    h24. Repli final : encoder un texte et mesurer — toujours vrai, jamais rapide.
    """
    for methode in ("get_embedding_dimension", "get_sentence_embedding_dimension"):
        fonction = getattr(modele, methode, None)
        if fonction is None:
            continue
        try:
            d = fonction()
            if d:
                return int(d)
        except Exception:
            continue
    try:
        return int(len(modele.encode(["test"])[0]))
    except Exception:
        return None


def verifier_compatibilite(collection, modele, nom_modele: str,
                           collection_nom: str = "") -> dict:
    """Vérifie que l'index a bien été construit par CE modèle.

    Deux contrôles, du plus fort au plus faible :

      1. le NOM de l'embeddeur, inscrit dans les métadonnées de la collection à
         l'indexation (depuis le 31/07/2026). C'est le vrai verrou : il distingue
         deux modèles de même dimension, ce que le contrôle de dimension ne sait
         pas faire — et 768 est une dimension si répandue que la coïncidence est
         la règle plutôt que l'exception.
      2. la DIMENSION des vecteurs, seul recours pour les index construits avant
         cette date. Barrière contre l'erreur grossière, pas preuve d'identité.

    Un index ancien, sans nom inscrit, ne fait pas échouer le démarrage : il
    serait absurde de rendre `corpus_demo` inutilisable pour une métadonnée
    manquante. Il est signalé, et la seule façon de le mettre en règle est de le
    réindexer — ce qui est exactement ce qu'il faut dire à l'utilisateur.
    """
    attendu = None
    try:
        attendu = (collection.metadata or {}).get("embeddeur")
    except Exception:
        attendu = None

    if attendu and nom_modele and attendu != nom_modele:
        raise IncompatibiliteIndex(
            f"L'embeddeur et l'index ne correspondent pas.\n"
            f"  collection '{collection_nom}' construite avec : {attendu}\n"
            f"  profil actuel                                 : {nom_modele}\n\n"
            f"  Les vecteurs de deux modèles ne vivent pas dans le même espace :\n"
            f"  la recherche renverrait du bruit, sans lever d'erreur.\n"
            f"  → réindexer avec ce modèle, ou revenir à l'embeddeur d'origine."
        )

    d_index = dimension_index(collection)
    d_modele = dimension_modele(modele)

    if d_index is None or d_modele is None:
        return {"verifie": False, "index": d_index, "modele": d_modele,
                "embeddeur_index": attendu}

    if d_index != d_modele:
        raise IncompatibiliteIndex(
            f"L'embeddeur et l'index ne correspondent pas.\n"
            f"  collection '{collection_nom}' : vecteurs de dimension {d_index}\n"
            f"  modèle '{nom_modele}'          : vecteurs de dimension {d_modele}\n\n"
            f"  Cet index a été construit avec un AUTRE modèle. Interroger l'un\n"
            f"  avec l'autre ne renverrait que du bruit.\n"
            f"  → réindexer avec ce modèle, ou pointer la collection d'origine."
        )
    return {"verifie": True, "index": d_index, "modele": d_modele,
            "embeddeur_index": attendu,
            "identite_verifiee": bool(attendu)}


# ─────────────────────────────────────────────────────────────────────────────
# Affichage
# ─────────────────────────────────────────────────────────────────────────────
def modeles_ollama_presents(hote: str = "http://localhost:11434") -> set[str]:
    """Ce qui est RÉELLEMENT téléchargé — le catalogue déclare le pertinent,
    Ollama seul sait ce qui est là."""
    try:
        from backends.ollama import BackendOllama
        client = BackendOllama(hote=hote)._client_ollama()
        return {m.get("model", m.get("name", "")) for m in client.list().get("models", [])}
    except Exception:
        return set()


def tableau(categorie: str, chemin: str | Path | None = None,
            presents: set[str] | None = None) -> str:
    section = charger(chemin).get(categorie, {}) or {}
    if not section:
        return f"(catégorie '{categorie}' vide)"

    lignes = [f"\n{categorie.upper()}"]
    for alias, f in section.items():
        poids = f.get("empreinte_mo") or f.get("empreinte_float32_mo") or 0
        marque = ""
        if presents is not None and categorie == "llm":
            marque = "  ✅ présent" if f.get("nom") in presents else "  ⬇️  à télécharger"
        dim = f"  dim {f['dimension']}" if f.get("dimension") else ""
        lignes.append(
            f"  {alias:<20} {f.get('nom', '?'):<48} "
            f"{f.get('langue', '?'):<12} {f.get('domaine', '—'):<12} "
            f"{poids:>6} Mo{dim}{marque}"
        )
        if f.get("prefixe_requete"):
            lignes.append(f"  {'':<20} ⚠️  exige les préfixes "
                          f"{f['prefixe_requete']!r} / {f['prefixe_document']!r}")
    return "\n".join(lignes)
