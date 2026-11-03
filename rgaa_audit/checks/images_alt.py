"""RGAA 1.1 : chaque image porteuse d'information a-t-elle une alternative textuelle ?"""

from bs4 import BeautifulSoup, Tag

from rgaa_audit.models import CheckResult, Statut

CRITERE = "RGAA 1.1"
TITRE = "Chaque image porteuse d'information a-t-elle une alternative textuelle ?"

SELECTEUR_IMAGES = 'img, area, input[type="image" i], svg[role="img" i]'


def verifier_images_alt(soup: BeautifulSoup) -> list[CheckResult]:
    """Renvoie un verdict par image du document."""
    images = soup.select(SELECTEUR_IMAGES)
    if not images:
        return [
            CheckResult(
                critere=CRITERE,
                titre=TITRE,
                methode="regle",
                statut="non_applicable",
                justification="La page ne contient aucune image.",
            )
        ]
    return [_verifier_image(image) for image in images]


def _verifier_image(image: Tag) -> CheckResult:
    if image.name == "svg":
        return _verifier_svg(image)
    if image.name == "input":
        return _verifier_bouton_image(image)
    return _verifier_attribut_alt(image)


def _verifier_attribut_alt(image: Tag) -> CheckResult:
    """<img> et <area> : l'attribut alt est obligatoire, vide si l'image est décorative."""
    alt = image.get("alt")
    if alt is None:
        return _resultat(image, "non_conforme", f"La balise <{image.name}> n'a pas d'attribut alt.")
    if not alt.strip():
        return _resultat(
            image,
            "a_verifier",
            "L'attribut alt est vide : acceptable uniquement si l'image est décorative.",
        )
    return _resultat(image, "conforme", f'Alternative textuelle présente : "{alt.strip()}".')


def _verifier_bouton_image(bouton: Tag) -> CheckResult:
    """<input type="image"> : un bouton doit toujours avoir un nom, jamais d'alt vide."""
    nom = _premiere_valeur_non_vide(bouton, "alt", "aria-label", "title")
    if nom is None and not bouton.get("aria-labelledby"):
        return _resultat(
            bouton,
            "non_conforme",
            "Le bouton image n'a ni alt, ni aria-label, ni aria-labelledby, ni title non vide.",
        )
    return _resultat(bouton, "conforme", f"Le bouton image a un nom accessible : {_decrire(nom)}.")


def _verifier_svg(svg: Tag) -> CheckResult:
    """<svg role="img"> : alternative via aria-label, aria-labelledby ou un enfant <title>."""
    titre_svg = svg.find("title")
    texte_titre = titre_svg.get_text(strip=True) if titre_svg else ""
    nom = _premiere_valeur_non_vide(svg, "aria-label") or texte_titre or None
    if nom is None and not svg.get("aria-labelledby"):
        return _resultat(
            svg,
            "non_conforme",
            'Le <svg role="img"> n\'a ni aria-label, ni aria-labelledby, ni <title> non vide.',
        )
    return _resultat(svg, "conforme", f"Le SVG a une alternative textuelle : {_decrire(nom)}.")


def _decrire(nom: str | None) -> str:
    # nom absent : l'alternative vient d'aria-labelledby, non résolu ici
    return f'"{nom}"' if nom else "fournie par aria-labelledby"


def _premiere_valeur_non_vide(element: Tag, *attributs: str) -> str | None:
    for attribut in attributs:
        valeur = (element.get(attribut) or "").strip()
        if valeur:
            return valeur
    return None


def _resultat(element: Tag, statut: Statut, justification: str) -> CheckResult:
    return CheckResult(
        critere=CRITERE,
        titre=TITRE,
        methode="regle",
        statut=statut,
        element=str(element),
        justification=justification,
    )
