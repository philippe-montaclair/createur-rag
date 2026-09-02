#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
regleur_latence.py — Premier agent autonome du système. Groupe D, version réduite.
==================================================================================

CE QU'IL FAIT, EN UNE PHRASE
----------------------------
Il change UN réglage, repose la même question plusieurs fois, et dit « c'est
mieux », « c'est pire », ou — le plus souvent, et c'est le plus important —
« je ne sais pas, l'écart est dans le bruit ».

POURQUOI LA LATENCE ET PAS LA QUALITÉ
-------------------------------------
Le régleur complet doit optimiser la QUALITÉ des réponses. Il ne le peut pas
encore : mesurer la qualité demande un jeu d'évaluation (des questions dont on
connaît les bonnes réponses), et ce jeu n'existe pas au 01/08/2026.

La latence, elle, se mesure sans rien d'autre qu'un chronomètre. C'est donc la
seule famille de réglages qu'un agent peut trancher AUJOURD'HUI. Et la structure
— mesurer, comparer au bruit, écrire en mémoire, proposer — est exactement celle
du régleur définitif. Le jour où le jeu existera, on remplacera le chronomètre
par un score de recall ; le reste ne bougera pas.

CE QU'IL NE FAIT PAS
--------------------
Il ne modifie AUCUN profil. Il propose la ligne à changer et s'arrête là
(règle 2 d'identite.md, et décision 4 du 31/07 : l'humain valide).

LES TROIS PIÈGES QUE CE CODE ÉVITE, ET QUI SONT LA MOITIÉ DU TRAVAIL
--------------------------------------------------------------------
1. LE SIGNE. `memoire.verdict()` est écrit pour des scores où PLUS GRAND est
   MIEUX (un recall, une note). Ici on mesure des millisecondes, où PLUS PETIT
   est MIEUX. Passer une durée directement à `verdict()` inverserait chaque
   conclusion, sans lever la moindre erreur. On passe donc `-durée`.

2. LE BRUIT N'EST PAS LE MÊME DES DEUX CÔTÉS. Le journal du 01/08 note que le
   rechargement du reranker varie de 66 % d'une fois sur l'autre (2843 · 3244 ·
   4732 · 3904 ms), alors qu'à chaud la variation est de 0,5 %. Or
   `decharger_reranker: true` FORCE un rechargement à chaque question : cette
   configuration est structurellement bien plus instable que l'autre. Mesurer le
   bruit une seule fois, sur la référence, sous-estimerait donc massivement
   l'incertitude. On mesure le bruit de CHAQUE configuration et on retient le
   plus grand des deux — le verdict prudent.

3. COMPARE-T-ON BIEN LA MÊME CHOSE ? Si la variante ne renvoie pas les mêmes
   passages ni la même réponse que la référence, on ne compare plus deux vitesses
   mais deux systèmes différents, et l'écart de temps ne veut plus rien dire.
   L'agent le vérifie et le signale. Pour `decharger_reranker` la réponse doit
   être identique (le déchargement ne touche qu'à la mémoire) : si elle diffère,
   c'est qu'autre chose a bougé et il faut le savoir AVANT de conclure.

USAGE
    python agents/regleur_latence.py --collection corpus_demo \
        --parametre agent_llm.decharger_reranker --valeur false

    python agents/regleur_latence.py --collection corpus_demo \
        --parametre agent_llm.decharger_reranker --valeur false --n 3   # essai court
    python agents/regleur_latence.py --a-blanc      # montre le plan, ne mesure rien
"""
from __future__ import annotations

import argparse
import copy
import gc
import statistics
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from memoire import Memoire, ecart_type, signature, verdict  # noqa: E402

# Pas un jeu d'évaluation, et c'est déclaré comme tel. `version_jeu_eval` est
# obligatoire dans memoire.py pour empêcher de comparer des scores de qualité
# mesurés sous des jeux différents. Une mesure de latence n'a pas de jeu — mais
# écrire "" serait refusé, et inventer "v1" mélangerait ces entrées avec les
# futures mesures de qualité. Cette étiquette les isole : une entrée de latence
# et une entrée de recall auront des versions différentes, donc `consulter()`
# les rendra `non_comparable` l'une par rapport à l'autre. C'est exactement ce
# qu'on veut.
VERSION_MESURE = "latence-sans-jeu-v1"

QUESTION_PAR_DEFAUT = "Quel est le sujet principal de ce document ?"


# ─────────────────────────────────────────────────────────────────────────────
# Modifier un réglage sans écrire de fichier
# ─────────────────────────────────────────────────────────────────────────────
def chemins_disponibles(config: dict) -> list[str]:
    """Tous les réglages atteignables, en notation pointée. Sert à écrire un
    message d'erreur utile plutôt qu'un KeyError nu — leçon du 25/07 sur les
    collections introuvables."""
    trouves = []
    for element in config.get("pipeline", []):
        if isinstance(element, dict):
            nom, params = next(iter(element.items()))
            for cle in (params or {}):
                trouves.append(f"{nom}.{cle}")
    for section in ("reranker", "backend", "index", "observabilite"):
        for cle in (config.get(section) or {}):
            trouves.append(f"{section}.{cle}")
    for cle in (config.get("ingestion", {}).get("embeddings") or {}):
        trouves.append(f"ingestion.embeddings.{cle}")
    return sorted(set(trouves))


def regler(config: dict, chemin: str, valeur) -> dict:
    """Rend une COPIE de `config` avec un seul réglage changé.

    Copie profonde, et non `dict(config)` : `charger_profil` fait une copie
    superficielle, si bien que la liste `pipeline` reste partagée entre l'original
    et la copie. Modifier la copie modifierait la référence — et l'agent
    comparerait la configuration à elle-même en croyant mesurer un écart. Ce
    genre de bug ne lève aucune erreur : il rend simplement un verdict « neutre »
    parfaitement crédible.

    La clé doit DÉJÀ EXISTER. On refuse de créer un réglage au passage : une
    faute de frappe dans `--parametre` produirait sinon une clé que personne ne
    lit, et l'agent mesurerait deux fois la même chose sans le dire.

    Un nom présent à deux endroits est refusé aussi, plutôt que tranché en
    silence — `reranker` est à la fois une brique du pipeline et une section de
    haut niveau.
    """
    neuve = copy.deepcopy(config)
    *prefixe, cle = chemin.split(".")
    if not prefixe:
        raise ValueError(f"Chemin de réglage attendu sous la forme 'brique.parametre', reçu : {chemin!r}")

    emplacements = []

    # 1) une brique du pipeline
    for element in neuve.get("pipeline", []):
        if isinstance(element, dict):
            nom, params = next(iter(element.items()))
            if nom == prefixe[0] and isinstance(params, dict) and cle in params:
                emplacements.append(params)

    # 2) une section de haut niveau ('reranker.precision', 'ingestion.embeddings.modele')
    noeud = neuve
    for part in prefixe:
        noeud = noeud.get(part) if isinstance(noeud, dict) else None
        if noeud is None:
            break
    if isinstance(noeud, dict) and cle in noeud:
        emplacements.append(noeud)

    if not emplacements:
        dispo = "\n  ".join(chemins_disponibles(config))
        raise KeyError(
            f"Réglage introuvable dans ce profil : {chemin!r}.\n"
            f"Réglages disponibles :\n  {dispo}")
    if len(emplacements) > 1:
        raise KeyError(
            f"Réglage ambigu : {chemin!r} existe à {len(emplacements)} endroits "
            f"du profil. Précise lequel plutôt que me laisser choisir.")

    emplacements[0][cle] = valeur
    return neuve


def _extraire(config: dict, chemin: str):
    """Valeur actuelle d'un réglage — c'est ce qui sera écrit en 'avant' dans la
    mémoire. Rend None si le chemin n'existe pas ; c'est `regler()` qui refuse
    et explique, pas cette fonction de lecture."""
    *prefixe, cle = chemin.split(".")
    for element in config.get("pipeline", []):
        if isinstance(element, dict):
            nom, params = next(iter(element.items()))
            if nom == prefixe[0] and isinstance(params, dict) and cle in params:
                return params[cle]
    noeud = config
    for part in prefixe:
        noeud = noeud.get(part) if isinstance(noeud, dict) else None
        if noeud is None:
            return None
    return noeud.get(cle) if isinstance(noeud, dict) else None


# ─────────────────────────────────────────────────────────────────────────────
# Mesurer
# ─────────────────────────────────────────────────────────────────────────────
def mesurer(rag, question: str, n: int, echauffement: int = 1) -> dict:
    """Pose `n + echauffement` fois la même question et rend les durées.

    LA PREMIÈRE MESURE EST ÉCARTÉE, PAS SUPPRIMÉE. Au premier appel, les modèles
    ne sont pas encore en mémoire : le journal du 31/07 chiffre l'écart à 2 843 ms
    contre 185 ms à chaud pour le reranker, soit un facteur 15. Garder cette
    mesure dans la moyenne, c'est mesurer le démarrage du programme et non le
    réglage. Elle est conservée à part : c'est elle qui permettra plus tard de
    chiffrer le coût de démarrage, une autre question, tout aussi réelle.

    Attention à ne pas se tromper sur ce que « à chaud » veut dire ici : avec
    `decharger_reranker: true`, le reranker est rechargé à CHAQUE question. Les
    mesures retenues restent donc « à froid » de son point de vue — et c'est
    précisément le coût qu'on veut chiffrer, pas un artefact.
    """
    durees, repartitions, empreintes = [], [], []
    rejetees = []

    for i in range(n + echauffement):
        r = rag.interroger(question)
        bilan = r["bilan"]
        if i < echauffement:
            rejetees.append(bilan["duree_totale_ms"])
            print(f"    échauffement {i + 1}      {bilan['duree_totale_ms']:>9.1f} ms  (écartée)")
            continue
        durees.append(bilan["duree_totale_ms"])
        repartitions.append(bilan["repartition_ms"])
        empreintes.append({
            "ids_passages": bilan["ids_passages"],
            "longueur_reponse": len(r["reponse"]),
        })
        print(f"    mesure {i - echauffement + 1:<2}          {bilan['duree_totale_ms']:>9.1f} ms")

    return {
        "durees": durees,
        "moyenne": round(statistics.fmean(durees), 1) if durees else 0.0,
        "bruit": round(ecart_type(durees), 2),
        "echauffement_rejete": rejetees,
        "repartition_moyenne": _moyenne_par_brique(repartitions),
        "empreinte": empreintes[0] if empreintes else {},
        "empreintes_stables": all(e == empreintes[0] for e in empreintes) if empreintes else True,
    }


def _moyenne_par_brique(repartitions: list[dict]) -> dict:
    """Où le temps est passé, en moyenne. C'est ce qui dira si l'écart vient bien
    du reranker ou d'ailleurs — un écart global sans coupable identifié est un
    écart qu'on n'a pas compris."""
    if not repartitions:
        return {}
    briques = {b for r in repartitions for b in r}
    return {b: round(statistics.fmean([r.get(b, 0.0) for r in repartitions]), 1)
            for b in sorted(briques, key=lambda x: -statistics.fmean(
                [r.get(x, 0.0) for r in repartitions]))}


# ─────────────────────────────────────────────────────────────────────────────
# L'expérience complète
# ─────────────────────────────────────────────────────────────────────────────
def experience(*, collection: str, chroma_dir: str | None, profil: str,
               parametre: str, valeur, question: str, n: int,
               memoire: Memoire, refaire: bool = False) -> dict:
    from createur import charger_profil, creer_rag

    base = charger_profil(profil)
    avant = _extraire(base, parametre)
    variante = regler(base, parametre, valeur)   # lève ici si le chemin est faux

    if avant == valeur:
        raise ValueError(
            f"{parametre} vaut déjà {valeur!r} dans le profil {profil!r}. "
            "Comparer une configuration à elle-même rendrait « neutre » à coup sûr, "
            "et ce « neutre » ne voudrait rien dire.")

    # ── Usage n°1 de la mémoire : ne pas refaire ────────────────────────────
    deja = memoire.consulter(variante, collection, VERSION_MESURE)
    if deja["statut"] == "deja_mesure" and not refaire:
        print(f"\nDéjà mesuré ({deja['signature']}) sur {collection}. "
              f"Verdict précédent : "
              f"{[e['verdict'] for e in deja['entrees']]}")
        print("Relancer avec --refaire pour remesurer malgré tout.")
        return {"statut": "deja_mesure", "entrees": deja["entrees"]}
    if deja["statut"] == "non_comparable":
        print(f"\n⚠️  Configuration déjà vue, mais sous une autre version de mesure "
              f"({deja['motif']}). On remesure.")

    resultats = {}
    for etiquette, config in (("reference", base), ("variante", variante)):
        montre = avant if etiquette == "reference" else valeur
        print(f"\n── {etiquette} : {parametre} = {montre!r} "
              f"— {n} mesure(s) + 1 échauffement")
        rag = creer_rag(source=None, profil=config, collection=collection,
                        chroma_dir=chroma_dir, indexer_source=False, verbeux=False)
        resultats[etiquette] = mesurer(rag, question, n=n)

        # Libérer AVANT de monter la configuration suivante, explicitement.
        # `Ressources` porte un cache par instance : chaque creer_rag() recharge
        # donc ses propres modèles. Sans ce déchargement, les deux jeux
        # coexisteraient en mémoire — sur 16 Go partagés, l'agent provoquerait
        # exactement la pression mémoire qu'il est censé mesurer, et fausserait
        # la seconde moitié de son expérience. Un `del rag` seul ne suffit pas :
        # rien ne garantit quand le ramasse-miettes passe.
        for objet in rag.ressources.charges():
            rag.ressources.decharger(objet)
        del rag
        gc.collect()

    ref, var = resultats["reference"], resultats["variante"]

    # ── Piège n°2 : le bruit le plus grand des deux ─────────────────────────
    bruit = max(ref["bruit"], var["bruit"])

    # ── Piège n°1 : le signe. Plus petit = mieux, donc on compare -durée. ────
    v = verdict(score=-var["moyenne"], reference=-ref["moyenne"], bruit=bruit)

    ecart = round(var["moyenne"] - ref["moyenne"], 1)

    # ── Piège n°3 : compare-t-on la même chose ? ────────────────────────────
    identique = ref["empreinte"] == var["empreinte"]

    entree = memoire.enregistrer(
        corpus=collection,
        version_jeu_eval=VERSION_MESURE,
        parametre=parametre,
        avant=avant,
        apres=valeur,
        score=-var["moyenne"],          # cohérent avec le calcul du verdict :
        reference=-ref["moyenne"],      # la mémoire ne doit jamais stocker un
        bruit=bruit,                    # score dont le sens dépend du lecteur
        config=variante,
        grandeur="duree_totale_ms",
        sens="plus_petit_est_mieux",
        moyenne_reference_ms=ref["moyenne"],
        moyenne_variante_ms=var["moyenne"],
        ecart_ms=ecart,
        n_mesures=n,
        question=question,
        profil=profil,
        sorties_identiques=identique,
        repartition_reference=ref["repartition_moyenne"],
        repartition_variante=var["repartition_moyenne"],
    )

    return {"statut": "mesure", "reference": ref, "variante": var,
            "verdict": v, "ecart_ms": ecart, "bruit": bruit,
            "sorties_identiques": identique, "avant": avant, "apres": valeur,
            "entree_memoire": entree}


# ─────────────────────────────────────────────────────────────────────────────
# Rapport
# ─────────────────────────────────────────────────────────────────────────────
def rapporter(r: dict, parametre: str, profil: str) -> str:
    ref, var = r["reference"], r["variante"]
    seuil = round(2 * r["bruit"], 2)
    lignes = [
        "",
        "═" * 72,
        f"VERDICT : {r['verdict'].upper()}",
        "═" * 72,
        f"  {parametre} = {r['avant']!r}   (référence)  {ref['moyenne']:>9.1f} ms   "
        f"± {ref['bruit']:.2f}",
        f"  {parametre} = {r['apres']!r}   (variante)   {var['moyenne']:>9.1f} ms   "
        f"± {var['bruit']:.2f}",
        "",
        f"  écart mesuré           {r['ecart_ms']:>+9.1f} ms",
        f"  seuil de crédibilité   {seuil:>9.2f} ms   (2 × le plus grand des deux bruits)",
    ]

    if r["verdict"] == "neutre":
        lignes += [
            "",
            "  L'écart est plus petit que le seuil : il n'est pas distinguable du",
            "  hasard de la machine. Ce n'est PAS « les deux se valent » — c'est",
            "  « cette mesure ne permet pas de trancher ». Pour trancher : plus de",
            "  mesures (--n 12), ou une machine plus calme.",
        ]
    elif r["verdict"] == "gain":
        lignes += ["", f"  La variante est plus RAPIDE de {abs(r['ecart_ms']):.1f} ms par question."]
    elif r["verdict"] == "regression":
        lignes += ["", f"  La variante est plus LENTE de {abs(r['ecart_ms']):.1f} ms par question."]
    else:
        lignes += ["", "  Bruit nul ou non mesuré : aucune conclusion possible."]

    if not r["sorties_identiques"]:
        lignes += [
            "",
            "  ⚠️  LES DEUX CONFIGURATIONS NE RENDENT PAS LA MÊME RÉPONSE.",
            "      Le verdict ci-dessus compare deux systèmes différents, pas deux",
            "      vitesses du même système. À comprendre AVANT d'en tenir compte.",
        ]

    lignes += ["", "  Où le temps est passé (moyenne, ms) :",
               f"  {'brique':<26} {'référence':>12} {'variante':>12} {'écart':>10}"]
    briques = list(ref["repartition_moyenne"]) + [
        b for b in var["repartition_moyenne"] if b not in ref["repartition_moyenne"]]
    for b in briques:
        a = ref["repartition_moyenne"].get(b, 0.0)
        c = var["repartition_moyenne"].get(b, 0.0)
        lignes.append(f"  {b:<26} {a:>12.1f} {c:>12.1f} {c - a:>+10.1f}")

    lignes += ["", "─" * 72]
    # Un gain de vitesse mesuré entre deux systèmes qui ne rendent pas la même
    # réponse n'est pas un gain : c'est une comparaison invalide. L'agent doit
    # donc RETIRER sa proposition, pas l'assortir d'un avertissement. Trouvé en
    # relecture d'enchaînement — chaque morceau était correct isolément
    # (l'écart est réel, l'alerte s'affiche), et l'ensemble recommandait
    # d'appliquer un réglage sur une mesure qu'il venait lui-même d'invalider.
    if r["verdict"] == "gain" and not r["sorties_identiques"]:
        lignes += [
            "  AUCUNE PROPOSITION. L'écart de temps est réel, mais il a été mesuré",
            "  entre deux systèmes qui ne répondent pas la même chose : il ne dit",
            "  rien du réglage. Comprendre d'abord pourquoi les sorties diffèrent.",
        ]
    elif r["verdict"] == "gain":
        lignes += [
            "  CE QUE JE PROPOSE — je n'ai modifié aucun fichier :",
            f"    dans profils/{profil}.yaml, remplacer",
            f"        {parametre.split('.')[-1]}: {r['avant']!r}",
            "    par",
            f"        {parametre.split('.')[-1]}: {r['apres']!r}",
            "",
            "  À vérifier avant d'appliquer : ce verdict porte sur la VITESSE seule.",
            "  Si le réglage touche à la mémoire (decharger_reranker), un gain de",
            "  vitesse peut se payer en pression mémoire — invisible ici.",
        ]
    else:
        lignes += ["  Rien à changer. Aucun fichier n'a été modifié."]
    return "\n".join(lignes)


# ─────────────────────────────────────────────────────────────────────────────
def _message(e: Exception) -> str:
    """Le texte d'une erreur, sans les guillemets que KeyError ajoute et sans les
    \\n littéraux qu'il produit. Une faute de frappe dans `--parametre` doit
    donner un message lisible, pas trente lignes de pile — c'est la correction
    déjà appliquée le 25/07 aux collections introuvables, et elle vaut d'autant
    plus ici : cet agent est destiné à tourner sans personne devant l'écran.

    On lit `e.args[0]` et non `str(e)` : sur un KeyError, `str()` rend la chaîne
    ÉCHAPPÉE — guillemets ajoutés et sauts de ligne rendus en « \\n » littéraux.
    Le message soigneusement mis en forme arriverait sur une seule ligne."""
    if isinstance(e, KeyError) and e.args:
        return str(e.args[0])
    return str(e)


def _bool_ou_texte(v: str):
    """--valeur false doit devenir False, pas la chaîne 'false' — qui serait
    vraie en Python et rendrait le réglage sans effet, en silence."""
    bas = v.strip().lower()
    if bas in ("true", "vrai", "oui"):
        return True
    if bas in ("false", "faux", "non"):
        return False
    if bas in ("null", "none"):
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--collection", default="corpus_demo")
    p.add_argument("--chroma-dir", default=None)
    p.add_argument("--profil", default="moyen")
    p.add_argument("--parametre", default="agent_llm.decharger_reranker")
    p.add_argument("--valeur", default="false")
    p.add_argument("--question", default=QUESTION_PAR_DEFAUT)
    p.add_argument("--n", type=int, default=6,
                   help="mesures retenues par configuration (défaut 6)")
    p.add_argument("--memoire", default=str(RACINE / "memoire.jsonl"))
    p.add_argument("--refaire", action="store_true",
                   help="remesurer même si la mémoire connaît déjà cette configuration")
    p.add_argument("--a-blanc", action="store_true",
                   help="affiche le plan d'expérience et s'arrête, sans rien mesurer")
    args = p.parse_args()

    valeur = _bool_ou_texte(args.valeur)

    if args.a_blanc:
        from createur import charger_profil
        try:
            base = charger_profil(args.profil)
            avant = _extraire(base, args.parametre)
            variante = regler(base, args.parametre, valeur)
        except (KeyError, ValueError, FileNotFoundError) as e:
            print(f"\n{_message(e)}")
            return 1
        total = 2 * (args.n + 1)
        print("Plan d'expérience")
        print(f"  profil        {args.profil}   collection {args.collection}")
        print(f"  paramètre     {args.parametre} : {avant!r} → {valeur!r}")
        print(f"  question      {args.question!r}")
        print(f"  mesures       {args.n} retenues + 1 échauffement, par configuration")
        # 22 s par question, mesuré le 31/07 sur ce profil ; les chargements de
        # modèles des deux montages s'ajoutent (~5 s chacun).
        print(f"  au total      {total} questions, soit ~{(total * 22 + 10) / 60:.0f} "
              f"à {(total * 28 + 10) / 60:.0f} minutes")
        print(f"  signature de la variante : {signature(variante)}")
        print("\nAucune mesure effectuée, aucun fichier écrit.")
        return 0

    memoire = Memoire(args.memoire)
    print(f"Régleur de latence — {datetime.now():%d/%m/%Y %H:%M}")
    print(f"Ne modifie aucun profil. Écrit uniquement dans {Path(args.memoire).name}.")

    try:
        r = experience(collection=args.collection, chroma_dir=args.chroma_dir,
                       profil=args.profil, parametre=args.parametre, valeur=valeur,
                       question=args.question, n=args.n, memoire=memoire,
                       refaire=args.refaire)
    except (KeyError, ValueError, FileNotFoundError) as e:
        print(f"\n{_message(e)}")
        return 1

    if r["statut"] == "deja_mesure":
        return 0
    print(rapporter(r, args.parametre, args.profil))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
