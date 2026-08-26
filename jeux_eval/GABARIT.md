# Jeux d'évaluation — format et fabrication

Ce dossier est **vide dans le dépôt, et c'est voulu.** Un jeu d'évaluation contient
les chemins de fichiers, les `chunk_id` et le texte verbatim du corpus qu'il évalue.
Publier un jeu, c'est publier le corpus. Le `.gitignore` exclut donc `jeux_eval/*`
et ne laisse passer que ce gabarit.

Ce fichier dit **comment en fabriquer un** sur ton propre corpus.

---

## La chaîne, en trois commandes

```bash
# 1. Indexer le corpus (produit chroma_db/ et l'inventaire des chunks)
python createur.py --source mon_corpus --collection mon_projet --profil moyen

# 2. Tirer un échantillon représentatif de chunks
python tools/tirer_echantillon.py --n 20 \
    --inventaire jeux_eval/mon_projet/inventaire.json \
    --sortie     jeux_eval/mon_projet/echantillon.json

# 3. Générer les questions à partir de l'échantillon
python tools/generer_questions.py --modele qwen3:8b --dry-run   # contrôler d'abord
python tools/generer_questions.py --modele qwen3:8b
```

`--dry-run` montre ce qui serait envoyé au modèle sans rien générer. À utiliser
systématiquement au premier passage sur un nouveau corpus : c'est là qu'on voit
que le découpage a produit des chunks inutilisables, avant d'avoir brûlé une heure
de génération.

---

## `inventaire.json` — ce que produit l'indexation

| Champ | Rôle |
|---|---|
| `collection` | le nom de la collection Chroma décrite |
| `n_chunks` | combien de chunks au total |
| `chunks` | un par entrée : `id`, `theme`, `source`, `texte` |
| `groupes` | les thèmes détectés, qui servent de base aux quotas du tirage |
| `equivalences`, `seuil_equivalence` | les quasi-doublons repérés, et le seuil qui les définit |
| `rattachements_forces` | les corrections manuelles de thème, quand la détection se trompe |
| `provenance` | d'où vient l'inventaire : sans ça, on ne sait plus quel index on a mesuré |

Le format d'un `id` est `chemin/du/fichier.docx::::numero_de_chunk`. **C'est ce
champ qui rend un jeu impubliable** : il porte l'arborescence du client.

## `echantillon.json` — ce que produit le tirage

| Champ | Rôle |
|---|---|
| `graine` | la graine aléatoire. **Sans elle, le tirage n'est pas reproductible** et deux mesures ne se comparent plus |
| `seuil_mots` | longueur minimale d'un chunk pour être tirable — un chunk de 12 mots ne porte pas de question |
| `quotas` | combien de chunks par thème, avec au moins 1 par thème présent |
| `chunks` | les chunks tirés, au format de l'inventaire |

---

## Ce qui fait un jeu honnête

**Les quotas suivent le corpus, pas ton intérêt.** Si un thème pèse 40 % des chunks
et 5 % des questions, la mesure ne dit rien de l'usage réel.

**Il faut des questions sans réponse.** Le tirage part de chunks existants : par
construction, toutes les questions générées ont une réponse dans le corpus. Un jeu
qui ne contient que celles-là ne teste jamais la promesse la plus importante — que
le système répond « je ne sais pas ». **Ajoute-les à la main** : plausibles, dans le
domaine, formulées comme les autres, et dont tu sais que la réponse n'est nulle
part. Une question manifestement absurde ne teste rien.

**Écris les réponses attendues avant d'interroger le système.** Après, on écrit sans
le vouloir les questions auxquelles il sait répondre, et le jeu mesure la
complaisance au lieu de mesurer le système. C'est l'erreur la plus banale et elle ne
laisse aucune trace.

**Note la graine, la date et la version du modèle générateur.** Un jeu sans ces
trois-là ne peut pas servir de référence à la mesure suivante.

---

## Nommer les versions

Un jeu se versionne (`mon_projet_v1`, `_v2`…) et **une version ne se modifie jamais
après avoir servi à une mesure.** Corriger trois questions dans un jeu déjà mesuré
rend toutes les mesures antérieures incomparables, silencieusement. On crée `_v3`.

Le champ `version_jeu_eval` de `memoire.jsonl` (voir `MEMOIRE_FORMAT.md`) porte ce
nom : c'est lui qui dit quelles lignes de la mémoire sont comparables entre elles.
