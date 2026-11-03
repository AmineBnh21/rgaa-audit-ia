"""RGAA 1.3 : l'alternative textuelle de chaque image est-elle pertinente ? (LLM vision)

Seules les images visibles avec un alt non vide sont évaluées, dans la limite de
`max_images` appels : chaque appel coûte du temps et des jetons.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from rgaa_audit.llm import ContexteImage, ErreurLLM, evaluer_alt
from rgaa_audit.models import CheckResult, Statut

CRITERE = "RGAA 1.3"
TITRE = (
    "Chaque image porteuse d'information ayant une alternative textuelle, "
    "cette alternative est-elle pertinente ?"
)

MAX_IMAGES = 5
SEUIL_CONFIANCE = 0.6
DELAI_CAPTURE_MS = 5_000
ATTRIBUT_REPERE = "data-rgaa-image"

Evaluateur = Callable[[bytes, str, ContexteImage], dict]

logger = logging.getLogger(__name__)

# Repère chaque image candidate par un attribut, pour la capturer ensuite de façon fiable
_SCRIPT_COLLECTE = f"""
() => [...document.images].flatMap((img, index) => {{
  const alt = (img.getAttribute("alt") || "").trim();
  if (!alt || img.getClientRects().length === 0) return [];
  const html = img.outerHTML;
  img.setAttribute("{ATTRIBUT_REPERE}", index);
  let bloc = img.parentElement;
  while (bloc && bloc !== document.body && bloc.innerText.trim().length < 50) {{
    bloc = bloc.parentElement;
  }}
  return [{{
    index,
    alt,
    html,
    texte_environnant: (bloc ? bloc.innerText : "").replace(/\\s+/g, " ").trim().slice(0, 300),
    dans_un_lien: img.closest("a[href]") !== null,
  }}];
}})
"""


@dataclass
class StatsLLM:
    appels: int = 0
    duree_s: float = 0.0


def verifier_pertinence_alt(
    page: Page, max_images: int = MAX_IMAGES, evaluer: Evaluateur = evaluer_alt
) -> tuple[list[CheckResult], StatsLLM]:
    """Évalue les `max_images` premières images ayant un alt ; renvoie aussi le coût en appels."""
    images = page.evaluate(_SCRIPT_COLLECTE)
    stats = StatsLLM()
    if not images:
        resultat = _resultat(None, "non_applicable", "Aucune image visible avec un alt non vide.")
        return [resultat], stats

    resultats = [_evaluer_image(page, image, evaluer, stats) for image in images[:max_images]]
    ignorees = len(images) - max_images
    if ignorees > 0:
        resultats.append(
            _resultat(
                None,
                "a_verifier",
                f"{ignorees} image(s) avec alt non évaluée(s) : plafond de {max_images} "
                "appels LLM atteint (option --max-llm).",
            )
        )
    logger.info("RGAA 1.3 : %d appel(s) LLM en %.1f s", stats.appels, stats.duree_s)
    return resultats, stats


def statut_depuis_verdict(verdict: str, confiance: float) -> Statut:
    if confiance < SEUIL_CONFIANCE:
        return "a_verifier"
    return "conforme" if verdict == "pertinent" else "non_conforme"


def _evaluer_image(page: Page, image: dict, evaluer: Evaluateur, stats: StatsLLM) -> CheckResult:
    try:
        capture = page.locator(f'[{ATTRIBUT_REPERE}="{image["index"]}"]').screenshot(
            timeout=DELAI_CAPTURE_MS
        )
    except PlaywrightError as erreur:
        cause = erreur.message.splitlines()[0]
        return _resultat(image, "a_verifier", f"Image non capturable ({cause}) : à vérifier.")

    contexte = ContexteImage(image["texte_environnant"], image["dans_un_lien"])
    stats.appels += 1
    debut = time.perf_counter()
    try:
        reponse = evaluer(capture, image["alt"], contexte)
    except ErreurLLM as erreur:
        return _resultat(image, "a_verifier", f"Évaluation LLM impossible : {erreur}.")
    finally:
        stats.duree_s += time.perf_counter() - debut

    statut = statut_depuis_verdict(reponse["verdict"], reponse["confiance"])
    justification = (
        f'Alt "{image["alt"]}" jugé {reponse["verdict"]} par le LLM : {reponse["justification"]}'
    )
    if statut == "a_verifier":
        justification += (
            f" Confiance inférieure à {SEUIL_CONFIANCE} : vérification humaine requise."
        )
    return _resultat(image, statut, justification, reponse["confiance"])


def _resultat(
    image: dict | None, statut: Statut, justification: str, confiance: float | None = None
) -> CheckResult:
    return CheckResult(
        critere=CRITERE,
        titre=TITRE,
        methode="llm",
        statut=statut,
        element=image["html"] if image is not None else None,
        justification=justification,
        confiance=confiance,
    )
