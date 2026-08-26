#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_regleur.py — Logique de l'agent régleur, sans modèle ni base.
========================================================================
Même principe que test_briques.py : rien qui charge Chroma, sentence-transformers
ou Ollama. Ce fichier vérifie ce qui est décidable à froid, et qui est justement
là où l'agent pourrait se tromper SANS LEVER D'ERREUR :

  · le signe (une durée basse est un bon résultat, un score bas est un mauvais) ;
  · le choix du bruit (celui de la config la plus instable, pas de la référence) ;
  · la copie de configuration (une copie superficielle ferait comparer la
    configuration à elle-même) ;
  · la conversion de --valeur false (la chaîne "false" est VRAIE en Python).

Chacun de ces quatre points produirait un verdict crédible et faux. C'est la
définition même de ce qu'un test doit attraper.

    python tests/test_regleur.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "agents"))

from memoire import Memoire, ecart_type, verdict                    # noqa: E402
from regleur_latence import (                                       # noqa: E402
    _bool_ou_texte, _extraire, _moyenne_par_brique, chemins_disponibles,
    rapporter, regler,
)

REUSSIS, ECHOUES = [], []


def verifier(nom: str, condition: bool, detail: str = "") -> None:
    (REUSSIS if condition else ECHOUES).append(nom)
    print(f"  {'✅' if condition else '❌'} {nom}{f'  — {detail}' if detail else ''}")


def profil_type() -> dict:
    """Un profil réduit, mais de la même FORME que moyen.yaml : le paramètre
    visé est dans une brique du pipeline, et une section de haut niveau porte
    un nom identique à une brique (`reranker`). C'est ce recouvrement de noms
    qui rend l'écriture d'un chemin de réglage piégeuse."""
    return {
        "nom": "type",
        "reranker": {"modele": "fr-camembert-mmarco", "precision": "float16"},
        "ingestion": {"embeddings": {"modele": "fr-finance", "precision": "float32"}},
        "pipeline": [
            {"recherche_vectorielle": {"top_k": None}},
            {"reranker": {"garde": None}},
            {"constructeur_contexte": {"k": 4}},
            {"agent_llm": {"modele": "qwen3-8b", "decharger_reranker": True}},
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
print("\n1) Modifier un réglage sans toucher à l'original")

base = profil_type()
variante = regler(base, "agent_llm.decharger_reranker", False)

verifier("la variante porte la nouvelle valeur",
         _extraire(variante, "agent_llm.decharger_reranker") is False)

# LE test qui compte. `charger_profil` fait `dict(profil)` — une copie
# SUPERFICIELLE : la liste `pipeline` reste partagée. Sans copie profonde,
# la ligne ci-dessus aurait modifié `base` aussi, et l'agent aurait comparé la
# configuration à elle-même. Verdict « neutre », parfaitement crédible, faux.
verifier("l'original n'a PAS bougé (copie profonde, pas superficielle)",
         _extraire(base, "agent_llm.decharger_reranker") is True)

verifier("les listes ne sont pas partagées entre les deux",
         base["pipeline"] is not variante["pipeline"]
         and base["pipeline"][3] is not variante["pipeline"][3])

# Un réglage de haut niveau, pas dans le pipeline.
v2 = regler(base, "ingestion.embeddings.precision", "float16")
verifier("atteint aussi un réglage hors pipeline",
         _extraire(v2, "ingestion.embeddings.precision") == "float16"
         and _extraire(base, "ingestion.embeddings.precision") == "float32")

# Une faute de frappe doit ARRÊTER l'agent, pas créer une clé fantôme : sinon
# les deux configurations seraient identiques et l'agent mesurerait deux fois
# la même chose en annonçant un écart.
try:
    regler(base, "agent_llm.decharge_reranker", False)      # 'r' manquant
    verifier("une faute de frappe est refusée", False, "aucune erreur levée")
except KeyError as e:
    verifier("une faute de frappe est refusée", True)
    verifier("le message d'erreur liste les réglages disponibles",
             "decharger_reranker" in str(e))

try:
    regler(base, "decharger_reranker", False)               # sans préfixe
    verifier("un chemin sans préfixe est refusé", False)
except ValueError:
    verifier("un chemin sans préfixe est refusé", True)

verifier("chemins_disponibles voit les deux familles de réglages",
         "agent_llm.decharger_reranker" in chemins_disponibles(base)
         and "reranker.precision" in chemins_disponibles(base),
         f"{len(chemins_disponibles(base))} chemins")

# `reranker` est à la fois une brique du pipeline et une section de haut niveau.
# `reranker.precision` n'existe que dans la section : pas d'ambiguïté réelle.
verifier("nom partagé brique/section : résolu sans ambiguïté quand la clé "
         "n'existe que d'un côté",
         _extraire(regler(base, "reranker.precision", "float32"),
                   "reranker.precision") == "float32")

# En revanche, si la MÊME clé existe des deux côtés, on refuse plutôt que de
# choisir en silence.
piege = profil_type()
piege["pipeline"][1] = {"reranker": {"garde": None, "precision": "float32"}}
try:
    regler(piege, "reranker.precision", "float16")
    verifier("une clé présente des deux côtés est refusée", False)
except KeyError as e:
    verifier("une clé présente des deux côtés est refusée", "ambigu" in str(e).lower())


# ─────────────────────────────────────────────────────────────────────────────
print("\n2) Le signe — une durée basse est un BON résultat")

# `verdict()` est écrit pour des scores où plus grand = mieux. L'agent lui passe
# donc -durée. Ce test fige cette convention : si quelqu'un « simplifie » plus
# tard en passant la durée directement, tous les verdicts s'inversent en silence.
ref_ms, var_ms, bruit = 21800.0, 19100.0, 300.0
verifier("variante plus rapide → gain",
         verdict(score=-var_ms, reference=-ref_ms, bruit=bruit) == "gain")
verifier("variante plus lente → regression",
         verdict(score=-24000.0, reference=-ref_ms, bruit=bruit) == "regression")
verifier("écart plus petit que 2 bruits → neutre",
         verdict(score=-22000.0, reference=-ref_ms, bruit=bruit) == "neutre")

# Le contre-test : sans l'inversion, la conclusion serait exactement l'inverse.
verifier("sans l'inversion, le verdict serait faux (contre-test)",
         verdict(score=var_ms, reference=ref_ms, bruit=bruit) == "regression")

# Bruit inconnu : ignorance, pas certitude.
verifier("bruit nul → indetermine, jamais gain",
         verdict(score=-19000.0, reference=-ref_ms, bruit=0.0) == "indetermine")


# ─────────────────────────────────────────────────────────────────────────────
print("\n3) Le bruit retenu est celui de la configuration la plus instable")

# Cas réel du projet : `decharger_reranker: true` recharge CamemBERT à chaque
# question. Journal du 01/08 : 2843 · 3244 · 4732 · 3904 ms à froid, contre
# σ ≈ 1 ms à chaud. Le bruit de la référence ne dit rien du bruit de la variante.
stable = [21800.0, 21801.0, 21799.5, 21800.5, 21800.2, 21799.8]
instable = [19600.0, 20900.0, 19800.0, 21500.0, 21000.0, 19000.0]

bruit_stable, bruit_instable = ecart_type(stable), ecart_type(instable)
verifier("la config instable a un bruit bien plus grand", bruit_instable > 50 * bruit_stable,
         f"{bruit_stable:.2f} contre {bruit_instable:.2f} ms")

retenu = max(bruit_stable, bruit_instable)
moy_s = sum(stable) / len(stable)
moy_i = sum(instable) / len(instable)

verifier("avec le bruit le plus grand → neutre (prudent, honnête)",
         verdict(score=-moy_i, reference=-moy_s, bruit=retenu) == "neutre")
verifier("avec le bruit de la référence seule → 'gain' fabriqué (contre-test)",
         verdict(score=-moy_i, reference=-moy_s, bruit=bruit_stable) == "gain")

verifier("écart_type refuse de conclure sur une seule mesure",
         ecart_type([21800.0]) == 0.0)


# ─────────────────────────────────────────────────────────────────────────────
print("\n4) Conversion des valeurs en ligne de commande")

# "false" est une chaîne non vide : elle est VRAIE en Python. Sans conversion,
# `--valeur false` laisserait le déchargement actif et l'agent comparerait deux
# fois la même configuration en annonçant mesurer un changement.
verifier("--valeur false → False (et pas la chaîne, qui serait vraie)",
         _bool_ou_texte("false") is False and bool("false") is True)
verifier("--valeur true → True", _bool_ou_texte("TRUE") is True)
verifier("--valeur null → None", _bool_ou_texte("null") is None)
verifier("--valeur 4 → entier 4", _bool_ou_texte("4") == 4 and isinstance(_bool_ou_texte("4"), int))
verifier("--valeur float16 → texte inchangé", _bool_ou_texte("float16") == "float16")


# ─────────────────────────────────────────────────────────────────────────────
print("\n5) Répartition par brique et rapport")

reparts = [
    {"agent_llm": 18900.0, "reranker": 2840.0, "recherche_vectorielle": 97.0},
    {"agent_llm": 18800.0, "reranker": 2860.0, "recherche_vectorielle": 99.0},
]
moy = _moyenne_par_brique(reparts)
verifier("moyenne par brique correcte", moy["agent_llm"] == 18850.0)
verifier("briques classées de la plus lente à la plus rapide",
         list(moy) == ["agent_llm", "reranker", "recherche_vectorielle"])
verifier("aucune répartition → dict vide, pas d'exception", _moyenne_par_brique([]) == {})

faux_resultat = {
    "reference": {"moyenne": 21800.0, "bruit": 1.0, "repartition_moyenne": moy},
    "variante": {"moyenne": 19100.0, "bruit": 900.0, "repartition_moyenne": moy},
    "verdict": "neutre", "ecart_ms": -2700.0, "bruit": 900.0,
    "sorties_identiques": False, "avant": True, "apres": False,
}
texte = rapporter(faux_resultat, "agent_llm.decharger_reranker", "moyen")
verifier("un verdict neutre n'est pas présenté comme 'les deux se valent'",
         "ne permet pas de trancher" in texte)
verifier("des sorties différentes sont signalées en clair",
         "NE RENDENT PAS LA MÊME RÉPONSE" in texte)
verifier("aucune proposition de modification quand le verdict n'est pas un gain",
         "Rien à changer" in texte and "remplacer" not in texte)

# Bug d'interface trouvé en relecture, pas par les tests unitaires : chaque
# morceau était juste (l'écart de temps existe, l'alerte s'affiche) et l'ensemble
# recommandait quand même d'appliquer le réglage. Un gain mesuré entre deux
# systèmes qui ne répondent pas la même chose n'est pas un gain.
gain_invalide = dict(faux_resultat, verdict="gain", sorties_identiques=False)
texte_gi = rapporter(gain_invalide, "agent_llm.decharger_reranker", "moyen")
verifier("un gain mesuré sur des sorties différentes ne propose RIEN",
         "AUCUNE PROPOSITION" in texte_gi and "remplacer" not in texte_gi)

gagnant = dict(faux_resultat, verdict="gain", sorties_identiques=True)
texte_g = rapporter(gagnant, "agent_llm.decharger_reranker", "moyen")
verifier("un gain propose la ligne exacte à changer",
         "decharger_reranker: True" in texte_g and "decharger_reranker: False" in texte_g)
verifier("et rappelle qu'il n'a rien modifié",
         "je n'ai modifié aucun fichier" in texte_g)


# ─────────────────────────────────────────────────────────────────────────────
print("\n6) Mémoire — ce qui est écrit, et ce qui est refusé")

import tempfile                                                     # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    m = Memoire(Path(tmp) / "memoire.jsonl")
    e = m.enregistrer(
        corpus="corpus_demo", version_jeu_eval="latence-sans-jeu-v1",
        parametre="agent_llm.decharger_reranker", avant=True, apres=False,
        score=-19100.0, reference=-21800.0, bruit=900.0, config=variante,
        grandeur="duree_totale_ms", sens="plus_petit_est_mieux")
    verifier("l'entrée porte le sens de la grandeur",
             e["sens"] == "plus_petit_est_mieux",
             "sans ça, un score négatif serait illisible dans six mois")
    # 2700 ms d'écart contre un bruit de 900 : au-delà des 2 σ, donc un gain.
    # C'est memoire.verdict() qui tranche à l'écriture — l'agent n'inscrit pas
    # sa propre conclusion, il inscrit les chiffres et laisse la mémoire juger.
    verifier("le verdict est calculé à l'écriture, pas fourni par l'agent",
             e["verdict"] == "gain")

    vu = m.consulter(variante, "corpus_demo", "latence-sans-jeu-v1")
    verifier("la mémoire retrouve la configuration : ne pas refaire",
             vu["statut"] == "deja_mesure")
    verifier("la même config sous une autre version d'éval → non_comparable",
             m.consulter(variante, "corpus_demo", "v1")["statut"] == "non_comparable",
             "une mesure de latence ne se compare pas à un score de qualité")
    verifier("une config jamais vue → inedit",
             m.consulter(base, "corpus_demo", "latence-sans-jeu-v1")["statut"] == "inedit")

    try:
        m.enregistrer(corpus="corpus_demo", version_jeu_eval="",
                      parametre="x", score=-1.0)
        verifier("une expérience non identifiable est refusée", False)
    except ValueError:
        verifier("une expérience non identifiable est refusée", True)


# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'─' * 60}")
print(f"{len(REUSSIS)} réussis, {len(ECHOUES)} échoués")
if ECHOUES:
    for nom in ECHOUES:
        print(f"  ❌ {nom}")
    sys.exit(1)
print("Tout est vert.")
