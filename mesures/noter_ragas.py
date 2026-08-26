#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mesures/noter_ragas.py — Note avec RAGAS les réponses déjà produites, et
réinjecte les scores dans `mesures/dernier_run.json`.

    python mesures/noter_ragas.py --agent-eval ../agent_evaluation_rag

POURQUOI UN SCRIPT SÉPARÉ, ET PAS UNE OPTION DE mesurer.py
-----------------------------------------------------------
Les deux dépôts ne vivent pas dans le même environnement, et c'est très bien
ainsi. `createur-rag` a besoin de chromadb, sentence-transformers et torch ;
`rag-evaluation-agent` a besoin de ragas, datasets et d'un langchain-community
verrouillé sous 0.4 (au-dessus, `import ragas` casse). Les fusionner dans un
seul environnement, c'est se donner un conflit de dépendances à arbitrer à
chaque mise à jour de l'un ou de l'autre.

La mesure se fait donc en trois temps, chacun dans l'environnement qui lui va :

  1. produire les réponses      → env. de createur-rag
     python mesures/mesurer.py --sans-ragas
  2. noter les réponses         → env. de rag-evaluation-agent   (CE SCRIPT)
     python mesures/noter_ragas.py
  3. écrire le rapport          → n'importe quel python
     python mesures/mesurer.py --depuis-json --refus-valides … --pieges-reussis …

Le fichier `dernier_run.json` est le seul contrat entre les trois. Ce script
n'importe RIEN de createur-rag : il ne lit que du JSON.

CE QUI EST NOTÉ, ET CE QUI NE L'EST PAS
----------------------------------------
Seules les questions dont la réponse est dans le corpus. Les hors-corpus sont
écartées : RAGAS mesure la fidélité d'une réponse à des passages récupérés, et
sur une question sans réponse dans le corpus cette grandeur n'a pas de sens —
la bonne réponse est justement de ne rien affirmer. Leur taux de refus est
relevé ailleurs, à la main.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent-eval", default="../agent_evaluation_rag",
                    help="dossier du dépôt rag-evaluation-agent")
    ap.add_argument("--profil", default="moyen",
                    help="profil dont la campagne doit être notée")
    ap.add_argument("--json", default=None,
                    help="chemin explicite ; par défaut mesures/runs/<profil>.json")
    ap.add_argument("--modele-juge", default="qwen3:8b",
                    help="modèle Ollama qui note. Privilégier un modèle *instruct* "
                         "non « thinking » : RAGAS attend du JSON propre.")
    ap.add_argument("--modele-embeddings", default="nomic-embed-text")
    ap.add_argument("--hote-ollama", default="http://localhost:11434")
    ap.add_argument("--timeout", type=int, default=600,
                    help="secondes par métrique. Un backend local est lent.")
    args = ap.parse_args()

    chemin = RACINE / (args.json or f"mesures/runs/{args.profil}.json")
    if not chemin.exists():
        dispo = sorted(p.stem for p in (RACINE / "mesures" / "runs").glob("*.json"))
        print(f"⛔ {chemin} absent.")
        print(f"   Lancer d'abord : python mesures/mesurer.py --profil {args.profil} --sans-ragas")
        if dispo:
            print(f"   Campagnes déjà faites : {', '.join(dispo)}")
        return 1

    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    notables = donnees.get("notables", [])
    if not notables:
        print("⛔ Aucune question notable dans le fichier.")
        return 1

    agent = (RACINE / args.agent_eval).resolve()
    if not (agent / "rag_evaluation_agent.py").exists():
        print(f"⛔ Agent d'évaluation introuvable dans {agent}")
        print("   git clone https://github.com/philippe-montaclair/rag-evaluation-agent")
        return 1

    sys.path.insert(0, str(agent))
    try:
        import rag_evaluation_agent as agent_module       # type: ignore
        from rag_evaluation_agent import RagEval          # type: ignore
    except ImportError as e:
        print(f"⛔ Import impossible : {e}\n")
        print("   Ce script doit tourner dans l'environnement de l'agent d'évaluation,")
        print("   pas dans celui de createur-rag. Depuis le dossier de l'agent :")
        print("       source venv/bin/activate")
        print("   Si `import ragas` échoue sur ChatVertexAI, c'est langchain-community")
        print("   en 0.4.x : le dépôt le verrouille sous 0.4 pour cette raison exacte.")
        return 1

    # L'agent s'importe très bien SANS ragas : il se dégrade en silence et
    # evaluate_ragas renvoie alors {"error": "ragas non installé"}. Écrire ça
    # dans dernier_run.json produirait un rapport qui annonce une notation
    # RAGAS sans un seul score. On s'arrête ici plutôt que de le laisser passer.
    if not getattr(agent_module, "RAGAS_AVAILABLE", False):
        print("⛔ L'agent d'évaluation s'est importé, mais RAGAS n'est pas installé")
        print("   dans cet environnement — il se dégraderait en silence.\n")
        print("   Ce script doit tourner dans l'environnement de l'agent :")
        print(f"       cd {agent}")
        print("       source venv/bin/activate")
        print(f"       cd {RACINE}")
        print("       python mesures/noter_ragas.py")
        print("\n   Rien n'a été écrit.")
        return 1

    jeu = [{
        "question": r["question"],
        "answer": r["reponse_systeme"],
        "contexts": r["contextes"],
        "ground_truth": r["reponse"],
    } for r in notables]

    vides = [r["id"] for r in notables if not r["contextes"]]
    if vides:
        print(f"⚠️  {len(vides)} question(s) sans aucun passage récupéré : {', '.join(vides)}")
        print("   RAGAS notera 0 en fidélité — c'est exact, mais la cause est en amont,")
        print("   dans la récupération, pas dans la génération.\n")

    print(f"Notation de {len(jeu)} questions notables — backend Ollama local.")
    print(f"  juge        : {args.modele_juge}")
    print(f"  embeddings  : {args.modele_embeddings}")
    print(f"  hôte        : {args.hote_ollama}")
    print("\nC'est long : un modèle local note en série, comptez plusieurs")
    print("dizaines de minutes. Aucun appel ne sort de la machine.\n")

    evaluateur = RagEval(
        pipeline=lambda q: {"answer": "", "contexts": []},   # exigé, jamais appelé ici
        ragas_provider="ollama",
        ragas_base_url=args.hote_ollama,
        ragas_model=args.modele_juge,
        ragas_embedding_model=args.modele_embeddings,
        ragas_timeout=args.timeout,
        ragas_max_workers=1,          # Ollama traite en série : plus de workers = TimeoutError
        judge_provider="ollama",
        judge_model=args.modele_juge,
    )

    scores = evaluateur.evaluate_ragas(jeu)

    moyennes = (scores or {}).get("averages") or {}
    if (scores or {}).get("error") or not moyennes:
        raison = (scores or {}).get("error", "aucune moyenne calculée")
        print(f"\n⛔ Notation inexploitable : {raison}")
        print("   Rien n'a été écrit dans le fichier de mesures — un rapport qui")
        print("   annoncerait une notation sans score serait pire que pas de rapport.")
        return 1

    donnees["ragas"] = scores
    donnees["ragas_conditions"] = {
        "modele_juge": args.modele_juge,
        "modele_embeddings": args.modele_embeddings,
        "n_questions": len(jeu),
        "questions_sans_passage": vides,
    }
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n─── Scores ───")
    for cle, valeur in sorted(moyennes.items()):
        if isinstance(valeur, (int, float)):
            print(f"  {cle:24s} {valeur:.3f}")

    print(f"\n✅ Scores réinjectés dans {chemin.relative_to(RACINE)}")
    print("\nDernière étape, dans n'importe quel python :")
    print(f"  python mesures/mesurer.py --depuis-json --profil {args.profil} \\")
    print("      --refus-valides tous --pieges-reussis Q9,Q11,Q19,Q20")
    return 0


if __name__ == "__main__":
    sys.exit(main())
