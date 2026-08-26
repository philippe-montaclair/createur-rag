#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mesures/mesurer.py — Fait tourner un jeu d'évaluation sur le créateur de RAG,
et produit un rapport daté.

    python mesures/mesurer.py --profil moyen
    python mesures/mesurer.py --profil minimal --sans-ragas   # réponses seules
    python mesures/mesurer.py --profil moyen --agent-eval ../agent_evaluation_rag

CE QUE CE SCRIPT MESURE, ET CE QU'IL NE MESURE PAS
--------------------------------------------------
Deux populations, deux grandeurs, jamais mélangées :

1. Les questions dont la réponse EST dans le corpus sont notées par RAGAS —
   fidélité aux passages récupérés, pertinence de la réponse, précision de la
   récupération.

2. Les questions hors-corpus ne peuvent pas être notées ainsi : la bonne
   réponse est de ne rien affirmer, et « fidélité aux passages » n'a pas de
   sens quand aucun passage ne contient la réponse. Elles sont mesurées sur le
   taux de refus.

Faire une moyenne des deux produirait un nombre qui MONTE quand le système se
met à inventer sur les hors-corpus. C'est la raison d'être de `jeu.separer()`.

CE QUI N'EST PAS AUTOMATISABLE ICI
----------------------------------
Le refus est détecté par deux indices structurels — absence de citation, et
présence d'un marqueur d'ignorance — dont aucun n'est une preuve. Le rapport
recopie donc les réponses hors-corpus intégralement : c'est un humain qui
tranche, et le chiffre produit est marqué « à confirmer » tant qu'il ne l'a
pas fait. Un taux de refus calculé par mots-clés et publié tel quel serait une
mesure de la liste de mots-clés.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from mesures.jeu import lire_jeu, composition, separer      # noqa: E402

# Marqueurs d'ignorance. Volontairement courts et peu nombreux : allonger cette
# liste améliore le chiffre sans améliorer le système, ce qui est exactement la
# façon dont une métrique cesse de mesurer quoi que ce soit.
MARQUEURS_REFUS = (
    "je ne sais pas",
    "ne figure pas",
    "n'est pas mentionn",
    "aucune information",
    "pas d'information",
    "le corpus ne",
    "les documents ne",
)


def parait_refuser(reponse: str, citations: List[str]) -> Dict[str, bool]:
    """Deux indices indépendants, rendus séparément — jamais fusionnés en un
    booléen unique, pour que le rapport montre lequel a joué."""
    minuscule = (reponse or "").lower()
    return {
        "marqueur": any(m in minuscule for m in MARQUEURS_REFUS),
        "sans_citation": not citations,
    }


def interroger_tout(rag, questions: List[Dict[str, Any]], verbeux: bool = True) -> List[Dict[str, Any]]:
    resultats = []
    for i, q in enumerate(questions, start=1):
        debut = time.perf_counter()
        r = rag.interroger(q["question"])
        duree = (time.perf_counter() - debut) * 1000
        contextes = [p["texte"] for p in r.get("passages", [])]
        resultats.append({
            **q,
            "reponse_systeme": r.get("reponse", ""),
            "citations": r.get("citations", []),
            "contextes": contextes,
            "sources_retrouvees": sorted({p.get("source", "") for p in r.get("passages", [])}),
            "duree_ms": round(duree, 1),
            "indices_refus": parait_refuser(r.get("reponse", ""), r.get("citations", [])),
        })
        if verbeux:
            print(f"  [{i:2d}/{len(questions)}] {q['id']} · {q['type']:16s} {duree:7.0f} ms")
    return resultats


def noter_ragas(resultats: List[Dict[str, Any]], chemin_agent: Path,
                modele_juge: str, hote_ollama: str, modele_embeddings: str) -> Dict[str, Any] | None:
    """Appelle RagEval sur les questions notables. Renvoie None si l'agent
    d'évaluation n'est pas joignable — auquel cas le rapport le dit, plutôt
    que d'omettre la section en silence."""
    if not (chemin_agent / "rag_evaluation_agent.py").exists():
        print(f"\n  ⚠️  Agent d'évaluation introuvable dans {chemin_agent}")
        print("      Dépôt : https://github.com/philippe-montaclair/rag-evaluation-agent")
        return None

    sys.path.insert(0, str(chemin_agent))
    try:
        from rag_evaluation_agent import RagEval          # type: ignore
    except Exception as e:
        print(f"\n  ⚠️  Import de l'agent d'évaluation impossible : {e}")
        return None

    jeu_ragas = [{
        "question": r["question"],
        "answer": r["reponse_systeme"],
        "contexts": r["contextes"],
        "ground_truth": r["reponse"],
    } for r in resultats]

    # pipeline= est exigé par le constructeur mais n'est pas appelé par
    # evaluate_ragas : les réponses sont déjà produites, on ne réinterroge pas.
    evaluateur = RagEval(
        pipeline=lambda q: {"answer": "", "contexts": []},
        ragas_provider="ollama",
        ragas_base_url=hote_ollama,
        ragas_model=modele_juge,
        ragas_embedding_model=modele_embeddings,
        judge_provider="ollama",
        judge_model=modele_juge,
    )
    print(f"\n  RAGAS sur {len(jeu_ragas)} questions notables (backend local, patience)…")
    return evaluateur.evaluate_ragas(jeu_ragas)


def ecrire_rapport(chemin: Path, profil: str, questions, notables_res, hors_res,
                   scores_ragas, meta: Dict[str, Any]) -> None:
    horodatage = datetime.now().strftime("%d/%m/%Y à %H:%M")
    durees = [r["duree_ms"] for r in notables_res + hors_res]

    lignes = [
        "# Mesures",
        "",
        f"Relevé le {horodatage}, profil `{profil}`, corpus `{meta['corpus']}`,",
        f"jeu `{meta['jeu']}`.",
        "",
        "Ce fichier est produit par `mesures/mesurer.py`. Il n'est pas écrit à la",
        "main : le rejouer sur la même machine avec le même corpus doit redonner",
        "les mêmes ordres de grandeur.",
        "",
        "## Conditions",
        "",
        "| | |",
        "|---|---|",
        f"| Profil | `{profil}` |",
        f"| Corpus | `{meta['corpus']}` — {meta['n_documents']} documents |",
        f"| Jeu d'évaluation | `{meta['jeu']}` — {len(questions)} questions |",
        f"| Modèle de génération | `{meta['modele_generation']}` |",
        f"| Modèle juge (RAGAS) | `{meta['modele_juge']}` |",
        f"| Machine | {meta['machine']} |",
        "",
        "Composition du jeu : "
        + ", ".join(f"{n} {t}" for t, n in sorted(composition(questions).items())) + ".",
        "",
        "## Latence",
        "",
        f"- médiane : **{statistics.median(durees):.0f} ms**",
        f"- moyenne : {statistics.mean(durees):.0f} ms",
        f"- écart-type : {statistics.pstdev(durees):.0f} ms" if len(durees) > 1 else "",
        f"- min / max : {min(durees):.0f} / {max(durees):.0f} ms",
        "",
        "L'écart-type est donné parce qu'une moyenne sans dispersion ne permet",
        "aucune comparaison : c'est la règle que `memoire.py` impose déjà aux",
        "expériences de réglage.",
        "",
        "## Qualité — questions dont la réponse est dans le corpus",
        "",
    ]

    if scores_ragas:
        lignes += ["| Métrique | Score |", "|---|---|"]
        for cle, valeur in sorted(scores_ragas.items()):
            if isinstance(valeur, (int, float)):
                lignes.append(f"| `{cle}` | {valeur:.3f} |")
        lignes += ["",
                   f"Calculé par RAGAS sur les {len(notables_res)} questions notables,",
                   "backend Ollama local — aucun appel sortant."]
    else:
        lignes += ["**Non calculé** : l'agent d'évaluation n'était pas joignable lors de",
                   "ce relevé. Les réponses brutes sont conservées dans `mesures/dernier_run.json`.",
                   "",
                   "Dépôt de l'agent : https://github.com/philippe-montaclair/rag-evaluation-agent"]

    lignes += ["", "## Refus — questions sans réponse dans le corpus", ""]
    avec_marqueur = sum(1 for r in hors_res if r["indices_refus"]["marqueur"])
    sans_citation = sum(1 for r in hors_res if r["indices_refus"]["sans_citation"])
    n = len(hors_res)
    lignes += [
        f"Sur {n} questions hors-corpus :",
        "",
        f"- **{avec_marqueur}/{n}** contiennent un marqueur d'ignorance explicite",
        f"- **{sans_citation}/{n}** ne produisent aucune citation",
        "",
        "> ⚠️ **Chiffres à confirmer à la main.** Ces deux indices sont structurels,",
        "> aucun n'est une preuve de refus : une réponse peut inventer tout en citant,",
        "> ou refuser sans employer l'un des marqueurs. Les réponses sont recopiées",
        "> ci-dessous pour qu'un humain tranche. Un taux de refus calculé par",
        "> mots-clés et publié tel quel mesurerait la liste de mots-clés.",
        "",
    ]
    for r in hors_res:
        lignes += [f"**{r['id']}** — {r['question']}", "",
                   "> " + (r["reponse_systeme"] or "(réponse vide)").replace("\n", "\n> "),
                   "",
                   f"citations : {r['citations'] or 'aucune'} · "
                   f"marqueur : {'oui' if r['indices_refus']['marqueur'] else 'non'}",
                   ""]

    lignes += ["## Ce que ces chiffres ne disent pas", "",
               "Le corpus d'exemple fait 14 chunks : `k: 4` en récupère 29 %. Les scores",
               "ci-dessus décrivent le comportement de la chaîne sur ce corpus-là, et ne",
               "se transposent pas à un corpus de production de plusieurs milliers de",
               "chunks, où la récupération devient le facteur limitant.",
               ""]

    chemin.write_text("\n".join(l for l in lignes if l is not None), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profil", default="moyen")
    ap.add_argument("--source", default="corpus_exemple")
    ap.add_argument("--collection", default="demo")
    ap.add_argument("--jeu", default="jeux_eval/exemple/questions.md")
    ap.add_argument("--agent-eval", default="../agent_evaluation_rag",
                    help="dossier du dépôt rag-evaluation-agent")
    ap.add_argument("--modele-juge", default="qwen3:8b")
    ap.add_argument("--modele-embeddings", default="nomic-embed-text",
                    help="modèle d'embeddings pour RAGAS (ollama pull nomic-embed-text)")
    ap.add_argument("--hote-ollama", default="http://localhost:11434")
    ap.add_argument("--sortie", default="MESURES.md")
    ap.add_argument("--sans-ragas", action="store_true",
                    help="produire les réponses et la latence sans noter la qualité")
    ap.add_argument("--pas-de-reindex", action="store_true")
    args = ap.parse_args()

    questions = lire_jeu(RACINE / args.jeu)
    notables, hors = separer(questions)
    print(f"\n{len(questions)} questions — {len(notables)} notables, {len(hors)} hors-corpus")

    from createur import creer_rag                             # noqa: E402
    print(f"Montage du profil '{args.profil}' sur '{args.source}'…")
    rag = creer_rag(None if args.pas_de_reindex else args.source,
                    profil=args.profil, collection=args.collection)

    print("\nQuestions notables :")
    notables_res = interroger_tout(rag, notables)
    print("\nQuestions hors-corpus :")
    hors_res = interroger_tout(rag, hors)

    scores = None
    if not args.sans_ragas:
        scores = noter_ragas(notables_res, (RACINE / args.agent_eval).resolve(),
                             args.modele_juge, args.hote_ollama, args.modele_embeddings)

    brut = RACINE / "mesures" / "dernier_run.json"
    brut.write_text(json.dumps(
        {"profil": args.profil, "horodatage": datetime.now().isoformat(),
         "notables": notables_res, "hors_corpus": hors_res, "ragas": scores},
        ensure_ascii=False, indent=2), encoding="utf-8")

    import platform
    # Le modèle de génération est celui du PROFIL, pas celui passé en option :
    # confondre les deux ferait publier un rapport qui attribue les réponses au
    # mauvais modèle — l'erreur exacte qu'un rapport de mesure doit exclure.
    modele_generation = "inconnu"
    try:
        from createur import charger_profil
        for etape in charger_profil(args.profil).get("pipeline", []):
            for nom, params in etape.items():
                if nom == "agent_llm":
                    modele_generation = (params or {}).get("modele", "inconnu")
    except Exception:
        pass

    meta = {
        "corpus": args.source,
        "jeu": args.jeu,
        "n_documents": len([p for p in (RACINE / args.source).glob("*.md")
                            if p.name != "LISEZ_MOI.md"]),
        "modele_generation": modele_generation,
        "modele_juge": args.modele_juge if not args.sans_ragas else "—",
        "machine": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
    }
    ecrire_rapport(RACINE / args.sortie, args.profil, questions,
                   notables_res, hors_res, scores, meta)

    print(f"\n✅ Rapport écrit dans {args.sortie}")
    print(f"   Réponses brutes dans mesures/dernier_run.json")
    print("   Relire les réponses hors-corpus AVANT de publier le taux de refus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
