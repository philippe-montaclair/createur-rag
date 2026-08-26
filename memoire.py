#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memoire.py — Agent N5 « memoire-experiences » du REGISTRE.
==========================================================
Retient ce que l'agent a ESSAYÉ et ce que ça a donné.

À ne pas confondre avec `feedback` (N5), qui retient ce que l'UTILISATEUR pense
des RÉPONSES. Ici, ce sont les réglages qu'on mémorise, pas les réponses.

Trois usages, dans l'ordre de leur valeur :
  1. Ne pas refaire  — avant de tester une configuration, vérifier qu'elle n'a
     pas déjà été mesurée sur ce corpus. Premier poste d'économie d'une boucle h24.
  2. Transférer      — « sur les 3 derniers corpus, pool=20 a battu pool=10 »
     devient un a priori pour le corpus suivant. C'est par là que l'agent
     « s'affine au fil du temps ».
  3. Rendre compte   — l'historique de POURQUOI la configuration actuelle est
     celle-là. Sans lui, six mois de réglages automatiques sont inauditables.

Support : JSONL append-only (décision ⬜6 du 31/07/2026)
-------------------------------------------------------
Cohérent avec `traces.jsonl`, lisible à l'œil, versionnable, sans dépendance.
Chroma a été écarté pour une raison de fond : « cette configuration a-t-elle
déjà été testée ? » est une question d'ÉGALITÉ, pas de similarité. Une réponse
« à peu près » y serait pire que pas de réponse du tout.

Ce que la mémoire ne fait PAS
-----------------------------
Elle ne décide rien. Elle répond « déjà vu, voici le résultat » ou « inédit ».
C'est le régleur qui choisit, et la mesure qui tranche. Une mémoire qui
déciderait rejouerait la faute que tout ce projet cherche à éviter : conclure
sans mesurer.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

# Un écart n'est un gain que s'il dépasse ce multiple de l'écart-type du bruit.
# 2 σ est le seuil retenu dans CONCEPTION_phase3_autonomie.md §3.1. Ce n'est pas
# une constante physique : c'est un arbitrage entre rater de vrais petits gains
# et courir après du hasard. Sur des centaines d'itérations sans surveillance,
# la seconde erreur coûte bien plus cher que la première.
FACTEUR_BRUIT = 2.0

CHAMPS_OBLIGATOIRES = ("corpus", "version_jeu_eval", "parametre", "score")


# ─────────────────────────────────────────────────────────────────────────────
# Signature d'une configuration
# ─────────────────────────────────────────────────────────────────────────────
def signature(config: Any) -> str:
    """Empreinte stable d'une configuration, pour répondre à « déjà testé ? ».

    Le tri des clés n'est pas cosmétique : deux profils identiques écrits dans un
    ordre différent doivent donner la MÊME empreinte, sans quoi la mémoire ne
    reconnaîtrait jamais rien et son premier usage — ne pas refaire — tomberait
    à l'eau sans que personne ne s'en aperçoive.
    """
    brut = json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(brut.encode("utf-8")).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────────────────────
# Bruit de mesure et verdict
# ─────────────────────────────────────────────────────────────────────────────
def ecart_type(valeurs: list[float]) -> float:
    """Dispersion de plusieurs exécutions de la MÊME configuration.

    `stdev` (échantillon, division par n−1) et non `pstdev` : ces 3 à 5
    exécutions sont un échantillon des exécutions possibles, pas la population
    entière. Sur de si petits effectifs, l'écart entre les deux formules n'est
    pas négligeable — et il va dans le sens prudent, celui qui déclare moins de
    faux gains.
    """
    valeurs = [float(v) for v in valeurs]
    if len(valeurs) < 2:
        return 0.0
    return statistics.stdev(valeurs)


def verdict(score: float, reference: float, bruit: float,
            facteur: float = FACTEUR_BRUIT) -> str:
    """gain | regression | neutre — au regard du bruit, jamais dans l'absolu.

    C'est ici que se joue la leçon de `tools/mesurer_ram.py` : un instrument qui
    donne deux réponses différentes sur la même entrée ne mesure rien. Comparer
    deux scores sans connaître leur dispersion, c'est lire du hasard.

    Cas `bruit == 0` : on n'a pas mesuré la dispersion, ou une seule exécution.
    On rend « indetermine » plutôt que « gain » — l'absence de bruit connu n'est
    pas la certitude, c'est l'ignorance.
    """
    if bruit <= 0:
        return "indetermine"
    ecart = float(score) - float(reference)
    if ecart > facteur * bruit:
        return "gain"
    if ecart < -facteur * bruit:
        return "regression"
    return "neutre"


# ─────────────────────────────────────────────────────────────────────────────
# La mémoire
# ─────────────────────────────────────────────────────────────────────────────
class Memoire:
    """Journal append-only des expériences de réglage."""

    def __init__(self, fichier: str | Path = "memoire.jsonl"):
        self.fichier = Path(fichier)
        self.fichier.parent.mkdir(parents=True, exist_ok=True)

    # ── Écriture ────────────────────────────────────────────────────────────
    def enregistrer(self, *, corpus: str, version_jeu_eval: str, parametre: str,
                    score: float, avant: Any = None, apres: Any = None,
                    reference: float | None = None, bruit: float = 0.0,
                    config: Any = None, **extra: Any) -> dict:
        """Ajoute une expérience. Refuse d'écrire si l'identification manque.

        `version_jeu_eval` est OBLIGATOIRE, et c'est le point le plus important
        de tout ce module. Si le jeu d'évaluation change, les scores antérieurs
        cessent d'être comparables. Une mémoire qui l'ignorerait accumulerait des
        certitudes fausses, et serait alors PIRE que pas de mémoire du tout :
        une erreur qu'on croit être un acquis ne se corrige jamais.
        """
        entree = {
            "horodatage": datetime.now().isoformat(timespec="seconds"),
            "corpus": corpus,
            "version_jeu_eval": version_jeu_eval,
            "parametre": parametre,
            "avant": avant,
            "apres": apres,
            "score": float(score),
            "reference": reference,
            "bruit": float(bruit),
            "signature": signature(config) if config is not None else None,
            **extra,
        }
        entree["verdict"] = (verdict(score, reference, bruit)
                             if reference is not None else "sans_reference")

        manquants = [c for c in CHAMPS_OBLIGATOIRES
                     if entree.get(c) in (None, "")]
        if manquants:
            raise ValueError(
                f"Mémoire : refus d'écrire, champ(s) manquant(s) : "
                f"{', '.join(manquants)}. Une expérience non identifiable n'est "
                "pas une expérience — elle ne pourra jamais être ni retrouvée, "
                "ni comparée, ni invalidée.")

        with self.fichier.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entree, ensure_ascii=False) + "\n")
        return entree

    # ── Lecture ─────────────────────────────────────────────────────────────
    def entrees(self) -> Iterator[dict]:
        """Parcourt le journal. Une ligne illisible est sautée, pas fatale :
        un fichier append-only peut se terminer par une ligne tronquée si le
        processus a été tué en pleine écriture. Perdre la dernière expérience
        est acceptable ; perdre l'accès aux mille précédentes ne l'est pas."""
        if not self.fichier.exists():
            return
        with self.fichier.open(encoding="utf-8") as f:
            for ligne in f:
                ligne = ligne.strip()
                if not ligne:
                    continue
                try:
                    yield json.loads(ligne)
                except json.JSONDecodeError:
                    continue

    def consulter(self, config: Any, corpus: str, version_jeu_eval: str) -> dict:
        """« A-t-on déjà mesuré cette configuration ? » — usage n°1.

        Trois réponses possibles, et la troisième est la raison d'être de cette
        méthode :

          inedit          jamais vu ici : à mesurer.
          deja_mesure     vu, sur le même corpus ET la même version d'éval.
          non_comparable  vu, mais sous une autre version du jeu d'éval. Le score
                          existe et il ne veut rien dire pour la décision d'aujourd'hui.

        Confondre les deux derniers, c'est fabriquer de fausses certitudes.
        """
        sig = signature(config)
        memes, autres_versions = [], []
        for e in self.entrees():
            if e.get("signature") != sig or e.get("corpus") != corpus:
                continue
            (memes if e.get("version_jeu_eval") == version_jeu_eval
             else autres_versions).append(e)

        if memes:
            return {"statut": "deja_mesure", "signature": sig, "entrees": memes}
        if autres_versions:
            return {"statut": "non_comparable", "signature": sig,
                    "entrees": autres_versions,
                    "motif": "mesuré sous une autre version du jeu d'éval — "
                             "le score existe, il n'est pas comparable"}
        return {"statut": "inedit", "signature": sig, "entrees": []}

    def a_priori(self, parametre: str, corpus: str | None = None) -> dict:
        """« Qu'a donné ce paramètre jusqu'ici ? » — usage n°2, le transfert.

        Compte les verdicts par valeur essayée. `corpus=None` agrège TOUS les
        corpus : c'est précisément ce qu'on veut pour transférer un acquis vers
        un corpus neuf.

        Réserve à garder en tête en lisant le résultat : un a priori n'est pas
        une conclusion. « pool=20 a gagné 3 fois sur 3 corpus » reste une
        indication de départ, pas une preuve valable sur le corpus suivant — les
        corpus ne se ressemblent pas. La mémoire oriente la recherche ; elle ne
        la remplace pas.
        """
        resume: dict[str, dict[str, int]] = {}
        for e in self.entrees():
            if e.get("parametre") != parametre:
                continue
            if corpus and e.get("corpus") != corpus:
                continue
            cle = json.dumps(e.get("apres"), ensure_ascii=False, default=str)
            case = resume.setdefault(cle, {"gain": 0, "neutre": 0,
                                           "regression": 0, "indetermine": 0,
                                           "sans_reference": 0})
            v = e.get("verdict", "indetermine")
            case[v] = case.get(v, 0) + 1
        return {"parametre": parametre, "corpus": corpus or "tous",
                "par_valeur": resume}

    def __repr__(self) -> str:
        return f"<Memoire {self.fichier} : {sum(1 for _ in self.entrees())} expériences>"
