#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
createur.py — L'assembleur. Prend un document et un profil, rend un RAG.
========================================================================
C'est le point d'entrée unique du créateur de RAG.

    from createur import creer_rag
    rag = creer_rag("./mes_documents", profil="moyen", collection="mon_corpus")
    resultat = rag.interroger("Ma question ?")

Deux usages, une seule mécanique :
  · un humain, en ligne de commande (`python createur.py --profil moyen ...`) ;
  · un AGENT, par appel de fonction — c'est l'usage qui compte. L'agent régleur
    modifiera une clé du profil, rappellera `creer_rag`, relira les traces. Il
    ne doit jamais avoir à écrire de code, seulement du YAML.

C'est aussi pourquoi `interroger()` ne renvoie pas une chaîne de caractères
mais un dictionnaire complet : réponse, citations, passages retenus ET bilan
d'exécution. L'agent évaluateur a besoin des passages pour juger la pertinence
du contexte ; l'agent régleur a besoin du bilan pour savoir quoi toucher.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))          # imports en chemin absolu depuis createur-rag/

from contrat import Contexte, Ressources          # noqa: E402
from observabilite import Journal, resumer        # noqa: E402
from briques import CATALOGUE                     # noqa: E402

PROFILS = RACINE / "profils"


# ─────────────────────────────────────────────────────────────────────────────
# Profils
# ─────────────────────────────────────────────────────────────────────────────
def charger_profil(profil: str | Path | dict) -> dict:
    """Accepte un nom court ('moyen'), un chemin, ou un dictionnaire déjà prêt.

    Le dictionnaire direct n'est pas un confort : c'est ce qui permettra à
    l'agent régleur de faire varier un paramètre en mémoire, sans écrire de
    fichier temporaire à chaque itération.
    """
    if isinstance(profil, dict):
        return dict(profil)

    import yaml
    chemin = Path(profil)
    if not chemin.exists():
        chemin = PROFILS / f"{profil}.yaml"
    if not chemin.exists():
        dispo = ", ".join(sorted(p.stem for p in PROFILS.glob("*.yaml")))
        raise FileNotFoundError(f"Profil introuvable : {profil} (disponibles : {dispo})")
    return yaml.safe_load(chemin.read_text(encoding="utf-8"))


def _construire_briques(config: dict, ressources: Ressources) -> list:
    """Transforme la liste `pipeline` du YAML en objets Brique, dans l'ordre."""
    briques = []
    for element in config.get("pipeline", []):
        if isinstance(element, str):
            nom, params = element, {}
        else:
            nom, params = next(iter(element.items()))
            params = params or {}
        if nom not in CATALOGUE:
            dispo = ", ".join(sorted(CATALOGUE))
            raise KeyError(f"Brique inconnue dans le profil : {nom!r}. Disponibles : {dispo}")
        briques.append(CATALOGUE[nom](params=params, ressources=ressources))
    return briques


# ─────────────────────────────────────────────────────────────────────────────
# Le RAG assemblé
# ─────────────────────────────────────────────────────────────────────────────
class RAG:
    """Un pipeline monté, prêt à répondre."""

    def __init__(self, config: dict, ressources: Ressources, briques: list,
                 journal: Journal):
        self.config = config
        self.ressources = ressources
        self.briques = briques
        self.journal = journal
        self.nom_profil = config.get("nom", "sans-nom")

    def interroger(self, question: str, filtre: dict | None = None) -> dict:
        """Pose une question. `filtre` restreint la recherche par métadonnées.

        Priorité : le filtre de l'appel REMPLACE celui du profil, il ne s'y
        ajoute pas. Les combiner par un ET implicite serait plus riche, mais
        produirait un périmètre effectif que personne ne lit nulle part — et un
        périmètre qu'on ne peut pas lire est un périmètre qu'on ne contrôle pas.
        """
        ctx = Contexte(question=question,
                       filtre=filtre if filtre is not None else self.config.get("filtre"))
        for brique in self.briques:
            # Instantané seulement si la brique est repliable : avec top_k null,
            # `candidats` porte tout le corpus classé, et copier cette liste pour
            # chaque brique d'un profil qui n'a aucun repli serait payer une
            # garantie dont on n'a pas l'usage.
            avant = ctx.instantane() if brique.sur_erreur == "ignorer" else None
            try:
                ctx = self.journal.executer(brique, ctx)
            except Exception as e:
                if not self._replier(brique, ctx, e):
                    # La panne arrête le pipeline — mais elle laisse une ligne
                    # dans le journal avant de remonter. En h24, une exception
                    # sans trace est une nuit perdue à comprendre quoi.
                    self.journal.clore(ctx, self.nom_profil)
                    raise
                ctx.restaurer(avant or {})
            else:
                brique.echecs_consecutifs = 0
        bilan = self.journal.clore(ctx, self.nom_profil)
        return {
            "question": question,
            "filtre": ctx.filtre,
            "reponse": ctx.reponse,
            "citations": ctx.citations,
            "passages": [
                {"id": p.id, "source": p.source, "locator": p.locator,
                 "score": p.score, "texte": p.texte}
                for p in ctx.passages
            ],
            "bilan": bilan,
        }

    # ── Repli sur erreur ────────────────────────────────────────────────────
    # Le repli est ici, dans l'assembleur, et NON dans Journal.executer() alors
    # que celui-ci a déjà un try/except. Raison : quand `observabilite.actif` est
    # à false, executer() se réduit à `return brique.run(ctx)`, sans aucun try.
    # Y loger le repli le ferait disparaître en même temps que l'observabilité —
    # un couplage invisible, du genre qui se découvre à 3 h du matin.
    # Le journal observe et relève ; l'assembleur décide.
    @staticmethod
    def _replier(brique, ctx: Contexte, e: Exception) -> bool:
        """Décide si l'on continue malgré l'échec de `brique`. Consigne dans tous
        les cas — un repli silencieux ne vaut pas mieux que la panne."""
        brique.echecs_consecutifs += 1
        incident = {
            "brique": brique.nom,
            "niveau": brique.niveau,
            "erreur": f"{type(e).__name__}: {e}",
            "politique": brique.sur_erreur,
            "echecs_consecutifs": brique.echecs_consecutifs,
        }

        if brique.sur_erreur != "ignorer":
            incident["repli"] = False
            ctx.erreurs.append(incident)
            return False

        if brique.echecs_consecutifs > brique.max_echecs:
            incident["repli"] = False
            incident["motif"] = (
                f"{brique.echecs_consecutifs} échecs consécutifs "
                f"(max_echecs={brique.max_echecs}) : la panne est installée, "
                "le repli ne la couvre plus")
            ctx.erreurs.append(incident)
            return False

        incident["repli"] = True
        ctx.erreurs.append(incident)
        return True

    def __repr__(self) -> str:
        chaine = " → ".join(b.nom for b in self.briques)
        return f"<RAG '{self.nom_profil}' : {chaine}>"


# ─────────────────────────────────────────────────────────────────────────────
# Fabrique
# ─────────────────────────────────────────────────────────────────────────────
def creer_rag(source: str | Path | None = None, profil: str | Path | dict = "moyen",
              collection: str = "corpus_v1", chroma_dir: str | Path | None = None,
              indexer_source: bool = True, verbeux: bool = True,
              verifier_index: bool = True) -> RAG:
    """Construit un RAG complet.

    source          dossier ou fichier à indexer. None = utiliser un index existant.
    profil          'minimal' | 'moyen' | 'total', un chemin, ou un dict.
    indexer_source  False pour interroger un index déjà construit sans le refaire.
    verifier_index  contrôle que l'embeddeur correspond bien à l'index (recommandé).
    """
    config = charger_profil(profil)
    chroma_dir = Path(chroma_dir or config.get("index", {}).get("chroma_dir",
                                                                RACINE / "chroma_db"))

    # Le modèle d'embedding de la RECHERCHE doit être celui de l'INGESTION.
    # Une seule source de vérité pour éviter l'erreur classique : indexer avec
    # un modèle, interroger avec un autre — les vecteurs ne vivent alors pas
    # dans le même espace et la recherche renvoie n'importe quoi, sans erreur.
    config["embeddings"] = config.get("ingestion", {}).get("embeddings", {})

    if source and indexer_source:
        from ingestion import indexer
        indexer(source, chroma_dir, collection, config.get("ingestion", {}),
                verbeux=verbeux)

    ressources = Ressources({
        "chroma_dir": str(chroma_dir),
        "collection": collection,
        "embeddings": config.get("embeddings", {}),
        "reranker": config.get("reranker", {}),
        "backend": config.get("backend", {}),
    })

    obs = config.get("observabilite", {}) or {}
    fichier = obs.get("fichier")
    journal = Journal(
        actif=obs.get("actif", True),
        fichier=(Path(fichier) if fichier and Path(fichier).is_absolute()
                 else (RACINE / fichier) if fichier else None),
    )

    rag = RAG(config, ressources, _construire_briques(config, ressources), journal)

    # ── Garde-fou : l'index a-t-il été construit par CET embeddeur ? ─────────
    # Interroger un index avec un autre modèle est une faute silencieuse : si
    # les dimensions coïncident par hasard (768 est très répandu), la recherche
    # renvoie du bruit sans lever la moindre erreur. On refuse de démarrer.
    if verifier_index and any(b.nom == "recherche_vectorielle" for b in rag.briques):
        import catalogue
        from briques.communs import charger_collection, charger_embed, fiche_embeddeur
        etat = catalogue.verifier_compatibilite(
            charger_collection(ressources), charger_embed(ressources),
            fiche_embeddeur(ressources)["nom"], collection)
        if verbeux:
            if etat["verifie"] and etat.get("identite_verifiee"):
                print(f"Index compatible : construit par {etat['embeddeur_index']} "
                      f"(dimension {etat['index']}).")
            elif etat["verifie"]:
                print(f"Index compatible en dimension ({etat['index']}), mais son "
                      f"embeddeur n'est pas inscrit : index antérieur au 31/07/2026. "
                      f"Contrôle partiel — deux modèles de même dimension passeraient.")
            else:
                print("⚠️  Compatibilité index/embeddeur non vérifiable "
                      "(index vide ou dimension illisible).")

    if verbeux:
        print(f"\n{rag}")
    return rag


# ─────────────────────────────────────────────────────────────────────────────
# Ligne de commande
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Créateur de RAG — ingestion + interrogation.")
    ap.add_argument("--profil", default="moyen", help="minimal | moyen | total | chemin.yaml")
    ap.add_argument("--source", help="Dossier ou fichier à indexer.")
    ap.add_argument("--collection", default="corpus_v1")
    ap.add_argument("--chroma-dir", default=None)
    ap.add_argument("--pas-de-reindex", action="store_true",
                    help="Utiliser l'index existant sans le reconstruire.")
    ap.add_argument("--question", help="Poser une seule question et sortir.")
    ap.add_argument("--traces", action="store_true", help="Afficher le détail des temps.")
    ap.add_argument("--modeles", action="store_true",
                    help="Afficher le catalogue des modèles et sortir.")
    ap.add_argument("--recommander", metavar="CATEGORIE",
                    choices=["embeddeurs", "rerankers", "llm"],
                    help="Proposer des modèles selon des contraintes, puis sortir.")
    ap.add_argument("--langue", help="Filtre de --recommander : fr | multilingue | en")
    ap.add_argument("--domaine", help="Filtre de --recommander : generaliste | finance | ...")
    ap.add_argument("--ram-max", type=int, metavar="MO",
                    help="Filtre de --recommander : empreinte maximale en Mo.")
    ap.add_argument("--environnement", choices=["local", "vps"],
                    help="Filtre de --recommander : où le modèle doit tourner.")
    args = ap.parse_args()

    # ── Consultation du catalogue (aucun modèle chargé) ─────────────────────
    if args.modeles:
        import catalogue
        presents = catalogue.modeles_ollama_presents()
        for cat in catalogue.CATEGORIES:
            print(catalogue.tableau(cat, presents=presents))
        if not presents:
            print("\n(Ollama injoignable : la colonne de présence des LLM est vide. "
                  "Lance `ollama serve`.)")
        return

    if args.recommander:
        import catalogue
        candidats = catalogue.recommander(
            args.recommander, langue=args.langue, domaine=args.domaine,
            ram_max_mo=args.ram_max, environnement=args.environnement)
        if not candidats:
            print("Aucun modèle ne satisfait ces contraintes. Assouplis un filtre.")
            return
        print(f"\n{len(candidats)} candidat(s), du plus léger au plus lourd :\n")
        for c in candidats:
            print(f"  {c['alias']:<20} {c['nom']:<48} {c['poids_mo']:>6} Mo")
            if c.get("note"):
                print(f"  {'':<20} {' '.join(c['note'].split())}")
            print()
        print("Le catalogue propose — il ne choisit pas. Reporte l'alias retenu")
        print("dans le profil, puis MESURE avant de garder.\n")
        return

    try:
        rag = creer_rag(source=args.source, profil=args.profil,
                        collection=args.collection, chroma_dir=args.chroma_dir,
                        indexer_source=not args.pas_de_reindex)
    except Exception as e:
        print(f"ERREUR : {e}")
        return

    def _poser(question: str) -> None:
        res = rag.interroger(question)
        print(f"\n{res['reponse']}\n")
        if res["citations"]:
            print("Sources :")
            for c in res["citations"]:
                print(f"  {c}")
        if args.traces:
            print()
            print(resumer(res["bilan"]))
        print()

    if args.question:
        _poser(args.question)
        return

    print("Pose tes questions. 'quit' pour sortir.\n")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in {"quit", "exit", "q"}:
            break
        _poser(q)


if __name__ == "__main__":
    main()
