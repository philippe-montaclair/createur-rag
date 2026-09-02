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
import os
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
                   scores_ragas, meta: Dict[str, Any],
                   refus_valides: set[str] | None = None,
                   pieges_reussis: set[str] | None = None) -> None:
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

    # L'agent d'évaluation renvoie {"scores": [par question], "averages": {…}}.
    # Lire scores_ragas à plat donnerait un tableau vide sans le moindre message.
    moyennes = (scores_ragas or {}).get("averages") or {}
    if moyennes:
        lignes += ["| Métrique | Score |", "|---|---|"]
        for cle, valeur in sorted(moyennes.items()):
            if isinstance(valeur, (int, float)):
                lignes.append(f"| `{cle}` | {valeur:.3f} |")
        lignes += ["",
                   f"Calculé par RAGAS sur les {len(notables_res)} questions notables,",
                   "backend Ollama local — aucun appel sortant.",
                   "",
                   "Les hors-corpus sont exclues de ce calcul : « fidélité aux passages",
                   "récupérés » n'a pas de sens quand la bonne réponse est de ne rien",
                   "affirmer. Leur mesure est la section suivante."]
    else:
        lignes += ["**Non calculé** : l'agent d'évaluation n'était pas joignable lors de",
                   "ce relevé. Les réponses brutes sont conservées dans `mesures/dernier_run.json`.",
                   "",
                   "Dépôt de l'agent : https://github.com/philippe-montaclair/rag-evaluation-agent"]

    lignes += ["", "## Refus — questions sans réponse dans le corpus", ""]
    avec_marqueur = sum(1 for r in hors_res if r["indices_refus"]["marqueur"])
    sans_citation = sum(1 for r in hors_res if r["indices_refus"]["sans_citation"])
    n = len(hors_res)
    lignes += [f"Sur {n} questions hors-corpus :", ""]

    if refus_valides is not None:
        valides = sum(1 for r in hors_res if r["id"] in refus_valides)
        lignes += [
            f"### Taux de refus : **{valides}/{n}** ({valides / n:.0%})",
            "",
            "**Relevé par lecture humaine des réponses**, question par question. C'est",
            "ce chiffre-là qui fait foi, et lui seul.",
            "",
            "Les deux indices automatiques sont donnés à titre de comparaison, et",
            "l'écart est le point intéressant :",
            "",
            f"- marqueur d'ignorance détecté : {avec_marqueur}/{n}",
            f"- aucune citation produite : {sans_citation}/{n}",
            "",
        ]
        if avec_marqueur != valides:
            lignes += [
                f"> **L'heuristique se trompe de {abs(valides - avec_marqueur)} cas sur {n}.**",
                "> Elle rate des refus parfaitement formulés — « la réponse ne se trouve pas",
                "> dans les extraits fournis » n'emploie aucun des marqueurs de la liste.",
                "> Publier le chiffre automatique aurait donné un taux faux, et allonger la",
                "> liste de marqueurs pour le corriger reviendrait à mesurer la liste.",
                "> C'est la raison pour laquelle ce taux est relevé à la main.",
                "",
            ]
        non_valides = [r["id"] for r in hors_res if r["id"] not in refus_valides]
        if non_valides:
            lignes += ["Questions où le refus n'a **pas** été jugé valable : "
                       + ", ".join(f"`{i}`" for i in non_valides) + ".", ""]
    else:
        lignes += [
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

    lignes += ["Les six réponses sont recopiées ci-dessous : un lecteur doit pouvoir",
               "refaire le jugement sans relancer la campagne.", ""]
    for r in hors_res:
        marque = ""
        if refus_valides is not None:
            marque = " ✅ refus valable" if r["id"] in refus_valides else " ❌ refus non valable"
        lignes += [f"**{r['id']}**{marque} — {r['question']}", "",
                   "> " + (r["reponse_systeme"] or "(réponse vide)").replace("\n", "\n> "),
                   "",
                   f"citations : {r['citations'] or 'aucune'} · "
                   f"marqueur : {'oui' if r['indices_refus']['marqueur'] else 'non'}",
                   ""]

    pieges = [r for r in notables_res if r["type"] == "piege"]
    if pieges:
        lignes += ["## Pièges — les questions écrites pour faire échouer la chaîne", ""]
        if pieges_reussis is not None:
            reussis = sum(1 for r in pieges if r["id"] in pieges_reussis)
            lignes += [f"### {reussis}/{len(pieges)} évités", "",
                       "Relevé à la main. Chaque piège a été écrit **avec l'erreur attendue**,",
                       "avant toute interrogation : c'est ce qui distingue un piège d'une",
                       "question difficile. Une erreur prédite qui se produit n'est pas une",
                       "surprise, c'est une mesure.", ""]
        else:
            lignes += ["Verdict non relevé. Relancer avec `--depuis-json --pieges-reussis …`",
                       "après lecture.", ""]
        for r in pieges:
            marque = ""
            if pieges_reussis is not None:
                marque = " ✅ évité" if r["id"] in pieges_reussis else " ❌ **l'erreur attendue s'est produite**"
            lignes += [f"**{r['id']}**{marque} — {r['question']}", ""]
            if r.get("erreur_attendue"):
                lignes += [f"*Erreur attendue :* {r['erreur_attendue']}", ""]
            lignes += ["> " + (r["reponse_systeme"] or "(vide)").replace("\n", "\n> "), ""]

    lignes += ["## Ce que ces chiffres ne disent pas", "",
               "Le corpus d'exemple fait 14 chunks : `k: 4` en récupère 29 %. Les scores",
               "ci-dessus décrivent le comportement de la chaîne sur ce corpus-là, et ne",
               "se transposent pas à un corpus de production de plusieurs milliers de",
               "chunks, où la récupération devient le facteur limitant.",
               ""]

    chemin.write_text("\n".join(ligne for ligne in lignes if ligne is not None), encoding="utf-8")


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
    ap.add_argument("--sortie", default=None,
                    help="par défaut MESURES_<profil>.md — un rapport par profil, "
                         "sinon chaque campagne écrase la précédente")
    ap.add_argument("--sans-ragas", action="store_true",
                    help="produire les réponses et la latence sans noter la qualité")
    ap.add_argument("--pas-de-reindex", action="store_true")
    ap.add_argument("--depuis-json", action="store_true",
                    help="réécrire le rapport depuis mesures/dernier_run.json, sans "
                         "réinterroger le système — pour intégrer un verdict humain")
    ap.add_argument("--pieges-reussis", default=None,
                    help="identifiants des pièges évités, relevés APRÈS lecture : "
                         "Q9,Q11,Q19,Q20. 'tous' les accepte toutes.")
    ap.add_argument("--refus-valides", default=None,
                    help="identifiants des hors-corpus dont le refus a été jugé valable "
                         "APRÈS lecture, séparés par des virgules : Q14,Q15,Q16. "
                         "'tous' les accepte toutes. Sans cette option, le rapport "
                         "affiche les indices automatiques et les marque à confirmer.")
    args = ap.parse_args()
    sortie = args.sortie or f"MESURES_{args.profil}.md"

    questions = lire_jeu(RACINE / args.jeu)
    notables, hors = separer(questions)
    print(f"\n{len(questions)} questions — {len(notables)} notables, {len(hors)} hors-corpus")

    refus_valides = None
    if args.refus_valides:
        refus_valides = ({q["id"] for q in hors} if args.refus_valides.strip().lower() == "tous"
                         else {i.strip() for i in args.refus_valides.split(",") if i.strip()})
        inconnus = refus_valides - {q["id"] for q in hors}
        if inconnus:
            print(f"\n⛔ Identifiants absents des hors-corpus : {', '.join(sorted(inconnus))}")
            return 1

    pieges_reussis = None
    if args.pieges_reussis:
        ids_pieges = {q["id"] for q in questions if q["type"] == "piege"}
        pieges_reussis = (ids_pieges if args.pieges_reussis.strip().lower() == "tous"
                          else {i.strip() for i in args.pieges_reussis.split(",") if i.strip()})
        inconnus = pieges_reussis - ids_pieges
        if inconnus:
            print(f"\n⛔ Identifiants qui ne sont pas des pièges : {', '.join(sorted(inconnus))}")
            return 1

    if args.depuis_json:
        brut = RACINE / "mesures" / "runs" / f"{args.profil}.json"
        if not brut.exists():
            dispo = sorted(p.stem for p in (RACINE / "mesures" / "runs").glob("*.json"))
            print(f"⛔ {brut} absent : aucune campagne pour le profil '{args.profil}'.")
            if dispo:
                print(f"   Campagnes disponibles : {', '.join(dispo)}")
            return 1
        d = json.loads(brut.read_text(encoding="utf-8"))
        import platform
        meta = {"corpus": args.source, "jeu": args.jeu,
                "n_documents": len(list((RACINE / args.source).glob("*.md"))),
                "modele_generation": d.get("modele_generation", "inconnu"),
                "modele_juge": "—" if not d.get("ragas") else args.modele_juge,
                "machine": f"{platform.system()} {platform.machine()}, "
                           f"Python {platform.python_version()}"}
        ecrire_rapport(RACINE / sortie, d.get("profil", args.profil), questions,
                       d["notables"], d["hors_corpus"], d.get("ragas"), meta,
                       refus_valides, pieges_reussis)
        print(f"✅ Rapport réécrit dans {sortie} depuis {brut.name} — rien n'a été réinterrogé.")
        return 0

    # Contrôle préalable, avant toute indexation. Sans lui, l'absence de chromadb
    # se révèle par une trace de pile au fond d'ingestion.py, une fois le jeu lu
    # et le profil monté. Le cas est banal : la notation RAGAS tourne dans le venv
    # de l'agent d'évaluation, et si l'on enchaîne sans en sortir, `python` reste
    # celui du venv — les deux environnements s'empilent, le premier du PATH gagne.
    manquants = []
    for module, paquet in (("chromadb", "chromadb"),
                           ("sentence_transformers", "sentence-transformers"),
                           ("yaml", "pyyaml")):
        try:
            __import__(module)
        except ImportError:
            manquants.append(paquet)
    if manquants:
        print(f"\n⛔ Modules absents de cet environnement : {', '.join(manquants)}")
        print(f"   python utilisé : {sys.executable}")
        if "VIRTUAL_ENV" in os.environ:
            print(f"   Un venv est actif : {os.environ['VIRTUAL_ENV']}")
            print("   S'il s'agit de celui de l'agent d'évaluation, en sortir : deactivate")
        print("   Sinon : pip install -r requirements.txt")
        print("\n   Rien n'a été indexé.")
        return 1

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

    # Un fichier par profil : sans cela, mesurer 'complet' effacerait la
    # campagne 'moyen', et la comparaison entre profils deviendrait impossible
    # sans tout relancer — dont trente minutes de notation par question.
    (RACINE / "mesures" / "runs").mkdir(parents=True, exist_ok=True)
    brut = RACINE / "mesures" / "runs" / f"{args.profil}.json"
    brut.write_text(json.dumps(
        {"profil": args.profil, "horodatage": datetime.now().isoformat(),
         "modele_generation": modele_generation,
         "notables": notables_res, "hors_corpus": hors_res, "ragas": scores},
        ensure_ascii=False, indent=2), encoding="utf-8")

    meta = {
        "corpus": args.source,
        "jeu": args.jeu,
        "n_documents": len(list((RACINE / args.source).glob("*.md"))),
        "modele_generation": modele_generation,
        "modele_juge": args.modele_juge if not args.sans_ragas else "—",
        "machine": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
    }
    ecrire_rapport(RACINE / sortie, args.profil, questions,
                   notables_res, hors_res, scores, meta, refus_valides, pieges_reussis)

    print(f"\n✅ Rapport écrit dans {sortie}")
    print(f"   Réponses brutes dans {brut.relative_to(RACINE)}")
    print("   Relire les réponses hors-corpus AVANT de publier le taux de refus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
