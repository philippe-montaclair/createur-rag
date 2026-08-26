#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ingestion.py — Lecture, découpage, vectorisation, indexation.
=============================================================
Repris d'ingest_tuteur.py, généralisé. Le moteur de découpage (`chunk_text`)
est copié À L'IDENTIQUE : c'est du code déjà éprouvé sur un vrai corpus, et
toute modification devrait être mesurée avant d'être gardée.

Pourquoi ce n'est PAS une Brique
--------------------------------
Les briques du pipeline traitent une QUESTION (elles reçoivent un Contexte).
L'ingestion, elle, traite un CORPUS, une fois, avant toute question. Deux
cycles de vie différents : les mélanger derrière la même interface aurait été
une abstraction de façade. Le REGISTRE de la banque n'ayant aucun agent pour
cette étape, une fiche `ingestion-chunking` (N0) sera créée pour combler ce
manque — c'est pourtant l'étape la plus déterminante pour la qualité finale.

Point d'accroche pour la phase 2
--------------------------------
`_TRAITEMENTS` est la liste (vide aujourd'hui) des traitements appliqués au
texte entre la lecture et le découpage. C'est là que viendront se brancher le
nettoyage, la détection d'entités personnelles et la pseudonymisation — AVANT
le découpage, parce qu'une entité doit être détectée sur le document entier
pour que sa substitution reste cohérente d'un chunk à l'autre.
"""

from __future__ import annotations

import fnmatch
import re
import sys
from datetime import datetime
from pathlib import Path

EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}

# Phase 2 : liste de callables (texte, meta) -> (texte, meta). Vide en phase 1.
_TRAITEMENTS: list = []


# ─────────────────────────────────────────────────────────────────────────────
# Découpage — copié tel quel d'ingest_tuteur.py
# ─────────────────────────────────────────────────────────────────────────────
_FIN_PHRASE = re.compile(r'(?<=[.!?…])\s+(?=[A-ZÀ-Ý0-9«"“(])')


def decouper_phrases(paragraphe: str) -> list[str]:
    """Découpe un alinéa en phrases, sans jamais couper un mot en deux."""
    return [p.strip() for p in _FIN_PHRASE.split(paragraphe) if p.strip()]


def chunk_text(text: str, max_mots: int = 300, overlap: int = 30) -> list[str]:
    """Regroupe des PHRASES ENTIÈRES jusqu'à max_mots, avec recouvrement en
    phrases complètes. Le saut de paragraphe est une préférence de coupure, pas
    une coupure forcée — sinon un titre seul sur sa ligne formerait un chunk
    quasi vide au lieu de se rattacher au contenu qui suit.

    Exception : une phrase plus longue que max_mots (transcription sans
    ponctuation) retombe sur une fenêtre glissante par mots.
    """
    paragraphes = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
    sequence = []
    for para in paragraphes:
        phrases = decouper_phrases(para)
        for i, phrase in enumerate(phrases):
            sequence.append((phrase, i == len(phrases) - 1))

    chunks, courant, n_mots = [], [], 0
    for phrase, fin_para in sequence:
        mots_phrase = len(phrase.split())

        if mots_phrase > max_mots:
            if courant:
                chunks.append(" ".join(courant))
                courant, n_mots = [], 0
            mots = phrase.split()
            debut = 0
            while debut < len(mots):
                fin = min(debut + max_mots, len(mots))
                chunks.append(" ".join(mots[debut:fin]))
                if fin == len(mots):
                    break
                debut += max_mots - overlap
            continue

        if not courant or n_mots + mots_phrase <= max_mots:
            courant.append(phrase)
            n_mots += mots_phrase
        else:
            chunks.append(" ".join(courant))
            recouvrement, mots_recouvrement = [], 0
            for p in reversed(courant):
                mp = len(p.split())
                if mots_recouvrement + mp > overlap:
                    break
                recouvrement.insert(0, p)
                mots_recouvrement += mp
            courant, n_mots = recouvrement + [phrase], mots_recouvrement + mots_phrase

        if fin_para and n_mots >= max_mots / 2:
            chunks.append(" ".join(courant))
            courant, n_mots = [], 0

    if courant:
        chunks.append(" ".join(courant))

    return [c for c in chunks if len(c.split()) >= 5]


# ─────────────────────────────────────────────────────────────────────────────
# Lecture des fichiers
# ─────────────────────────────────────────────────────────────────────────────
def lire_unites(path: Path) -> list[tuple[str, str]]:
    """Renvoie [(texte, localisateur)]. Un PDF donne une unité par page, ce qui
    permet de citer « p.12 » plutôt que le fichier entier."""
    ext = path.suffix.lower()
    if ext in (".txt", ".md"):
        return [(path.read_text(encoding="utf-8", errors="ignore"), "")]
    if ext == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return [((p.extract_text() or ""), f"p.{i}")
                        for i, p in enumerate(pdf.pages, 1)]
        except ImportError:
            print(f"    [!] {path.name} ignoré (pip install pdfplumber).", file=sys.stderr)
    elif ext == ".docx":
        try:
            import docx
            txt = "\n\n".join(p.text for p in docx.Document(str(path)).paragraphs)
            return [(txt, "")]
        except ImportError:
            print(f"    [!] {path.name} ignoré (pip install python-docx).", file=sys.stderr)
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Indexation
# ─────────────────────────────────────────────────────────────────────────────
def indexer(source: str | Path, chroma_dir: str | Path, collection: str,
            config_ingestion: dict, verbeux: bool = True) -> dict:
    """Indexe un dossier (ou un fichier) et renvoie un bilan.

    Ré-indexation idempotente : la collection est recréée à chaque appel. Le
    régleur pourra donc relancer une ingestion avec d'autres paramètres de
    chunking sans se soucier de l'état précédent.
    """
    import chromadb
    import catalogue
    from sentence_transformers import SentenceTransformer
    from briques.communs import appliquer_precision, cache_modeles, MODELE_EMBED_DEFAUT

    src = Path(source)
    chunking = config_ingestion.get("chunking", {})
    max_mots = int(chunking.get("max_mots", 300))
    overlap = int(chunking.get("overlap", 30))
    exclure = config_ingestion.get("exclure", []) or []
    conf_embed = config_ingestion.get("embeddings", {})

    # Alias du catalogue → modèle réel, avec ses préfixes éventuels.
    fiche = catalogue.resoudre("embeddeurs", conf_embed.get("modele", MODELE_EMBED_DEFAUT))
    nom_modele = fiche["nom"]
    prefixe_doc = fiche.get("prefixe_document", "") or ""

    modele = SentenceTransformer(nom_modele, cache_folder=cache_modeles())
    modele = appliquer_precision(modele, conf_embed.get("precision"))
    if verbeux:
        alias = fiche.get("alias")
        precision = conf_embed.get("precision")
        details = "".join([
            f" (alias {alias})" if alias else "",
            f" — précision {precision}" if precision else "",
        ])
        print(f"Modèle d'embedding : {nom_modele}{details}")
        if fiche.get("hors_catalogue"):
            print("   ⚠️  modèle hors catalogue : ni ses préfixes ni sa dimension "
                  "ne sont connus (voir modeles.yaml).")
        if prefixe_doc:
            print(f"   Préfixe document appliqué : {prefixe_doc!r}")

    # Sélection des fichiers
    if src.is_file():
        tous, racine = [src], src.parent
    else:
        tous = [p for p in src.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS]
        racine = src

    def _exclu(p: Path) -> bool:
        rel, nom = str(p.relative_to(racine)).lower(), p.name.lower()
        return any(fnmatch.fnmatch(nom, m.lower()) or fnmatch.fnmatch(rel, m.lower())
                   for m in exclure)

    fichiers = [p for p in tous if not _exclu(p)]
    if verbeux:
        print(f"{len(fichiers)} fichier(s) à indexer "
              f"({len(tous) - len(fichiers)} exclu(s)).")

    # Lecture → traitements (phase 2) → découpage
    ids, textes, metas = [], [], []
    for path in fichiers:
        nom_source = str(path.relative_to(racine))
        for texte_unite, locator in lire_unites(path):
            meta_unite = {"source": nom_source, "locator": locator}
            for traitement in _TRAITEMENTS:
                texte_unite, meta_unite = traitement(texte_unite, meta_unite)
            for i, ch in enumerate(chunk_text(texte_unite, max_mots, overlap)):
                # Identifiant STABLE : même corpus + mêmes paramètres = mêmes ids.
                # C'est la clé de la ré-hydratation prévue en phase 2.
                ids.append(f"{nom_source}::{locator}::{i}")
                textes.append(ch)
                metas.append(dict(meta_unite))
        if verbeux:
            print(f"→ {nom_source}")

    if not textes:
        raise SystemExit("Aucun chunk produit. Vérifie le contenu de la source.")

    # Déduplication exacte (un même passage exporté en .pdf ET en .docx occuperait
    # deux places du top-k avec le même contenu).
    vus, gardes, doublons = set(), [], 0
    for cid, txt, meta in zip(ids, textes, metas):
        if txt in vus:
            doublons += 1
            continue
        vus.add(txt)
        gardes.append((cid, txt, meta))
    ids, textes, metas = ([g[0] for g in gardes],
                          [g[1] for g in gardes],
                          [g[2] for g in gardes])

    if verbeux:
        print(f"\nEncodage de {len(textes)} chunks…")
    # Le préfixe éventuel ne s'applique qu'à l'ENCODAGE : le texte stocké dans
    # l'index reste propre, sans quoi les extraits affichés à l'utilisateur
    # commenceraient tous par « passage: ».
    a_encoder = [prefixe_doc + t for t in textes] if prefixe_doc else textes
    vecteurs = modele.encode(a_encoder, show_progress_bar=verbeux).tolist()

    client = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        client.delete_collection(collection)
    except Exception:
        pass
    # L'IDENTITÉ de l'index, inscrite dans la collection elle-même.
    # Sans elle, le seul contrôle possible est la dimension des vecteurs — et
    # deux modèles différents partagent très souvent la même (768 est partout).
    # Interroger un index avec un autre embeddeur ne renvoie que du bruit, sans
    # la moindre erreur : c'est la faute la plus coûteuse du RAG parce qu'elle
    # est parfaitement silencieuse. Chroma n'accepte que str/int/float/bool en
    # métadonnées de collection, d'où les conversions.
    col = client.create_collection(collection, metadata={
        "embeddeur": str(nom_modele),
        "precision": str(conf_embed.get("precision") or "float32"),
        "dimension": int(len(vecteurs[0])) if vecteurs else 0,
        "max_mots": int(max_mots),
        "overlap": int(overlap),
        "indexe_le": datetime.now().isoformat(timespec="seconds"),
    })
    col.add(ids=ids, embeddings=vecteurs, documents=textes, metadatas=metas)

    bilan = {"fichiers": len(fichiers), "chunks": len(textes),
             "doublons_ignores": doublons, "collection": collection,
             "chroma_dir": str(chroma_dir), "modele": nom_modele,
             "max_mots": max_mots, "overlap": overlap}
    if verbeux:
        print(f"\n✅ '{collection}' : {len(textes)} chunks "
              f"({doublons} doublon(s) ignoré(s)).")
    return bilan
