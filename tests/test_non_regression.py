#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_non_regression.py — Le profil 'moyen' reproduit-il tuteur.py ?
=========================================================================
CE TEST DOIT ÊTRE LANCÉ SUR LE MAC (il charge Marsilia, CamemBERT et Chroma).

    conda activate ia_projects
    cd createur-rag
    python tests/test_non_regression.py --collection <ta_collection>

    # pour lister les collections disponibles :
    python tests/test_non_regression.py --lister

Pourquoi ce test est le plus important du lot
---------------------------------------------
Le créateur de RAG n'est pas du code neuf : c'est le code de tuteur-local,
démonté en briques. Un démontage réussi ne change RIEN au comportement. Si le
profil 'moyen' ne récupère pas exactement les mêmes passages que tuteur.py sur
les mêmes questions, c'est qu'une erreur s'est glissée dans l'extraction — et
il faut la trouver AVANT d'ajouter quoi que ce soit par-dessus.

Ce qui est comparé
------------------
· La RÉCUPÉRATION, à l'identique. Elle est déterministe : mêmes modèles, mêmes
  paramètres, même ordre d'opérations → mêmes identifiants de chunks, dans le
  même ordre. C'est le vrai critère.
· La GÉNÉRATION, à titre indicatif seulement. Même à température 0, un LLM
  local peut varier d'une exécution à l'autre. On mesure donc une similarité,
  pas une égalité — un écart ici n'est pas nécessairement une régression.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PROJETS = RACINE.parent
TUTEUR = PROJETS / "tuteur-local"

sys.path.insert(0, str(RACINE))


def lister_collections(chroma_dir: Path) -> list[str]:
    import chromadb
    client = chromadb.PersistentClient(path=str(chroma_dir))
    return [c.name for c in client.list_collections()]


def similarite_mots(a: str, b: str) -> float:
    ma, mb = set(a.lower().split()), set(b.lower().split())
    return len(ma & mb) / len(ma | mb) if (ma or mb) else 1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", help="Collection Chroma de tuteur-local.")
    ap.add_argument("--chroma-dir", default=str(TUTEUR / "chroma_db"))
    ap.add_argument("--questions", default=str(TUTEUR / "questions_tuteur.json"))
    ap.add_argument("--modele", default="qwen3:8b")
    ap.add_argument("--lister", action="store_true")
    ap.add_argument("--sans-generation", action="store_true",
                    help="Ne compare que la récupération (rapide, sans Ollama).")
    args = ap.parse_args()

    chroma_dir = Path(args.chroma_dir)

    if args.lister:
        print("Collections disponibles :")
        for nom in lister_collections(chroma_dir):
            print(f"  · {nom}")
        return

    if not args.collection:
        dispo = lister_collections(chroma_dir)
        sys.exit(f"Précise --collection parmi : {', '.join(dispo)}")

    # ── Référence : le tuteur d'origine ─────────────────────────────────────
    sys.path.insert(0, str(TUTEUR))
    from tuteur import Tuteur                                    # noqa: E402

    print(f"Chargement de la référence (tuteur.py, collection '{args.collection}')…")
    reference = Tuteur(args.collection, model_gen=args.modele, rerank=True)

    # ── Candidat : le profil 'moyen' du créateur de RAG ─────────────────────
    from createur import charger_profil, creer_rag              # noqa: E402

    config = charger_profil("moyen")
    # On aligne les consignes sur le prompt exact de tuteur.py, pour que la
    # comparaison des réponses porte sur le pipeline et non sur la formulation.
    for etape in config["pipeline"]:
        if "prompt_engineering" in etape:
            etape["prompt_engineering"] = {
                "consignes": (
                    "Tu es un tuteur pédagogue qui aide un élève à réviser sa formation. "
                    "Réponds à la question en t'appuyant UNIQUEMENT sur les extraits de cours "
                    "numérotés ci-dessous. Cite tes sources entre crochets, ex. [1], [2], après "
                    "chaque affirmation. Explique clairement, comme à un élève. Si la réponse ne "
                    "se trouve pas dans les extraits, dis-le franchement sans inventer."
                ),
                "gabarit": "{consignes}\n\nExtraits de cours :\n{contexte}\n\nQuestion de l'élève : {question}",
            }
        if "agent_llm" in etape:
            etape["agent_llm"]["modele"] = args.modele
    if args.sans_generation:
        config["pipeline"] = [e for e in config["pipeline"]
                              if not any(k in e for k in ("prompt_engineering",
                                                          "agent_llm",
                                                          "post_processing"))]

    print("Montage du profil 'moyen'…")
    rag = creer_rag(source=None, profil=config, collection=args.collection,
                    chroma_dir=chroma_dir, indexer_source=False, verbeux=True)

    # ── Vérifier que le traitement testé est BIEN appliqué ───────────────────
    # Sans ça, on peut faire varier `precision` dans le YAML, voir 7/7, et
    # conclure « float16 ne change rien » alors que float16 n'a jamais été
    # chargé. Une expérience dont on ne vérifie pas la condition ne prouve rien.
    from briques.communs import charger_embed, charger_reranker    # noqa: E402

    def _dtype(modele) -> str:
        module = getattr(modele, "model", modele)
        params = list(module.parameters())
        return str(params[0].dtype).replace("torch.", "") if params else "?"

    demande_embed = config.get("ingestion", {}).get("embeddings", {}).get("precision", "float32")
    demande_rerank = config.get("reranker", {}).get("precision", "float32")
    reel_embed = _dtype(charger_embed(rag.ressources))
    reel_rerank = _dtype(charger_reranker(rag.ressources))

    print("\nPrécision effectivement chargée (candidat) :")
    print(f"  embeddeur  demandé {demande_embed:<9} → réel {reel_embed}"
          f"{'   ⚠️  NON APPLIQUÉ' if demande_embed.replace('float', 'float') != reel_embed else '   ✅'}")
    print(f"  reranker   demandé {demande_rerank:<9} → réel {reel_rerank}"
          f"{'   ⚠️  NON APPLIQUÉ' if demande_rerank != reel_rerank else '   ✅'}")
    print(f"  référence (tuteur.py) : embeddeur {_dtype(reference.embed)}, "
          f"reranker {_dtype(reference.reranker) if reference.reranker else '—'}")

    if demande_embed != "float32":
        print("\n  ⚠️  L'embeddeur est testé en demi-précision, mais l'index a été")
        print("      construit en float32. Ce test ne valide donc que le côté REQUÊTE.")
        print("      Pour valider l'ensemble, il faut réindexer avec la même précision.")

    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))

    identiques, divergentes, similarites = 0, [], []
    print(f"\nComparaison sur {len(questions)} questions\n{'─' * 60}")

    for item in questions:
        q = item["question"]

        ids_ref = [p["id"] for p in reference.rechercher(q, pool=10, k=4)]
        resultat = rag.interroger(q)
        ids_new = [p["id"] for p in resultat["passages"]]

        ok = ids_ref == ids_new
        identiques += ok
        print(f"{'✅' if ok else '❌'} {item['id']:<28} "
              f"{len(set(ids_ref) & set(ids_new))}/4 passages communs"
              f"{'' if ok else '  ← ORDRE OU CONTENU DIFFÉRENT'}")
        if not ok:
            divergentes.append({"question": q, "reference": ids_ref, "obtenu": ids_new})
            print(f"     réf : {ids_ref}")
            print(f"     obt : {ids_new}")

        if not args.sans_generation:
            sim = similarite_mots(reference.repondre(q, reference.rechercher(q, pool=10, k=4)),
                                  resultat["reponse"])
            similarites.append(sim)
            print(f"     similarité des réponses : {sim:.0%}")

    # ── Verdict ─────────────────────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print(f"Récupération identique : {identiques}/{len(questions)} questions")
    if similarites:
        moyenne = sum(similarites) / len(similarites)
        print(f"Similarité moyenne des réponses : {moyenne:.0%} "
              f"(indicatif — un LLM local varie même à température 0)")

    if divergentes:
        rapport = RACINE / "tests" / "divergences_non_regression.json"
        rapport.write_text(json.dumps(divergentes, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        print(f"\n❌ NON-RÉGRESSION ÉCHOUÉE — détail écrit dans {rapport.name}")
        print("   L'extraction des briques a modifié le comportement. À corriger")
        print("   avant d'aller plus loin : tout le reste s'appuie dessus.")
        sys.exit(1)

    print("\n✅ NON-RÉGRESSION VALIDÉE — le démontage en briques n'a rien changé.")


if __name__ == "__main__":
    main()
