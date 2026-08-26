#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prompt_engineering.py — Agent N4 « prompt-engineering » du REGISTRE.
====================================================================
Extrait de Tuteur.repondre() (la partie qui assemblait le prompt).

Rôle : fabriquer le prompt final à partir du bloc de contexte et de la question.

Généralisation par rapport à tuteur.py : les consignes ne sont plus écrites en
dur dans le code. Le créateur de RAG est GÉNÉRIQUE — le même moteur doit servir
un tuteur de formation, un assistant juridique ou une base documentaire
d'artisan. Ce qui change d'un métier à l'autre, c'est le rôle et le ton, pas la
mécanique. Ils vivent donc dans le profil YAML.

Les deux garde-fous restent, eux, par défaut, parce qu'ils ne sont pas une
question de goût mais de fiabilité :
  · répondre UNIQUEMENT à partir des extraits ;
  · dire franchement quand la réponse ne s'y trouve pas.
Sans eux, le modèle comble les trous avec ce qu'il croit savoir — et un RAG qui
invente est pire qu'une recherche vide, parce que l'erreur est présentée avec
l'autorité d'une source.
"""

from __future__ import annotations

from contrat import Brique, Contexte

GABARIT_DEFAUT = (
    "{consignes}\n\n"
    "Extraits :\n{contexte}\n\n"
    "Question : {question}"
)

CONSIGNES_DEFAUT = (
    "Réponds à la question en t'appuyant UNIQUEMENT sur les extraits numérotés "
    "ci-dessous. Cite tes sources entre crochets, ex. [1], [2], après chaque "
    "affirmation. Si la réponse ne se trouve pas dans les extraits, dis-le "
    "franchement sans inventer."
)


class PromptEngineering(Brique):
    nom = "prompt_engineering"
    niveau = "N4"

    def run(self, ctx: Contexte) -> Contexte:
        consignes = self.params.get("consignes", CONSIGNES_DEFAUT)
        gabarit = self.params.get("gabarit", GABARIT_DEFAUT)

        # Aucun passage retenu : on ne fabrique pas un prompt qui invite le
        # modèle à répondre dans le vide.
        if not ctx.passages:
            ctx.prompt = ""
            ctx.noter(self.nom, ignoree=True, motif="aucun passage retenu")
            return ctx

        ctx.prompt = gabarit.format(
            consignes=consignes,
            contexte=ctx.bloc_contexte,
            question=ctx.question,
        )

        ctx.noter(self.nom, longueur_prompt=len(ctx.prompt),
                  mots_approx=len(ctx.prompt.split()))
        return ctx
