"""RGAA 9.1 : l'information est-elle structurée par l'utilisation appropriée de titres ?"""

from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from rgaa_audit.models import CheckResult, Statut

CRITERE = "RGAA 9.1"
TITRE = (
    "Dans chaque page web, l'information est-elle structurée "
    "par l'utilisation appropriée de titres ?"
)

SELECTEUR_TITRES = 'h1, h2, h3, h4, h5, h6, [role="heading" i]'
ROLES_NEUTRALISANTS = {"presentation", "none"}
NIVEAU_ARIA_PAR_DEFAUT = 2  # valeur implicite d'aria-level pour role="heading"


@dataclass(frozen=True)
class Titre:
    niveau: int
    texte: str
    element: Tag

    def __str__(self) -> str:
        return f'h{self.niveau} "{self.texte}"'


def verifier_titres(soup: BeautifulSoup) -> list[CheckResult]:
    """Vérifie la présence d'un h1, l'absence de titre vide et de saut de niveau."""
    titres = extraire_titres(soup)
    if not titres:
        return [_resultat(None, "non_conforme", "La page ne contient aucun titre.")]

    resultats = []
    if not any(titre.niveau == 1 for titre in titres):
        resultats.append(_resultat(None, "non_conforme", "La page ne contient aucun titre h1."))

    precedent: Titre | None = None
    for titre in titres:
        resultats.append(_verifier_titre(titre, precedent))
        precedent = titre
    return resultats


def extraire_titres(soup: BeautifulSoup) -> list[Titre]:
    """Titres dans l'ordre du document, niveau ARIA prioritaire sur la balise."""
    titres = []
    for element in soup.select(SELECTEUR_TITRES):
        role = (element.get("role") or "").strip().lower()
        if role in ROLES_NEUTRALISANTS:
            continue
        titres.append(Titre(_niveau(element, role), _texte_accessible(element), element))
    return titres


def _verifier_titre(titre: Titre, precedent: Titre | None) -> CheckResult:
    if not titre.texte:
        return _resultat(titre.element, "non_conforme", f"Le titre h{titre.niveau} est vide.")
    if precedent is not None and titre.niveau > precedent.niveau + 1:
        return _resultat(
            titre.element,
            "non_conforme",
            f"Saut de niveau : le titre {titre} suit le titre {precedent} "
            f"(niveau h{precedent.niveau + 1} attendu au plus).",
        )
    return _resultat(titre.element, "conforme", f"Le titre {titre} respecte la hiérarchie.")


def _niveau(element: Tag, role: str) -> int:
    if role == "heading":
        niveau_aria = (element.get("aria-level") or "").strip()
        if niveau_aria.isdigit() and int(niveau_aria) >= 1:
            return int(niveau_aria)
        if element.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return int(element.name[1])
        return NIVEAU_ARIA_PAR_DEFAUT
    return int(element.name[1])


def _texte_accessible(element: Tag) -> str:
    """Texte du titre, alternatives des images incluses (ex. <h1><img alt="Logo"></h1>)."""
    morceaux = [element.get_text(" ", strip=True)]
    morceaux += [(image.get("alt") or "").strip() for image in element.find_all("img")]
    return " ".join(morceau for morceau in morceaux if morceau)


def _resultat(element: Tag | None, statut: Statut, justification: str) -> CheckResult:
    return CheckResult(
        critere=CRITERE,
        titre=TITRE,
        methode="regle",
        statut=statut,
        element=str(element) if element is not None else None,
        justification=justification,
    )
