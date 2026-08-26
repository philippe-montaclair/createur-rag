#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
comparer_juges.py — Départage deux juges sur deux critères objectifs.

LE PRINCIPE : DEUX CRITÈRES QUI TIRENT EN SENS CONTRAIRE
---------------------------------------------------------
Aucun des deux critères ne vaut seul, parce que chacun se triche — et se triche
dans la direction opposée de l'autre.

  · RECOUVREMENT LEXICAL (bas = bon). Le moyen le plus simple de faire remonter
    un chunk en tête, c'est de recopier ses mots rares : « qu'est-ce que la phase
    de déblocage ? » sort premier sans effort. Rang parfait, question sans valeur,
    puisqu'aucun praticien ne connaît le vocabulaire d'un document qu'il n'a pas
    lu. C'est la triche du juge paresseux, qui paraphrase au lieu d'interroger.

  · RANG DU CHUNK D'ORIGINE (haut = bon). Le moyen le plus simple de faire tomber
    le recouvrement à zéro, c'est d'écrire une question vague. « Comment bien
    travailler ? » ne partage aucun mot — et ne désigne rien, donc ne retrouve
    rien.

Tricher sur l'un dégrade l'autre. Une question qui tient les deux bouts a fait le
vrai travail : désigner un contenu SANS le nommer, ce qui est exactement la
situation d'un utilisateur réel.

C'est pourquoi ce script n'agrège JAMAIS les deux en un score unique. La moyenne
effacerait précisément l'information qu'on cherche — un juge médiocre sur les deux
et un juge excellent sur les deux peuvent avoir la même moyenne qu'un tricheur.

CE QUE CES MESURES NE DISENT PAS
--------------------------------
Elles disent si une question est bien FORMÉE. Elles ne disent pas si elle est
PLAUSIBLE dans la bouche d'un praticien. Une question parfaitement calibrée sur
les deux axes peut porter sur un détail dont personne ne se soucie. Seule la
relecture du mainteneur tranche cela, et elle reste indispensable.

Deux effets connus, à garder en tête en lisant les chiffres :
  · le recouvrement est mécaniquement plus élevé sur les questions COURTES —
    trois mots pleins dont deux communs font 0,67 sans que ce soit de la
    paraphrase. La longueur est donc affichée à côté.
  · le rang souffre des chunks quasi jumeaux. Deux passages du corpus décrivent
    le même protocole du genou dans deux cours différents ; une question sur le
    genou a donc DEUX bonnes réponses, et le rang du chunk d'origine peut être 2
    sans que la question soit en cause. D'où la colonne `rang_voisin`.

USAGE
    python tools/comparer_juges.py                       # recouvrement seul
    python tools/comparer_juges.py --collection corpus_demo \
        --chroma-dir ../tuteur-local/chroma_db --profil profils/moyen.yaml
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
DOSSIER = RACINE / "jeux_eval" / "corpus_demo"

# Mots-outils écartés du recouvrement : leur présence commune ne prouve rien.
# Deux textes français quelconques partagent « dans », « pour », « avec ».
OUTILS = set("""le la les un une des de du au aux et ou en dans sur pour par avec sans
que qui quoi dont ou est sont il elle on nous vous ils elles ce cet cette ces se sa son
ses leur leurs ne pas plus me te mon ma je tu comme quel quelle quels quelles faut
est-il faut-il peut peuvent etre avoir fait faire tout tous toute toutes meme aussi
donc alors ainsi cela ceci ici lors quand
""".split())


def mots_pleins(t: str) -> set[str]:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return {w for w in re.findall(r"[a-z]+", t) if len(w) > 2 and w not in OUTILS}


def charger(chemin: Path) -> tuple[str, dict[str, str]]:
    d = json.loads(chemin.read_text(encoding="utf-8"))
    return d["juge"], {q["chunk_id"]: q["question"] for q in d["questions"] if q["question"]}


def rangs(questions: dict[str, str], args) -> dict[str, tuple[int | None, int | None]]:
    """(rang du chunk d'origine, rang du meilleur autre chunk du même document).

    Le second n'est pas un raffinement : sans lui, un rang de 2 est illisible.
    Il peut vouloir dire « la question est mauvaise » ou « un passage jumeau est
    passé devant », et ces deux cas appellent des corrections opposées.

    DEUX PRÉCAUTIONS SUR LE MONTAGE DU PIPELINE
    -------------------------------------------
    · La génération est retirée (`prompt_engineering`, `agent_llm`,
      `post_processing`). On mesure la RÉCUPÉRATION ; garder le LLM coûterait
      ~19 s par question — 13 minutes pour 40 questions — sans rien apporter.
      Même procédé que `test_non_regression.py --sans-generation`.

    · Seul `constructeur_contexte.k` est modifié, pour LIRE plus loin dans le
      classement. `fusion.pool` reste à sa valeur de production : le changer
      modifierait l'ensemble soumis au reranker, donc le classement lui-même —
      on ne mesurerait plus le pipeline réel mais un autre. D'où le refus si
      l'on demande à lire au-delà du panier.
    """
    from createur import charger_profil, creer_rag

    config = charger_profil(args.profil)
    config["pipeline"] = [e for e in config["pipeline"]
                          if not any(k in e for k in ("prompt_engineering",
                                                      "agent_llm",
                                                      "post_processing"))]
    pool = None
    for etape in config["pipeline"]:
        if "fusion" in etape:
            pool = (etape["fusion"] or {}).get("pool")
        if "constructeur_contexte" in etape:
            etape["constructeur_contexte"]["k"] = args.k

    if pool and args.k > pool:
        print(f"✗ --k {args.k} dépasse le panier du reranker (pool={pool}).")
        print("  Au-delà, les passages ne sont pas reclassés : le rang lu ne serait")
        print(f"  pas celui du pipeline. Relance avec --k {pool} au maximum.")
        sys.exit(1)

    rag = creer_rag(source=None, profil=config, collection=args.collection,
                    chroma_dir=args.chroma_dir, indexer_source=False, verbeux=True)

    out: dict[str, dict] = {}
    for cid, q in questions.items():
        passages = rag.interroger(q)["passages"]
        doc = cid.split("::")[0]
        fiche = {"rang": None, "voisin_rang": None, "voisin_id": None,
                 "voisin_texte": "", "tete_id": None, "tete_texte": ""}
        if passages:
            fiche["tete_id"] = passages[0].get("id")
            fiche["tete_texte"] = (passages[0].get("texte") or "").strip()
        for i, p in enumerate(passages, 1):
            pid = p.get("id") or ""
            if pid == cid and fiche["rang"] is None:
                fiche["rang"] = i
            elif pid.split("::")[0] == doc and fiche["voisin_rang"] is None:
                fiche["voisin_rang"] = i
                fiche["voisin_id"] = pid
                fiche["voisin_texte"] = (p.get("texte") or "").strip()
        out[cid] = fiche
    return out


def extrait(t: str, n: int = 260) -> str:
    t = " ".join(t.split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--juges", nargs="+",
                    default=[str(DOSSIER / "questions_claude.json"),
                             str(DOSSIER / "questions_qwen3.json")])
    ap.add_argument("--echantillon", default=str(DOSSIER / "echantillon.json"))
    ap.add_argument("--collection", default=None,
                    help="si fourni, mesure aussi le rang (nécessite l'embeddeur)")
    ap.add_argument("--chroma-dir", default=None)
    ap.add_argument("--profil", default=str(RACINE / "profils" / "moyen.yaml"))
    ap.add_argument("--k", type=int, default=10,
                    help="profondeur de lecture du classement (défaut 10 = le "
                         "panier du reranker dans le profil moyen)")
    args = ap.parse_args()

    ech = json.loads(Path(args.echantillon).read_text(encoding="utf-8"))
    textes = {c["id"]: c["texte"] for c in ech["chunks"]}
    ordre = [c["id"] for c in ech["chunks"]]

    juges = [charger(Path(p)) for p in args.juges]
    mesures: dict[str, dict] = {}

    for nom, questions in juges:
        rec, longueurs = {}, {}
        for cid, q in questions.items():
            if cid not in textes:
                continue          # question écrite sur un ancien tirage
            qm = mots_pleins(q)
            rec[cid] = len(qm & mots_pleins(textes[cid])) / max(len(qm), 1)
            longueurs[cid] = len(qm)
        mesures[nom] = {"q": questions, "rec": rec, "len": longueurs, "rang": {}}

    if args.collection:
        for nom, _ in juges:
            mesures[nom]["rang"] = rangs(
                {c: q for c, q in mesures[nom]["q"].items() if c in textes}, args)

    # ---- détail, question par question ----
    for i, cid in enumerate(ordre, 1):
        print("=" * 96)
        print(f"[{i:2}] {cid}")
        for nom, _ in juges:
            m = mesures[nom]
            if cid not in m["rec"]:
                print(f"   {nom:<8} (absent de ce tirage)")
                continue
            r = m["rang"].get(cid)
            col = ""
            if r:
                exact = f"rang {r['rang']}" if r["rang"] else f"absent du top-{args.k}"
                col = f"  {exact:<18}" + (f"voisin {r['voisin_rang']}"
                                          if r["voisin_rang"] else "")
            print(f"   {nom:<8} rec {m['rec'][cid]:.2f} ({m['len'][cid]:2} mots){col}")
            print(f"            {m['q'][cid]}")

    # ---- synthèse : deux colonnes, jamais un score unique ----
    print("\n" + "=" * 96)
    print(f"{'juge':<10}{'recouvrement':>16}{'mots/question':>16}"
          f"{'rang median':>14}{'hors top-k':>12}")
    for nom, _ in juges:
        m = mesures[nom]
        rec = list(m["rec"].values())
        lon = list(m["len"].values())
        rs = [v["rang"] for v in m["rang"].values() if v["rang"]] if m["rang"] else []
        rate = (sum(1 for v in m["rang"].values() if not v["rang"])
                if m["rang"] else None)
        med = f"{statistics.median(rs):.1f}" if rs else "—"
        print(f"{nom:<10}{statistics.mean(rec):>16.2f}{statistics.mean(lon):>16.1f}"
              f"{med:>14}{(str(rate) if rate is not None else '—'):>12}")

    # ---- les concurrents, à juger à la main ----------------------------------
    # Un chunk d'origine absent du top-k ne prouve PAS que la question est
    # mauvaise. Dans un document de 44 morceaux qui développe un thème sur
    # plusieurs passages voisins, le chunk mitoyen répond souvent tout aussi
    # bien — et le critère « rang du chunk d'origine » suppose à tort qu'il
    # n'existe qu'une bonne réponse.
    #
    # Le rang seul ne permet pas de trancher : il faut LIRE le concurrent.
    # C'est exactement l'étape de pooling, appliquée là où elle rapporte le
    # plus — sur les cas litigieux, et non sur les 167 chunks.
    #
    # Trois issues possibles pour chaque cas ci-dessous, et elles ne se
    # confondent pas :
    #   · le concurrent répond aussi  → il devient un chunk pertinent de plus,
    #     la question est bonne, c'est le jeu qui s'enrichit ;
    #   · le concurrent ne répond pas → la question est trop vague ou le
    #     moteur est en défaut, à départager en la relisant ;
    #   · aucun des deux ne répond    → la question est à jeter.
    if args.collection:
        litiges = [(nom, cid, m["rang"][cid]) for nom, _ in juges
                   for m in [mesures[nom]]
                   for cid in ordre
                   if cid in m["rang"] and not m["rang"][cid]["rang"]]
        if litiges:
            print("\n" + "=" * 96)
            print(f"CHUNKS CONCURRENTS À JUGER — {len(litiges)} cas où le chunk "
                  f"d'origine sort du top-{args.k}")
            for nom, cid, r in litiges:
                i = ordre.index(cid) + 1
                print("─" * 96)
                print(f"[{i:2}] {nom} — {mesures[nom]['q'][cid]}")
                print(f"     attendu : {cid}")
                if r["voisin_id"]:
                    print(f"     voisin (rang {r['voisin_rang']}, même document) : "
                          f"{r['voisin_id'].split('::', 1)[-1]}")
                    print(f"       « {extrait(r['voisin_texte'])} »")
                if r["tete_id"] and r["tete_id"] != r["voisin_id"]:
                    print(f"     tête de classement : {r['tete_id']}")
                    print(f"       « {extrait(r['tete_texte'])} »")
                print("     → ce passage répond-il à la question ? "
                      "oui = chunk pertinent de plus · non = question à revoir")

    if not args.collection:
        print("\nRecouvrement seul. Pour le rang — il faut l'embeddeur et la collection :")
        print("  python tools/comparer_juges.py --collection corpus_demo \\")
        print("      --chroma-dir ../tuteur-local/chroma_db")
    print("\nCes chiffres disent si une question est bien FORMÉE, pas si elle est")
    print("PLAUSIBLE. La relecture du mainteneur reste nécessaire, en priorité là où les")
    print("deux juges divergent : c'est là que sont les erreurs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
