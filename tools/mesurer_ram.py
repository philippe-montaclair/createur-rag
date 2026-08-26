#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/mesurer_ram.py — Ce que pèsent réellement les modèles.
=============================================================
À LANCER SUR LE MAC.

    conda activate ia_projects
    python tools/mesurer_ram.py

Note sur la version précédente de ce script (25/07/2026)
--------------------------------------------------------
La v1 mesurait le RSS du processus avant/après chaque chargement. Deux
exécutions successives ont donné des résultats contradictoires — le reranker
« pesait » +56 Mo puis −51 Mo, et la mémoire système libre AUGMENTAIT après un
chargement. La méthode était fausse, pour trois raisons cumulées :

  · les poids sont mappés en mémoire (mmap) et matérialisés paresseusement :
    le RSS ne monte qu'à mesure que les pages sont réellement touchées ;
  · PyTorch réutilise l'arène mémoire déjà réservée par le modèle précédent,
    donc le second chargement paraît gratuit ;
  · sur RAM unifiée, `available` reflète toute l'activité de macOS et bouge de
    plusieurs centaines de Mo d'une seconde à l'autre.

Un delta de RSS entre deux chargements ne mesure donc pas la taille d'un
modèle. Ce script mesure maintenant ce qui est DÉTERMINISTE : le nombre de
paramètres et leur type. Même entrée, même sortie, à chaque exécution.

Le RSS reste affiché, mais à titre indicatif et explicitement étiqueté comme
non fiable — pas comme base d'une décision.
"""

from __future__ import annotations

import resource
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))


def mo(octets: float) -> str:
    return f"{octets / (1024 ** 2):,.0f} Mo".replace(",", " ")


def pic_rss() -> int:
    """Pic de mémoire résidente depuis le lancement. Sur macOS, ru_maxrss est
    en OCTETS (sur Linux, en kilo-octets) — d'où la normalisation."""
    brut = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return brut if sys.platform == "darwin" else brut * 1024


def peser(modele, nom: str) -> dict:
    """Taille réelle d'un modèle : nombre de paramètres × taille du type.
    Déterministe, indépendant de l'allocateur et de l'état du système."""
    import torch

    module = getattr(modele, "model", modele)          # CrossEncoder encapsule
    if hasattr(module, "_modules") and not list(module.parameters()):
        module = modele
    params = list(module.parameters())
    n = sum(p.numel() for p in params)
    octets = sum(p.numel() * p.element_size() for p in params)
    dtypes = {str(p.dtype) for p in params}
    appareils = {str(p.device) for p in params}

    print(f"\n  {nom}")
    print(f"    paramètres     {n / 1e6:>8.1f} M")
    print(f"    type           {', '.join(sorted(dtypes))}")
    print(f"    appareil       {', '.join(sorted(appareils))}")
    print(f"    poids en RAM   {mo(octets)}   ← chiffre fiable")
    _ = torch
    return {"nom": nom, "params": n, "octets": octets}


def main() -> None:
    from contrat import Ressources
    from briques.communs import (MODELE_EMBED_DEFAUT, MODELE_RERANK_DEFAUT,
                                 charger_embed, charger_reranker)

    print("Empreinte des modèles — mesure par comptage de paramètres")
    print("═" * 72)

    res = Ressources({
        "embeddings": {"modele": MODELE_EMBED_DEFAUT},
        "reranker": {"modele": MODELE_RERANK_DEFAUT},
    })

    mesures = [
        peser(charger_embed(res), f"Embeddeur — {MODELE_EMBED_DEFAUT}"),
        peser(charger_reranker(res), f"Reranker  — {MODELE_RERANK_DEFAUT}"),
    ]

    total = sum(m["octets"] for m in mesures)
    print("\n" + "═" * 72)
    print(f"Total des deux modèles Python : {mo(total)}")
    print(f"Pic de mémoire du processus   : {mo(pic_rss())}   (indicatif, non fiable)")

    # Le LLM ne vit PAS dans ce processus : Ollama le charge de son côté.
    print("\nLe LLM n'apparaît pas ici — Ollama tourne dans son propre processus.")
    print("Pour le voir, pendant qu'une question est en cours :  ollama ps")

    print("\n" + "─" * 72)
    print("Lecture :")
    print(f"  · Python occupe ~{mo(total)} de modèles pendant la recherche.")
    print("  · qwen3:8b en Q4 demande ~5 Go côté Ollama, en plus.")
    print("  · Sur 16 Go partagés avec macOS, la question n'est pas « est-ce que")
    print("    ça tient » mais « quelle marge reste-t-il avant le swap ».")
    print("\n  Le seul verdict qui vaille se lit à l'usage : si une génération qui")
    print("  prend 40 s en prend soudain 200, la machine swappe. Le journal")
    print("  (traces.jsonl) le montrera sur la ligne 'agent_llm'.")


if __name__ == "__main__":
    main()
