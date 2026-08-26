#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_briques.py — Tests de la logique pure, sans modèle ni base.
======================================================================
Ces tests ne chargent NI Chroma, NI sentence-transformers, NI Ollama. Ils
vérifient uniquement ce qui est décidable sans eux : le découpage, la fusion,
la validation, le routage, la résolution des citations, et le montage des trois
profils.

Pourquoi ça vaut la peine : ce sont les tests qu'on peut lancer en une seconde,
autant de fois qu'on veut, y compris quand le Mac est déjà occupé à faire
tourner un modèle. Le test qui a besoin des modèles (non-régression contre
tuteur.py) est séparé, dans test_non_regression.py.

    python tests/test_briques.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from contrat import Brique, Contexte, Passage, Ressources     # noqa: E402
from observabilite import Journal                             # noqa: E402
from ingestion import chunk_text, decouper_phrases            # noqa: E402
from briques.fusion import rrf                                # noqa: E402
from briques.validateur_chunks import ValidateurChunks, jaccard   # noqa: E402
from briques.routeur import Routeur                           # noqa: E402
from briques.post_processing import PostProcessing            # noqa: E402
from briques.constructeur_contexte import ConstructeurContexte    # noqa: E402
from briques.prompt_engineering import PromptEngineering      # noqa: E402

REUSSIS, ECHOUES = [], []


def verifier(nom: str, condition: bool, detail: str = "") -> None:
    (REUSSIS if condition else ECHOUES).append(nom)
    print(f"  {'✅' if condition else '❌'} {nom}{f'  — {detail}' if detail else ''}")


def passage(pid: str, texte: str, score=None) -> Passage:
    return Passage(id=pid, texte=texte, source="doc.pdf", locator="p.1", score=score)


# ─────────────────────────────────────────────────────────────────────────────
print("\n1) Découpage (ingestion)")

texte = (
    "Le système nerveux central comprend le cerveau et la moelle épinière. "
    "Il traite les informations sensorielles. Il commande les mouvements.\n\n"
    "Le système nerveux périphérique relie le centre aux organes. "
    "Il comprend les nerfs crâniens et les nerfs rachidiens."
)
chunks = chunk_text(texte, max_mots=20, overlap=5)
verifier("produit des chunks", len(chunks) > 0, f"{len(chunks)} chunks")
verifier("aucun chunk vide", all(c.strip() for c in chunks))
verifier("aucun mot coupé en deux",
         all(not c.endswith("-") for c in chunks))
verifier("chunks courts écartés (< 5 mots)",
         all(len(c.split()) >= 5 for c in chunks))

phrases = decouper_phrases("Première phrase. Deuxième phrase ! Troisième ?")
verifier("découpage en phrases", len(phrases) == 3, str(phrases))

# Phrase-fleuve sans ponctuation : ne doit pas produire un chunk illimité.
fleuve = " ".join(["mot"] * 100)
morceaux = chunk_text(fleuve, max_mots=20, overlap=5)
verifier("phrase-fleuve découpée en fenêtres",
         all(len(m.split()) <= 20 for m in morceaux), f"{len(morceaux)} morceaux")

# Le découpage doit être DÉTERMINISTE : même entrée, même sortie. C'est la
# condition pour que les identifiants de chunks soient stables d'une
# indexation à l'autre — donc pour la ré-hydratation prévue en phase 2.
verifier("découpage déterministe", chunk_text(texte, 20, 5) == chunks)


# ─────────────────────────────────────────────────────────────────────────────
print("\n2) Fusion RRF")

liste_a = ["c1", "c2", "c3", "c4"]
liste_b = ["c4", "c3", "c9", "c1"]
fusionne = rrf([liste_a, liste_b], k=60)

verifier("tous les ids présents", set(fusionne) == {"c1", "c2", "c3", "c4", "c9"})
verifier("un id trouvé par les deux moteurs passe devant un id trouvé par un seul",
         fusionne.index("c1") < fusionne.index("c9"),
         f"ordre : {fusionne}")
verifier("fusion d'une seule liste = la liste", rrf([liste_a]) == liste_a)
verifier("fusion vide ne casse pas", rrf([]) == [])


# ─────────────────────────────────────────────────────────────────────────────
print("\n3) Validateur de chunks")

verifier("jaccard identiques = 1.0", jaccard({"a", "b"}, {"a", "b"}) == 1.0)
verifier("jaccard disjoints = 0.0", jaccard({"a"}, {"b"}) == 0.0)
verifier("jaccard ensemble vide = 0.0", jaccard(set(), {"a"}) == 0.0)

ctx = Contexte(question="test")
ctx.candidats = [
    passage("p1", "le patient présente une lombalgie chronique depuis six mois environ"),
    passage("p2", "le patient présente une lombalgie chronique depuis six mois environ !"),
    passage("p3", "la posologie recommandée est de deux comprimés par jour au maximum"),
    passage("p4", "trop court"),
]
ctx = ValidateurChunks({"seuil_doublon": 0.85, "mots_min": 5,
                        "couverture_min": 3}).run(ctx)
gardes = [p.id for p in ctx.candidats]
verifier("quasi-doublon écarté", "p2" not in gardes, f"gardés : {gardes}")
verifier("chunk trop court écarté", "p4" not in gardes)
verifier("passages distincts conservés", {"p1", "p3"} <= set(gardes))
note = ctx.notes["validateur_chunks"]
verifier("alerte de couverture émise", bool(note["alerte"]), note["alerte"])
verifier("motifs de rejet tracés", len(note["jetes"]) == 2, str(note["jetes"]))


# ─────────────────────────────────────────────────────────────────────────────
print("\n4) Routeur")

r = Routeur({"regles_actives": True, "defaut": "hybride"})
c = r.run(Contexte(question="Que dit l'article L.123-4 du code du travail ?"))
verifier("référence d'article détectée", bool(c.notes["routeur"]["motifs"]),
         str(c.notes["routeur"]["raisons"]))
verifier("route reste hybride (on n'écarte jamais le vectoriel)",
         c.route == "hybride")

c = r.run(Contexte(question="lombalgie"))
verifier("requête courte signalée",
         "requête courte, type mot-clé" in c.notes["routeur"]["raisons"])

c = r.run(Contexte(question="Peux-tu m'expliquer comment fonctionne la digestion ?"))
verifier("question naturelle sans signal littéral",
         c.notes["routeur"]["raisons"] == [], str(c.notes["routeur"]["raisons"]))

verifier("le coffre reste fermé par défaut (phase 2)", c.ouvrir_coffre is False)

c = Routeur({"regles_actives": False, "defaut": "vectorielle"}).run(Contexte(question="x"))
verifier("règles désactivées → route par défaut", c.route == "vectorielle")


# ─────────────────────────────────────────────────────────────────────────────
print("\n5) Constructeur de contexte + prompt")

ctx = Contexte(question="Ma question ?")
ctx.candidats = [passage(f"p{i}", f"texte numéro {i} du corpus") for i in range(1, 8)]
ctx = ConstructeurContexte({"k": 3}).run(ctx)
verifier("sélection limitée à k", len(ctx.passages) == 3)
verifier("numérotation des extraits", "[1]" in ctx.bloc_contexte and "[3]" in ctx.bloc_contexte)
verifier("provenance présente", "doc.pdf" in ctx.bloc_contexte)
verifier("candidats non détruits", len(ctx.candidats) == 7)

ctx = PromptEngineering({}).run(ctx)
verifier("prompt contient la question", "Ma question ?" in ctx.prompt)
verifier("prompt contient le contexte", "texte numéro 1" in ctx.prompt)
verifier("consigne anti-invention présente", "sans inventer" in ctx.prompt)

vide = PromptEngineering({}).run(Contexte(question="q"))
verifier("aucun passage → aucun prompt", vide.prompt == "")


# ─────────────────────────────────────────────────────────────────────────────
print("\n6) Post-traitement et citations")

ctx = Contexte(question="q")
ctx.passages = [passage("p1", "a"), passage("p2", "b"), passage("p3", "c")]
ctx.reponse = "<think>je réfléchis</think>La réponse est oui [1], et aussi [2]. Voir [9]."
ctx = PostProcessing({}).run(ctx)
note = ctx.notes["post_processing"]

verifier("bloc de raisonnement retiré", "<think>" not in ctx.reponse)
verifier("citations valides relevées", note["citations_valides"] == [1, 2])
verifier("citation orpheline détectée", note["citations_orphelines"] == [9],
         "le modèle a cité une source qu'on ne lui a pas donnée")
verifier("passage jamais cité repéré", note["passages_ignores"] == [3])
verifier("citations résolues en sources", len(ctx.citations) == 2, str(ctx.citations))


# ─────────────────────────────────────────────────────────────────────────────
print("\n7) Observabilité")

class BriqueLente(Brique):
    nom, niveau = "brique_lente", "N9"
    def run(self, ctx):
        import time
        time.sleep(0.02)
        ctx.candidats = [passage("x1", "un texte")]
        ctx.noter(self.nom, fait=True)
        return ctx

journal = Journal(actif=True, fichier=None)
ctx = journal.executer(BriqueLente(), Contexte(question="q"))
bilan = journal.clore(ctx, profil="test")

verifier("une trace par brique", len(ctx.traces) == 1)
verifier("durée mesurée", ctx.traces[0]["duree_ms"] >= 20,
         f"{ctx.traces[0]['duree_ms']} ms")
verifier("état avant/après capturé",
         ctx.traces[0]["avant"]["n_candidats"] == 0
         and ctx.traces[0]["apres"]["n_candidats"] == 1)
verifier("note de la brique remontée", ctx.traces[0]["notes"] == {"fait": True})
verifier("goulot identifié", bilan["goulot"] == "brique_lente")
verifier("bilan sérialisable en JSON",
         __import__("json").dumps(bilan, ensure_ascii=False) is not None)

inactif = Journal(actif=False)
ctx2 = inactif.executer(BriqueLente(), Contexte(question="q"))
verifier("journal inactif ne trace rien", ctx2.traces == [])


# ─────────────────────────────────────────────────────────────────────────────
print("\n8) Ressources (chargement paresseux, déchargement)")

res = Ressources({})
appels = {"n": 0}
def _fabrique():
    appels["n"] += 1
    return {"gros": "objet"}

res.obtenir("truc", _fabrique)
res.obtenir("truc", _fabrique)
verifier("objet construit une seule fois", appels["n"] == 1)
verifier("objet listé comme chargé", res.charges() == ["truc"])
verifier("déchargement effectif", res.decharger("truc") is True)
verifier("plus rien en mémoire", res.charges() == [])
verifier("décharger l'inexistant ne casse pas", res.decharger("truc") is False)


# ─────────────────────────────────────────────────────────────────────────────
print("\n9) Montage des trois profils")

from createur import charger_profil, _construire_briques      # noqa: E402

attendus = {
    "minimal": ["recherche_vectorielle", "constructeur_contexte",
                "prompt_engineering", "agent_llm", "post_processing"],
    "moyen": ["recherche_vectorielle", "recherche_bm25", "fusion", "reranker",
              "constructeur_contexte", "prompt_engineering", "agent_llm",
              "post_processing"],
    "complet": ["routeur", "recherche_vectorielle", "recherche_bm25", "fusion",
              "reranker", "validateur_chunks", "constructeur_contexte",
              "prompt_engineering", "agent_llm", "post_processing"],
}

for nom, chaine in attendus.items():
    config = charger_profil(nom)
    briques = _construire_briques(config, Ressources({}))
    verifier(f"profil '{nom}' se monte", [b.nom for b in briques] == chaine,
             " → ".join(b.nom for b in briques))
    # Le modèle d'embedding de l'ingestion doit exister : c'est lui qui sera
    # réutilisé côté recherche.
    verifier(f"profil '{nom}' déclare son embeddeur",
             bool(config.get("ingestion", {}).get("embeddings", {}).get("modele")))

config_moyen = charger_profil("moyen")
verifier("profil 'moyen' fidèle à tuteur.py : pool=10",
         config_moyen["pipeline"][2]["fusion"]["pool"] == 10)
verifier("profil 'moyen' fidèle à tuteur.py : k=4",
         config_moyen["pipeline"][4]["constructeur_contexte"]["k"] == 4)
verifier("profil 'moyen' fidèle à tuteur.py : température 0",
         config_moyen["pipeline"][6]["agent_llm"]["temperature"] == 0.0)

try:
    _construire_briques({"pipeline": [{"brique_qui_nexiste_pas": {}}]}, Ressources({}))
    verifier("brique inconnue rejetée", False)
except KeyError:
    verifier("brique inconnue rejetée", True)


# ─────────────────────────────────────────────────────────────────────────────
print("\n10) Catalogue de modèles")

import catalogue                                                # noqa: E402

verifier("alias résolu", catalogue.resoudre("embeddeurs", "fr-finance")["nom"]
         == "sujet-ai/Marsilia-Embeddings-FR-Base")
verifier("nom complet résolu vers son alias",
         catalogue.resoudre("embeddeurs", "sujet-ai/Marsilia-Embeddings-FR-Base")["alias"]
         == "fr-finance")
verifier("modèle hors catalogue accepté mais signalé",
         catalogue.resoudre("embeddeurs", "un/modele-inconnu").get("hors_catalogue") is True)
verifier("alias LLM résolu vers le tag Ollama",
         catalogue.resoudre("llm", "qwen3-8b")["nom"] == "qwen3:8b")
verifier("tag Ollama direct accepté",
         catalogue.resoudre("llm", "qwen3:8b")["nom"] == "qwen3:8b")

try:
    catalogue.resoudre("inexistant", "x")
    verifier("catégorie inconnue rejetée", False)
except ValueError:
    verifier("catégorie inconnue rejetée", True)

# Le piège des préfixes : la famille e5 en exige, Marsilia non. Les oublier
# dégrade la qualité SANS erreur — d'où leur présence au catalogue.
verifier("préfixes e5 déclarés",
         catalogue.resoudre("embeddeurs", "multi-e5-base")["prefixe_requete"] == "query: ")
verifier("pas de préfixe pour Marsilia",
         "prefixe_requete" not in catalogue.resoudre("embeddeurs", "fr-finance"))

leger = catalogue.recommander("embeddeurs", ram_max_mo=600)
verifier("recommandation filtre par RAM",
         all(c["poids_mo"] <= 600 for c in leger) and len(leger) > 0,
         ", ".join(c["alias"] for c in leger))
verifier("recommandation triée du plus léger au plus lourd",
         [c["poids_mo"] for c in leger] == sorted(c["poids_mo"] for c in leger))
verifier("bge-m3 écarté d'un budget local serré",
         "bge-m3" not in [c["alias"] for c in leger])
verifier("filtre par environnement",
         "bge-m3" not in [c["alias"] for c in
                          catalogue.recommander("embeddeurs", environnement="local")])
verifier("le domaine 'finance' ramène aussi les généralistes",
         {"fr-finance", "fr-camembert"} <=
         {c["alias"] for c in catalogue.recommander("embeddeurs", domaine="finance")})
verifier("contraintes impossibles → liste vide",
         catalogue.recommander("embeddeurs", ram_max_mo=1) == [])

# Garde-fou de compatibilité : c'est la fonction qui évite l'erreur silencieuse
# la plus coûteuse du projet (index construit par un modèle, interrogé par un autre).
class FausseCollection:
    def __init__(self, dim): self.dim = dim
    def get(self, limit=None, include=None):
        return {"embeddings": [[0.0] * self.dim]}

class FauxModele:
    def __init__(self, dim): self.dim = dim
    def get_sentence_embedding_dimension(self): return self.dim

etat = catalogue.verifier_compatibilite(FausseCollection(768), FauxModele(768), "m", "c")
verifier("dimensions concordantes → passe", etat["verifie"] is True)

try:
    catalogue.verifier_compatibilite(FausseCollection(768), FauxModele(384), "m", "c")
    verifier("dimensions divergentes → refus", False)
except catalogue.IncompatibiliteIndex as e:
    verifier("dimensions divergentes → refus", True)
    verifier("le message d'erreur nomme les deux dimensions",
             "768" in str(e) and "384" in str(e))

class CollectionVide:
    def get(self, limit=None, include=None): return {"embeddings": []}

etat = catalogue.verifier_compatibilite(CollectionVide(), FauxModele(768), "m", "c")
verifier("index vide → non vérifiable, mais pas d'exception", etat["verifie"] is False)

# Les profils doivent tous référencer des alias connus.
for nom_profil in ("minimal", "moyen", "complet"):
    cfg = charger_profil(nom_profil)
    fe = catalogue.resoudre("embeddeurs", cfg["ingestion"]["embeddings"]["modele"])
    verifier(f"profil '{nom_profil}' : embeddeur au catalogue",
             not fe.get("hors_catalogue"), fe["nom"])
    if "reranker" in cfg:
        fr_ = catalogue.resoudre("rerankers", cfg["reranker"]["modele"])
        verifier(f"profil '{nom_profil}' : reranker au catalogue",
                 not fr_.get("hors_catalogue"), fr_["nom"])
    for etape in cfg["pipeline"]:
        if isinstance(etape, dict) and "agent_llm" in etape:
            fl = catalogue.resoudre("llm", etape["agent_llm"]["modele"])
            verifier(f"profil '{nom_profil}' : LLM au catalogue",
                     not fl.get("hors_catalogue"), fl["nom"])


# ─────────────────────────────────────────────────────────────────────────────
print("\n9) Repli sur erreur (sur_erreur) — lot 1 de la phase 3")

from createur import RAG                                      # noqa: E402


class BriqueQuiTombe(Brique):
    """Vide les passages PUIS lève — le cas qui rend l'instantané nécessaire."""
    nom, niveau = "casse", "N3"

    def __init__(self, params=None, ressources=None, tombe_toujours=True):
        super().__init__(params, ressources)
        self.tombe_toujours = tombe_toujours
        self.appels = 0

    def run(self, ctx):
        self.appels += 1
        ctx.passages = []                 # dégât AVANT l'exception
        ctx.noter(self.nom, tentative=self.appels)
        if self.tombe_toujours:
            raise RuntimeError("panne simulée")
        return ctx


class BriqueTemoin(Brique):
    """Brique en aval : prouve que le pipeline a continué."""
    nom, niveau = "temoin", "N4"

    def run(self, ctx):
        ctx.reponse = f"{len(ctx.passages)} passages reçus"
        return ctx


def _rag(politique: str, max_echecs: int = 3, tombe: bool = True) -> tuple:
    params = {"sur_erreur": politique, "max_echecs": max_echecs}
    casse = BriqueQuiTombe(params=params, tombe_toujours=tombe)
    briques = [casse, BriqueTemoin()]
    return RAG({"nom": "test"}, Ressources({}), briques, Journal(actif=True)), casse


# Défaut et validation de la valeur
verifier("sur_erreur vaut 'arreter' par défaut", Brique().sur_erreur == "arreter")
verifier("max_echecs vaut 3 par défaut", Brique().max_echecs == 3)
try:
    Brique(params={"sur_erreur": "ignore"})       # faute de frappe courante
    verifier("valeur inconnue refusée", False)
except ValueError:
    verifier("valeur inconnue refusée (pas de retour silencieux au défaut)", True)

# Instantané / restauration
ctx_test = Contexte(question="q")
ctx_test.passages = [passage("a::p.1::0", "texte a")]
ctx_test.listes = {"vectorielle": ["a::p.1::0"]}
snap = ctx_test.instantane()
ctx_test.passages = []
ctx_test.listes["vectorielle"] = []
ctx_test.traces.append({"brique": "x"})
ctx_test.restaurer(snap)
verifier("restauration : passages retrouvés", len(ctx_test.passages) == 1)
verifier("restauration : listes retrouvées (copie, pas référence)",
         ctx_test.listes["vectorielle"] == ["a::p.1::0"])
verifier("restauration : les traces SURVIVENT au repli", len(ctx_test.traces) == 1)

# Repli effectif
rag, casse = _rag("ignorer")
res = rag.interroger("q")
verifier("repli : le pipeline continue jusqu'au bout", res["reponse"] == "0 passages reçus")
verifier("repli : l'incident est consigné", len(res["bilan"]["erreurs"]) == 1)
verifier("repli : consigné comme repli, pas comme arrêt",
         res["bilan"]["erreurs"][0]["repli"] is True)
verifier("repli : l'erreur nomme la brique fautive",
         res["bilan"]["erreurs"][0]["brique"] == "casse")

# Le contexte est bien restauré AVANT la brique suivante
rag, casse = _rag("ignorer")
rag.briques.insert(0, BriqueTemoin())            # pose une réponse en amont
ctx_amont = Contexte(question="q")
ctx_amont.passages = [passage("a::p.1::0", "texte")]
snap2 = ctx_amont.instantane()
ctx_amont.passages = []
ctx_amont.restaurer(snap2)
verifier("repli : une brique en échec est comme si elle n'avait pas tourné",
         len(ctx_amont.passages) == 1)

# Politique 'arreter'
rag, casse = _rag("arreter")
try:
    rag.interroger("q")
    verifier("arreter : l'exception remonte", False)
except RuntimeError:
    verifier("arreter : l'exception remonte (non-régression préservée)", True)

# Bascule après max_echecs échecs consécutifs
rag, casse = _rag("ignorer", max_echecs=2)
rag.interroger("q1")
rag.interroger("q2")
verifier("bascule : les 2 premiers échecs sont repliés", casse.echecs_consecutifs == 2)
try:
    rag.interroger("q3")
    verifier("bascule : le 3e échec arrête le pipeline", False)
except RuntimeError:
    verifier("bascule : au-delà de max_echecs, la panne installée arrête", True)

# Le compteur retombe à zéro après un succès
rag, casse = _rag("ignorer", max_echecs=1, tombe=True)
rag.interroger("q1")
casse.tombe_toujours = False
rag.interroger("q2")
verifier("compteur remis à zéro après un succès", casse.echecs_consecutifs == 0)
casse.tombe_toujours = True
res = rag.interroger("q3")
verifier("après remise à zéro, le repli fonctionne de nouveau",
         res["bilan"]["erreurs"][-1]["repli"] is True)

# Les profils livrés restent valides
for nom_profil in ("minimal", "moyen", "complet"):
    cfg = charger_profil(nom_profil)
    politiques = {}
    for etape in cfg["pipeline"]:
        nom_b, prm = (etape, {}) if isinstance(etape, str) else next(iter(etape.items()))
        politiques[nom_b] = (prm or {}).get("sur_erreur", "arreter")
    vitales = {"recherche_vectorielle", "recherche_bm25", "agent_llm",
               "constructeur_contexte", "prompt_engineering"}
    verifier(f"profil '{nom_profil}' : aucune brique vitale n'est repliable",
             all(politiques.get(b, "arreter") == "arreter" for b in vitales))

cfg_complet = charger_profil("complet")
noms_replies = [n for e in cfg_complet["pipeline"] if isinstance(e, dict)
                for n, prm in [next(iter(e.items()))]
                if (prm or {}).get("sur_erreur") == "ignorer"]
verifier("profil 'complet' : 5 briques repliables déclarées",
         len(noms_replies) == 5, ", ".join(noms_replies))

cfg_moyen = charger_profil("moyen")
verifier("profil 'moyen' : aucun repli (témoin de non-régression intact)",
         all("sur_erreur" not in (next(iter(e.items()))[1] or {})
             for e in cfg_moyen["pipeline"] if isinstance(e, dict)))


# ─────────────────────────────────────────────────────────────────────────────
print("\n10) Fusion par score pondéré — lot 2 de la phase 3")

from briques.fusion import minmax, fusion_ponderee, Fusion          # noqa: E402

verifier("minmax : le meilleur vaut 1, le pire 0",
         minmax({"a": 1.0, "b": 0.0, "c": 0.5}) == {"a": 1.0, "b": 0.0, "c": 0.5})
verifier("minmax : échelle quelconque ramenée à [0,1]",
         minmax({"a": 100.0, "b": 50.0, "c": 0.0}) == {"a": 1.0, "b": 0.5, "c": 0.0})
verifier("minmax : scores tous égaux → 0,5 (aucune information inventée)",
         minmax({"a": 3.0, "b": 3.0}) == {"a": 0.5, "b": 0.5})
verifier("minmax : liste vide → dict vide", minmax({}) == {})

# Un chunk bien noté par les DEUX moteurs doit passer devant.
scores = {
    "vectorielle": {"consensus": 0.80, "vect_seul": 0.90, "bm_seul": 0.10},
    "bm25":        {"consensus": 8.00, "vect_seul": 0.50, "bm_seul": 9.00},
}
ordre = fusion_ponderee(scores)
verifier("pondérée : le chunk trouvé par les deux moteurs passe premier",
         ordre[0] == "consensus", " → ".join(ordre))

# Le poids doit pouvoir renverser le classement — sinon ce n'est pas un levier.
ordre_vect = fusion_ponderee(scores, {"vectorielle": 1.0, "bm25": 0.0})
verifier("pondérée : poids 100 % vectoriel → le meilleur vectoriel gagne",
         ordre_vect[0] == "vect_seul", " → ".join(ordre_vect))
ordre_bm = fusion_ponderee(scores, {"vectorielle": 0.0, "bm25": 1.0})
verifier("pondérée : poids 100 % BM25 → le meilleur BM25 gagne",
         ordre_bm[0] == "bm_seul", " → ".join(ordre_bm))

# Absent d'une liste = 0 pour ce moteur.
partiel = fusion_ponderee({"vectorielle": {"a": 1.0, "b": 0.0},
                           "bm25": {"b": 5.0}})
verifier("pondérée : un chunk absent d'un moteur n'est pas disqualifié",
         set(partiel) == {"a", "b"}, " → ".join(partiel))

# La brique elle-même : stratégie inconnue refusée, défaut inchangé.
ctx_f = Contexte(question="q")
ctx_f.listes = {"vectorielle": ["a", "b"], "bm25": ["b", "a"]}
try:
    Fusion(params={"strategie": "ponderee"}).run(ctx_f)
    verifier("fusion : stratégie inconnue refusée", False)
except ValueError:
    verifier("fusion : stratégie inconnue refusée", True)

# 'score' sans scores des deux moteurs → repli tracé sur la RRF.
ctx_f = Contexte(question="q")
ctx_f.listes = {"vectorielle": ["a", "b"], "bm25": ["b", "a"]}
ctx_f.scores = {"vectorielle": {"a": 0.9, "b": 0.2}}      # bm25 manquant
import briques.fusion as _mf                                        # noqa: E402
_vrai = _mf.passages_depuis_ids
_mf.passages_depuis_ids = lambda res, ids, scores=None: [passage(i, i) for i in ids]
try:
    Fusion(params={"strategie": "score"}).run(ctx_f)
    note = ctx_f.notes["fusion"]
    verifier("fusion : 'score' sans les deux moteurs → repli sur RRF",
             note.get("strategie_appliquee") == "rrf")
    verifier("fusion : le repli est TRACÉ, pas silencieux",
             "motif" in note, note.get("motif", ""))

    # Cas nominal : les deux moteurs ont déposé leurs scores.
    ctx_f = Contexte(question="q")
    ctx_f.listes = {"vectorielle": ["a", "b"], "bm25": ["b", "a"]}
    ctx_f.scores = {"vectorielle": {"a": 0.9, "b": 0.2},
                    "bm25": {"a": 1.0, "b": 9.0}}
    Fusion(params={"strategie": "score",
                   "poids": {"vectorielle": 1.0, "bm25": 0.0}}).run(ctx_f)
    verifier("fusion : stratégie 'score' appliquée quand les scores sont là",
             ctx_f.notes["fusion"].get("strategie") == "score")
    verifier("fusion : le classement suit les poids",
             [p.id for p in ctx_f.candidats][0] == "a")

    # La RRF reste le défaut : le témoin de non-régression n'est pas touché.
    ctx_f = Contexte(question="q")
    ctx_f.listes = {"vectorielle": ["a", "b"], "bm25": ["b", "a"]}
    Fusion(params={"k": 60, "pool": 10}).run(ctx_f)
    verifier("fusion : la RRF reste la stratégie par défaut",
             ctx_f.notes["fusion"].get("strategie") == "rrf")
finally:
    _mf.passages_depuis_ids = _vrai

# L'instantané doit transporter les scores, sinon le repli les perdrait.
ctx_s = Contexte(question="q")
ctx_s.scores = {"bm25": {"a": 1.0}}
snap_s = ctx_s.instantane()
ctx_s.scores = {}
ctx_s.restaurer(snap_s)
verifier("repli : les scores font partie de l'instantané",
         ctx_s.scores == {"bm25": {"a": 1.0}})


# ─────────────────────────────────────────────────────────────────────────────
print("\n11) Filtres par métadonnées — lot 3 de la phase 3")

from briques.communs import correspond                              # noqa: E402
from briques.recherche_bm25 import RechercheBM25                    # noqa: E402

meta_a = {"domaine": "anatomie", "annee": 2024, "source": "cours.pdf"}

verifier("filtre vide → tout passe", correspond(meta_a, None) and correspond(meta_a, {}))
verifier("égalité simple", correspond(meta_a, {"domaine": "anatomie"}))
verifier("égalité qui échoue", not correspond(meta_a, {"domaine": "droit"}))
verifier("deux clés = ET implicite",
         not correspond(meta_a, {"domaine": "anatomie", "annee": 2020}))
verifier("$eq", correspond(meta_a, {"domaine": {"$eq": "anatomie"}}))
verifier("$ne", correspond(meta_a, {"domaine": {"$ne": "droit"}}))
verifier("$in", correspond(meta_a, {"domaine": {"$in": ["anatomie", "droit"]}}))
verifier("$nin", correspond(meta_a, {"domaine": {"$nin": ["droit"]}}))
verifier("$or", correspond(meta_a, {"$or": [{"domaine": "droit"}, {"annee": 2024}]}))
verifier("$and", correspond(meta_a, {"$and": [{"domaine": "anatomie"}, {"annee": 2024}]}))
verifier("clé absente des métadonnées → ne correspond pas",
         not correspond(meta_a, {"client": "dupont"}))
try:
    correspond(meta_a, {"annee": {"$gt": 2000}})
    verifier("opérateur non réimplémenté → refus explicite", False)
except ValueError:
    verifier("opérateur non réimplémenté → refus explicite (pas d'application à moitié)",
             True)

# BM25 doit appliquer le filtre, sinon la fusion réintroduit le hors-périmètre.
class FauxBM25:
    def __init__(self, scores): self.scores = scores
    def get_scores(self, tokens): return self.scores

def _res_corpus():
    res = Ressources({})
    ids = ["a::p.1::0", "b::p.1::0", "c::p.1::0"]
    res._objets["corpus"] = {
        "ids": ids,
        "texte_par_id": {i: f"texte {i}" for i in ids},
        "meta_par_id": {
            "a::p.1::0": {"domaine": "anatomie", "source": "a.pdf", "locator": "p.1"},
            "b::p.1::0": {"domaine": "droit", "source": "b.pdf", "locator": "p.1"},
            "c::p.1::0": {"domaine": "anatomie", "source": "c.pdf", "locator": "p.1"},
        },
        "bm25": FauxBM25([3.0, 9.0, 1.0]),     # 'b' (hors filtre) est le mieux noté
    }
    return res

ctx_b = Contexte(question="q")
RechercheBM25(ressources=_res_corpus()).run(ctx_b)
verifier("bm25 sans filtre : les 3 chunks, le mieux noté d'abord",
         ctx_b.listes["bm25"] == ["b::p.1::0", "a::p.1::0", "c::p.1::0"])

ctx_b = Contexte(question="q", filtre={"domaine": "anatomie"})
RechercheBM25(ressources=_res_corpus()).run(ctx_b)
verifier("bm25 avec filtre : le hors-périmètre est retiré MALGRÉ son meilleur score",
         ctx_b.listes["bm25"] == ["a::p.1::0", "c::p.1::0"],
         " ".join(ctx_b.listes["bm25"]))
verifier("bm25 : le filtre appliqué apparaît dans la trace",
         ctx_b.notes["recherche_bm25"]["filtre"] == {"domaine": "anatomie"})

ctx_b = Contexte(question="q", filtre={"domaine": "botanique"})
RechercheBM25(ressources=_res_corpus()).run(ctx_b)
verifier("filtre sans résultat : liste vide, PAS de repli hors périmètre",
         ctx_b.listes["bm25"] == [])

# Le filtre voyage dans le contexte et survit au repli.
ctx_f2 = Contexte(question="q", filtre={"client": "dupont"})
snap_f = ctx_f2.instantane()
ctx_f2.filtre = None
ctx_f2.restaurer(snap_f)
verifier("repli : le filtre fait partie de l'instantané",
         ctx_f2.filtre == {"client": "dupont"})

# Priorité : l'appel remplace le profil.
class BriqueLitFiltre(Brique):
    nom, niveau = "lit_filtre", "N2"
    def run(self, ctx):
        ctx.reponse = repr(ctx.filtre)
        return ctx

rag_f = RAG({"nom": "t", "filtre": {"domaine": "anatomie"}}, Ressources({}),
            [BriqueLitFiltre()], Journal(actif=False))
verifier("filtre du profil appliqué par défaut",
         rag_f.interroger("q")["reponse"] == "{'domaine': 'anatomie'}")
verifier("filtre de l'appel : il REMPLACE celui du profil",
         rag_f.interroger("q", filtre={"client": "x"})["reponse"] == "{'client': 'x'}")
verifier("filtre {} à l'appel : lève explicitement le filtre du profil",
         rag_f.interroger("q", filtre={})["reponse"] == "{}")
verifier("le filtre effectif est rendu dans le résultat",
         rag_f.interroger("q")["filtre"] == {"domaine": "anatomie"})


# ─────────────────────────────────────────────────────────────────────────────
print("\n12) Mémoire d'expériences — lot 4 de la phase 3")

import tempfile                                                     # noqa: E402
from memoire import (Memoire, signature, ecart_type, verdict)       # noqa: E402

# Signature : stable, insensible à l'ordre des clés, sensible aux valeurs.
verifier("signature : insensible à l'ordre des clés",
         signature({"a": 1, "b": 2}) == signature({"b": 2, "a": 1}))
verifier("signature : une valeur qui change change l'empreinte",
         signature({"pool": 10}) != signature({"pool": 20}))
verifier("signature : imbrication profonde prise en compte",
         signature({"p": {"k": 1}}) != signature({"p": {"k": 2}}))

# Bruit et verdict.
verifier("écart-type : une seule mesure → 0 (aucune dispersion connue)",
         ecart_type([0.8]) == 0.0)
verifier("écart-type : mesures identiques → 0", ecart_type([0.8, 0.8, 0.8]) == 0.0)
verifier("écart-type : dispersion réelle > 0", ecart_type([0.70, 0.80, 0.75]) > 0)

verifier("verdict : gain seulement au-delà de 2 écarts-types",
         verdict(score=0.90, reference=0.80, bruit=0.02) == "gain")
verifier("verdict : un écart dans le bruit est NEUTRE, pas un gain",
         verdict(score=0.83, reference=0.80, bruit=0.02) == "neutre")
verifier("verdict : régression symétrique",
         verdict(score=0.70, reference=0.80, bruit=0.02) == "regression")
verifier("verdict : bruit inconnu → indéterminé, jamais 'gain'",
         verdict(score=0.95, reference=0.80, bruit=0.0) == "indetermine")

with tempfile.TemporaryDirectory() as d:
    mem = Memoire(Path(d) / "memoire.jsonl")

    # Le garde-fou central : pas de version d'éval, pas d'écriture.
    try:
        mem.enregistrer(corpus="corpus_demo", version_jeu_eval="",
                        parametre="fusion.pool", score=0.8)
        verifier("refus d'écrire sans version du jeu d'éval", False)
    except ValueError as e:
        verifier("refus d'écrire sans version du jeu d'éval", "version_jeu_eval" in str(e))

    cfg_a = {"fusion": {"pool": 10}}
    cfg_b = {"fusion": {"pool": 20}}

    e1 = mem.enregistrer(corpus="corpus_demo", version_jeu_eval="v1",
                         parametre="fusion.pool", avant=10, apres=20,
                         score=0.90, reference=0.80, bruit=0.02, config=cfg_b)
    verifier("verdict calculé à l'écriture", e1["verdict"] == "gain")
    verifier("l'horodatage est posé", "horodatage" in e1)

    # Usage 1 — ne pas refaire.
    r = mem.consulter(cfg_b, corpus="corpus_demo", version_jeu_eval="v1")
    verifier("consulter : configuration déjà mesurée reconnue",
             r["statut"] == "deja_mesure")
    r = mem.consulter(cfg_a, corpus="corpus_demo", version_jeu_eval="v1")
    verifier("consulter : configuration jamais vue → inédit", r["statut"] == "inedit")
    r = mem.consulter(cfg_b, corpus="autre_corpus", version_jeu_eval="v1")
    verifier("consulter : même config, autre corpus → inédit", r["statut"] == "inedit")

    # Le point de vigilance de la fiche : version d'éval différente.
    r = mem.consulter(cfg_b, corpus="corpus_demo", version_jeu_eval="v2")
    verifier("consulter : autre version d'éval → NON COMPARABLE, pas 'déjà mesuré'",
             r["statut"] == "non_comparable")
    verifier("consulter : le motif de non-comparabilité est explicite",
             "comparable" in r.get("motif", ""))

    # Usage 2 — transférer d'un corpus à l'autre.
    mem.enregistrer(corpus="corpus_droit", version_jeu_eval="v1",
                    parametre="fusion.pool", avant=10, apres=20,
                    score=0.88, reference=0.80, bruit=0.02, config=cfg_b)
    mem.enregistrer(corpus="corpus_droit", version_jeu_eval="v1",
                    parametre="fusion.pool", avant=20, apres=10,
                    score=0.79, reference=0.80, bruit=0.02, config=cfg_a)
    ap = mem.a_priori("fusion.pool")
    verifier("a_priori : agrège tous les corpus",
             ap["par_valeur"]["20"]["gain"] == 2, str(ap["par_valeur"]))
    verifier("a_priori : la valeur qui ne gagne pas est comptée neutre",
             ap["par_valeur"]["10"]["neutre"] == 1)
    ap1 = mem.a_priori("fusion.pool", corpus="corpus_demo")
    verifier("a_priori : filtrable par corpus",
             sum(sum(v.values()) for v in ap1["par_valeur"].values()) == 1)

    # Append-only : une ligne corrompue ne doit pas rendre le journal illisible.
    with (Path(d) / "memoire.jsonl").open("a", encoding="utf-8") as f:
        f.write('{"tronque": tru\n')
    verifier("journal : une ligne corrompue est sautée, pas fatale",
             sum(1 for _ in mem.entrees()) == 3)


# ─────────────────────────────────────────────────────────────────────────────
print("\n13) Identité de l'index — point ouvert de la phase 1 soldé")

class CollectionAvecIdentite:
    """Collection Chroma indexée depuis le 31/07 : elle sait qui l'a construite."""
    def __init__(self, embeddeur, dim=768):
        self.metadata = {"embeddeur": embeddeur, "dimension": dim}
        self._dim = dim
    def get(self, limit=None, include=None):
        return {"embeddings": [[0.0] * self._dim]}

class CollectionAncienne(CollectionAvecIdentite):
    """Index antérieur : dimension lisible, embeddeur inconnu."""
    def __init__(self, dim=768):
        super().__init__(embeddeur=None, dim=dim)
        self.metadata = {}

etat = catalogue.verifier_compatibilite(
    CollectionAvecIdentite("sujet-ai/Marsilia-Embeddings-FR-Base"),
    FauxModele(768), "sujet-ai/Marsilia-Embeddings-FR-Base", "corpus_demo")
verifier("index : même embeddeur → passe", etat["verifie"] is True)
verifier("index : l'identité est confirmée, pas seulement la dimension",
         etat["identite_verifiee"] is True)

try:
    catalogue.verifier_compatibilite(
        CollectionAvecIdentite("sujet-ai/Marsilia-Embeddings-FR-Base"),
        FauxModele(768), "intfloat/multilingual-e5-base", "corpus_demo")
    verifier("index : DEUX MODÈLES DE MÊME DIMENSION sont désormais distingués", False)
except catalogue.IncompatibiliteIndex as e:
    verifier("index : deux modèles de même dimension sont désormais distingués",
             "e5-base" in str(e) and "Marsilia" in str(e))

etat = catalogue.verifier_compatibilite(
    CollectionAncienne(), FauxModele(768), "n_importe_lequel", "corpus_demo")
verifier("index ancien : ne bloque pas le démarrage", etat["verifie"] is True)
verifier("index ancien : mais l'identité est signalée comme non vérifiée",
         etat.get("identite_verifiee") is not True)

cfg_t = charger_profil("complet")
verifier("complet.yaml : reranker aligné sur moyen (float16)",
         cfg_t["reranker"]["precision"] == "float16")
verifier("moyen.yaml : reranker toujours en float16",
         charger_profil("moyen")["reranker"]["precision"] == "float16")


# ─────────────────────────────────────────────────────────────────────────────
print("\n14) Non-régression du bug trouvé en relecture (filtre + BM25 seul)")

# Enchaînement réel : un filtre ne laisse rien passer côté vectoriel, BM25 trouve
# quand même des chunks — et le pipeline sortait ZÉRO passage. Deux briques
# correctes séparément, fausses ensemble. Le test fige les deux corrections.
ctx_bug = Contexte(question="q")
ctx_bug.listes["vectorielle"] = []                    # le filtre n'a rien laissé
res_bug = _res_corpus()
RechercheBM25(ressources=res_bug).run(ctx_bug)
verifier("bm25 : liste vectorielle VIDE ≠ vectoriel présent",
         len(ctx_bug.candidats) == 3, f"{len(ctx_bug.candidats)} candidats")

ctx_bug2 = Contexte(question="q")
ctx_bug2.listes = {"vectorielle": [], "bm25": ["a::p.1::0", "c::p.1::0"]}
_vrai2 = _mf.passages_depuis_ids
_mf.passages_depuis_ids = lambda res, ids, scores=None: [passage(i, i) for i in ids]
try:
    Fusion(params={"pool": 10}).run(ctx_bug2)
    verifier("fusion : une seule liste non vide → les candidats sont GARANTIS",
             len(ctx_bug2.candidats) == 2, f"{len(ctx_bug2.candidats)} candidats")

    # Et elle ne doit pas écraser des candidats déjà posés en amont.
    ctx_bug3 = Contexte(question="q")
    ctx_bug3.listes = {"bm25": ["a::p.1::0", "c::p.1::0"]}
    ctx_bug3.candidats = [passage("deja::p.1::0", "posé en amont")]
    Fusion(params={"pool": 10}).run(ctx_bug3)
    verifier("fusion : ne réécrit pas des candidats déjà posés",
             [p.id for p in ctx_bug3.candidats] == ["deja::p.1::0"])
finally:
    _mf.passages_depuis_ids = _vrai2

# L'affichage des incidents dans le résumé de trace.
from observabilite import resumer                                   # noqa: E402
rag_r, casse_r = _rag("ignorer")
bilan_r = rag_r.interroger("q")["bilan"]
verifier("resumer : un repli est visible à l'écran, pas seulement dans le JSON",
         "repli" in resumer(bilan_r) and "casse" in resumer(bilan_r))

# Les trois profils se montent toujours avec leurs nouveaux paramètres.
for nom_profil in ("minimal", "moyen", "complet"):
    cfg = charger_profil(nom_profil)
    montees = _construire_briques(cfg, Ressources({}))
    verifier(f"profil '{nom_profil}' : se monte avec les paramètres du 31/07",
             len(montees) == len(cfg["pipeline"]),
             " → ".join(b.nom for b in montees))


# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'─' * 60}")
print(f"{len(REUSSIS)} réussis, {len(ECHOUES)} échoués")
if ECHOUES:
    for nom in ECHOUES:
        print(f"  ❌ {nom}")
    sys.exit(1)
print("Tout est vert.")
