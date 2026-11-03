# rgaa-audit-ia

[![CI/CD](https://github.com/AmineBnh21/rgaa-audit-ia/actions/workflows/ci.yml/badge.svg)](https://github.com/AmineBnh21/rgaa-audit-ia/actions/workflows/ci.yml)

Prototype Python d'audit d'accessibilité web selon le **RGAA 4.1**. L'outil charge une page dans un vrai navigateur, vérifie trois critères par **règles déterministes** et un critère par **LLM vision**, puis produit un rapport où **chaque verdict est justifié**.

```bash
python audit.py https://exemple.fr                 # audit complet (5 images max pour le LLM)
python audit.py https://exemple.fr --no-llm        # règles seules : aucun appel LLM, aucun coût
python audit.py https://exemple.fr --max-llm 10 --out rapports/
```

Sortie : `rapports/rapport.json` (données) et `rapports/rapport.md` (résumé par critère puis détail), voir [`examples/rapport_exemple.md`](examples/rapport_exemple.md).

| Critère | Ce qui est vérifié | Méthode |
|---|---|---|
| **1.1** Images | `<img>`, `<area>`, `<input type="image">`, `<svg role="img">` ont une alternative textuelle | règle |
| **1.3** Pertinence de l'alternative | l'alt décrit-il vraiment l'image, dans son contexte ? | LLM vision |
| **3.2** Contraste | ratio WCAG entre texte et fond : 4,5:1, ou 3:1 pour le texte large | règle |
| **9.1** Titres | présence d'un `h1`, pas de saut de niveau, pas de titre vide | règle |

## Installation

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env    # puis renseigner LLM_PROVIDER et la clé API correspondante
```

Fournisseurs LLM pris en charge (`LLM_PROVIDER`) : `gemini`, `openai`, `anthropic`, `ollama` (local, sans clé). Le modèle par défaut de chaque fournisseur peut être remplacé avec `LLM_MODEL`.

## Pourquoi des règles pour 1.1, 3.2 et 9.1, et un LLM pour 1.3

Les critères 1.1, 3.2 et 9.1 sont **objectifs et mesurables** : un attribut existe ou non, un ratio de contraste se calcule, une hiérarchie de titres se vérifie. Une règle donne un résultat exact, reproductible, instantané et gratuit. Y mettre un LLM ajouterait du coût et de l'incertitude sans rien apporter.

Le critère 1.3 demande un **jugement sémantique** : `alt="image"` est présent mais inutile, `alt="Ventes en hausse de 20 %"` est faux si l'image est un logo, et dans un lien l'alternative doit décrire la destination plutôt que l'image. Aucune règle ne sait regarder une image et la comparer à son texte. C'est exactement là qu'un LLM vision apporte de la valeur.

Le LLM reçoit une **capture de l'image telle qu'affichée** dans la page, son alt, environ 300 caractères de texte environnant et l'indication d'un éventuel lien parent. Il répond en JSON strict (`verdict`, `justification`, `confiance`), validé par un modèle pydantic.

## Arbitrages : précision, coût, temps

Mesures sur la page Wikipédia « Accessibilité du web » :

| | Résultats | Durée | Coût |
|---|---|---|---|
| Règles seules (`--no-llm`) | 264 | environ 2 s | nul |
| LLM `gemini-3.5-flash` (1.3) | 1 par image | environ 7 à 8 s par image | jetons facturés par image |
| LLM `gemini-3.5-flash-lite` (1.3) | 1 par image | environ 2 s par image | plus faible |

Une seule image évaluée par le LLM prend autant ou plus de temps que les 264 vérifications par règles réunies. Le choix du modèle (`LLM_MODEL`) est lui-même un arbitrage : un modèle léger est plus rapide et moins cher, au prix d'un jugement potentiellement moins fin. D'où plusieurs garde-fous :

- **Plafond d'images** (`--max-llm`, 5 par défaut) : la durée et le coût restent bornés. Les images non évaluées sont signalées dans le rapport, jamais ignorées en silence.
- **`--no-llm`** : audit rapide et gratuit, utilisé en CI.
- **Seuil de confiance** : sous 0,6, le verdict du LLM devient `a_verifier` au lieu d'être présenté comme une certitude. On perd un peu d'automatisation, mais on évite les faux verdicts.
- **Une seule nouvelle tentative** sur erreur temporaire (429, 5xx), pour ne pas allonger l'audit indéfiniment.
- **Plafond de 200 textes** pour le contraste, signalé dans le rapport s'il est atteint.

## Explicabilité

Chaque résultat suit le même modèle (`CheckResult`) : critère, méthode (`regle` ou `llm`), statut, élément concerné et **justification**. Le modèle refuse une justification vide : aucun verdict ne sort sans explication. Exemples tirés de vrais rapports :

- 3.2 : *Texte "Texte trop peu contrasté." : ratio 2.32:1 (#aaaaaa sur #ffffff), minimum 4.5:1 pour du texte normal (16 px, graisse 400).*
- 9.1 : *Saut de niveau : le titre h4 "Détails" suit le titre h2 "Présentation" (niveau h3 attendu au plus).*
- 1.3 : *Alt "Wikipédia" jugé pertinent par le LLM : L'alternative « Wikipédia » restitue fidèlement le texte présent dans l'image et indique clairement le nom du site ainsi que la destination du lien. (confiance 0.95)*

Quatre statuts : `conforme`, `non_conforme`, `a_verifier` (l'outil ne peut pas trancher seul, et le dit) et `non_applicable`. Un échec technique (image non capturable, quota LLM dépassé, JSON invalide) donne `a_verifier` avec la cause, jamais un faux verdict.

## Limites connues

- **Contraste** : les images de fond, dégradés et fonds semi-transparents ne sont pas calculés (statut `a_verifier`). L'opacité CSS (`opacity`) et les éléments superposés par positionnement ne sont pas pris en compte.
- **Critère 1.3 non déterministe et faillible** : deux exécutions peuvent donner des verdicts différents, d'où l'affichage de la confiance et le seuil de 0,6. Le seuil ne suffit pas toujours : dans l'extrait ci-dessous, l'icône de cadenas `alt="Accès payant"`, qui signale une source payante, est jugée insuffisante avec une confiance de 0,95. C'est très probablement un faux positif. Le verdict du LLM reste une aide à l'auditeur, pas une décision. Une image décorative avec un alt non vide est signalée `non_conforme`, alors qu'elle relève en toute rigueur du critère 1.2.
- **`aria-labelledby`** : sa présence est vérifiée, mais pas le contenu de l'élément référencé.
- **Pages inaccessibles au navigateur headless** : pages derrière une authentification, et sites qui bloquent les robots (le W3C renvoie par exemple une erreur 403). L'outil s'arrête avec un message clair.
- **Une seule page** par exécution, et quatre critères sur les 106 du RGAA : l'outil assiste un audit, il ne le remplace pas.

## Industrialisation

Pipeline GitHub Actions (`.github/workflows/ci.yml`) :

1. **lint** : `ruff check` et `ruff format --check` ;
2. **test** : `pytest` avec couverture, sous Python 3.11 et 3.12. Aucun test n'appelle un vrai LLM (réponses simulées) ;
3. **smoke** : audit réel d'une page de test servie en local, sans LLM, et vérification des rapports produits ;
4. **docker** : image publiée sur GitHub Container Registry à chaque push sur `main` ;
5. **release** : release GitHub avec le rapport de démonstration à chaque tag `v*`.

```bash
docker run --rm ghcr.io/aminebnh21/rgaa-audit-ia https://exemple.fr --no-llm
```

## Pistes

- Autres critères RGAA automatisables par règles : 8.3 et 8.5 (langue et titre de la page), 11.1 (étiquettes de formulaires), 6.1 (intitulés de liens).
- Évaluer le LLM sur un jeu d'images annoté par des auditeurs, pour mesurer sa précision et ajuster le seuil de confiance.
- Arrêter les appels LLM dès la première erreur de quota, au lieu de la répéter sur chaque image.
- Auditer plusieurs pages à partir d'un sitemap.

## Structure

```
audit.py                    point d'entrée CLI
rgaa_audit/
  models.py                 CheckResult (pydantic)
  fetch.py                  chargement de la page (Playwright)
  llm.py                    client LLM vision multi-fournisseur
  report.py                 export JSON et Markdown
  checks/
    images_alt.py           RGAA 1.1
    alt_relevance.py        RGAA 1.3 (LLM)
    contrast.py             RGAA 3.2
    headings.py             RGAA 9.1
tests/                      pytest et pages HTML de test
```

## Extrait de rapport

Extrait de [`examples/rapport_exemple.md`](examples/rapport_exemple.md), généré le 03/11/2026 sur la page Wikipédia « Accessibilité du web » avec `LLM_MODEL=gemini-3.5-flash-lite` (270 résultats, 5 appels LLM en 11 s) :

| Critère | Méthode | Conformes | Non conformes | À vérifier | Non applicables |
|---|---|---|---|---|---|
| RGAA 1.1 | regle | 9 | 1 | 4 | 0 |
| RGAA 1.3 | llm | 4 | 1 | 1 | 0 |
| RGAA 3.2 | regle | 200 | 0 | 1 | 0 |
| RGAA 9.1 | regle | 49 | 0 | 0 | 0 |

RGAA 1.3 (LLM) :

- **Conforme** `<img class="mw-logo-wordmark" alt="Wikipédia" ...>` : Alt "Wikipédia" jugé pertinent par le LLM : L'alternative textuelle "Wikipédia" identifie clairement le logo de la marque qui sert également de lien vers la page d'accueil. (confiance 1.00)
- **Non conforme** `<img ... alt="Accès payant" ...>` : Alt "Accès payant" jugé insuffisant par le LLM : L'image représente un cadenas ou un symbole de restriction, mais le texte alternatif 'Accès payant' ne correspond pas à sa fonction, d'autant plus que l'image n'est pas interactive (hors d'un lien) et qu'aucun autre élément ne justifie cette information dans le contexte bibliographique. (confiance 0.95)
- **À vérifier** : 4 image(s) avec alt non évaluée(s) : plafond de 5 appels LLM atteint (option --max-llm).

RGAA 1.1 (règle) :

- **À vérifier** `<img alt="" aria-hidden="true" class="mw-logo-icon" height="50" src="/static/images/icons/wikipedia.png" width="50"/>` : L'attribut alt est vide : acceptable uniquement si l'image est décorative.

Les éléments HTML sont abrégés (`...`) dans cet extrait ; le rapport complet les donne en entier, dans la limite de 200 caractères.
