"""Client LLM vision : évalue la pertinence d'une alternative textuelle d'image.

Le fournisseur est choisi par la variable d'environnement LLM_PROVIDER, le modèle
par LLM_MODEL (facultatif). Les appels passent par l'API HTTP de chaque fournisseur.
"""

import base64
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import requests
from pydantic import BaseModel, Field, ValidationError

DELAI_S = 60
# Saturation ou quota momentané : une seule nouvelle tentative, pour borner le temps d'audit
CODES_TEMPORAIRES = {429, 500, 502, 503, 504}
ATTENTE_AVANT_NOUVEL_ESSAI_S = 2
MODELES_PAR_DEFAUT = {
    "gemini": "gemini-3.5-flash",
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-haiku-5-5",
    "ollama": "llava",
}

PROMPT = """Tu es auditeur d'accessibilité RGAA 4.1 (critère 1.3).
Évalue si l'alternative textuelle de l'image ci-jointe est pertinente dans son contexte.

Alternative (attribut alt) : "{alt}"
Image placée dans un lien : {dans_un_lien}
Texte environnant : "{texte_environnant}"

Règles :
- "pertinent" : l'alt transmet l'information ou la fonction de l'image (la destination du lien
  si l'image est dans un lien), sans redondance inutile avec le texte environnant.
- "insuffisant" : l'alt est vague, faux, générique (nom de fichier, "image", "photo") ou incomplet.
- "decoratif_mal_balise" : l'image est purement décorative, son alt devrait être vide.

Réponds uniquement par un objet JSON, sans texte autour :
{{"verdict": "pertinent|insuffisant|decoratif_mal_balise",
"justification": "une phrase en français", "confiance": nombre entre 0 et 1}}"""


class ErreurLLM(Exception):
    """L'évaluation par le LLM a échoué (configuration, réseau ou réponse invalide)."""


@dataclass(frozen=True)
class ContexteImage:
    texte_environnant: str
    dans_un_lien: bool


class ReponseLLM(BaseModel):
    verdict: Literal["pertinent", "insuffisant", "decoratif_mal_balise"]
    justification: str = Field(min_length=1)
    confiance: float = Field(ge=0.0, le=1.0)


def evaluer_alt(
    image_bytes: bytes, alt: str, contexte: ContexteImage, type_mime: str = "image/png"
) -> dict:
    """Renvoie {"verdict", "justification", "confiance"} ; lève ErreurLLM en cas d'échec."""
    fournisseur = os.getenv("LLM_PROVIDER", "none").strip().lower()
    appeler = _FOURNISSEURS.get(fournisseur)
    if appeler is None:
        raise ErreurLLM(
            f"LLM_PROVIDER={fournisseur!r} non pris en charge "
            f"(valeurs possibles : {', '.join(_FOURNISSEURS)})"
        )

    modele = os.getenv("LLM_MODEL") or MODELES_PAR_DEFAUT[fournisseur]
    prompt = PROMPT.format(
        alt=alt,
        dans_un_lien="oui" if contexte.dans_un_lien else "non",
        texte_environnant=contexte.texte_environnant,
    )
    image = base64.b64encode(image_bytes).decode("ascii")
    try:
        texte = appeler(modele, prompt, image, type_mime)
    except requests.RequestException as erreur:
        raise ErreurLLM(f"appel {fournisseur} échoué : {erreur}") from erreur
    except (KeyError, IndexError, TypeError, ValueError) as erreur:
        raise ErreurLLM(f"réponse {fournisseur} inattendue : {erreur!r}") from erreur
    return analyser_reponse(texte)


def analyser_reponse(texte: str) -> dict:
    """Valide la réponse JSON stricte du LLM (bloc ```json toléré)."""
    nettoye = texte.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        return ReponseLLM.model_validate_json(nettoye).model_dump()
    except ValidationError as erreur:
        raise ErreurLLM(f"réponse JSON invalide : {nettoye[:120]!r}") from erreur


def _cle(variable: str) -> str:
    cle = os.getenv(variable, "").strip()
    if not cle:
        raise ErreurLLM(f"{variable} absente : la renseigner dans le fichier .env")
    return cle


def _post(url: str, corps: dict, entetes: dict[str, str] | None = None) -> dict:
    reponse = requests.post(url, json=corps, headers=entetes, timeout=DELAI_S)
    if reponse.status_code in CODES_TEMPORAIRES:
        time.sleep(ATTENTE_AVANT_NOUVEL_ESSAI_S)
        reponse = requests.post(url, json=corps, headers=entetes, timeout=DELAI_S)
    if not reponse.ok:
        # Le corps de la réponse explique l'erreur (modèle retiré, quota, clé invalide...)
        detail = " ".join(reponse.text.split())[:300]
        raise requests.HTTPError(f"HTTP {reponse.status_code} : {detail}", response=reponse)
    return reponse.json()


def _appeler_gemini(modele: str, prompt: str, image: str, type_mime: str) -> str:
    donnees = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent",
        {
            "contents": [
                {
                    "parts": [
                        {"inline_data": {"mime_type": type_mime, "data": image}},
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {"response_mime_type": "application/json"},
        },
        # Clé en en-tête plutôt que dans l'URL : elle n'apparaît pas dans les messages d'erreur
        {"x-goog-api-key": _cle("GEMINI_API_KEY")},
    )
    return donnees["candidates"][0]["content"]["parts"][0]["text"]


def _appeler_openai(modele: str, prompt: str, image: str, type_mime: str) -> str:
    donnees = _post(
        "https://api.openai.com/v1/chat/completions",
        {
            "model": modele,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{type_mime};base64,{image}"},
                        },
                    ],
                }
            ],
        },
        {"Authorization": f"Bearer {_cle('OPENAI_API_KEY')}"},
    )
    return donnees["choices"][0]["message"]["content"]


def _appeler_anthropic(modele: str, prompt: str, image: str, type_mime: str) -> str:
    donnees = _post(
        "https://api.anthropic.com/v1/messages",
        {
            "model": modele,
            "max_tokens": 400,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": type_mime, "data": image},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        },
        {"x-api-key": _cle("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"},
    )
    return donnees["content"][0]["text"]


def _appeler_ollama(modele: str, prompt: str, image: str, type_mime: str) -> str:
    hote = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    donnees = _post(
        f"{hote}/api/chat",
        {
            "model": modele,
            "stream": False,
            "format": "json",
            "messages": [{"role": "user", "content": prompt, "images": [image]}],
        },
    )
    return donnees["message"]["content"]


_FOURNISSEURS: dict[str, Callable[[str, str, str, str], str]] = {
    "gemini": _appeler_gemini,
    "openai": _appeler_openai,
    "anthropic": _appeler_anthropic,
    "ollama": _appeler_ollama,
}
