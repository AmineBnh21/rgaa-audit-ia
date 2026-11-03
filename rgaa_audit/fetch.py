"""Chargement d'une page web rendue par Chromium (Playwright)."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

DELAI_MAX_MS = 30_000


class ErreurChargement(Exception):
    """La page n'a pas pu être chargée."""


@dataclass(frozen=True)
class PageChargee:
    """HTML final de la page, et page Playwright encore ouverte (styles calculés)."""

    url: str
    html: str
    page: Page


@contextmanager
def charger_page(url: str, delai_ms: int = DELAI_MAX_MS) -> Iterator[PageChargee]:
    """Ouvre `url` en headless et garde le navigateur ouvert le temps du bloc `with`."""
    with sync_playwright() as playwright:
        navigateur = playwright.chromium.launch(headless=True)
        try:
            page = navigateur.new_page()
            _naviguer(page, url, delai_ms)
            yield PageChargee(url=page.url, html=page.content(), page=page)
        finally:
            navigateur.close()


def _naviguer(page: Page, url: str, delai_ms: int) -> None:
    try:
        reponse = page.goto(url, wait_until="networkidle", timeout=delai_ms)
    except PlaywrightTimeoutError as erreur:
        raise ErreurChargement(
            f"Délai de {delai_ms // 1000} s dépassé en chargeant {url}"
        ) from erreur
    except PlaywrightError as erreur:
        cause = erreur.message.splitlines()[0]
        raise ErreurChargement(f"URL inaccessible : {url} ({cause})") from erreur

    # Pas de réponse HTTP pour les URL file:// : rien à vérifier
    if reponse is not None and not reponse.ok:
        raise ErreurChargement(f"{url} a répondu avec le code HTTP {reponse.status}")
