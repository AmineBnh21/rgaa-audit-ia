"""RGAA 3.2 : le contraste entre la couleur du texte et celle de son arrière-plan est-il suffisant ?

Le navigateur fournit les styles calculés ; le calcul du ratio et le verdict sont des
fonctions pures, testables sans Playwright.
"""

import re
from dataclasses import dataclass
from typing import NamedTuple

from playwright.sync_api import Page

from rgaa_audit.models import CheckResult, Statut

CRITERE = "RGAA 3.2"
TITRE = (
    "Dans chaque page web, le contraste entre la couleur du texte "
    "et la couleur de son arrière-plan est-il suffisamment élevé ?"
)

MAX_ELEMENTS = 200
SEUIL_TEXTE_NORMAL = 4.5
SEUIL_TEXTE_LARGE = 3.0
TAILLE_LARGE_PX = 24.0
TAILLE_LARGE_GRAS_PX = 18.66
GRAISSE_GRAS = 700

_MOTIF_RGB = re.compile(
    r"rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:\s*[,/]\s*([\d.]+)(%?))?\s*\)"
)

# Collecte côté navigateur : un élément par nœud texte visible, avec la chaîne de ses fonds
_SCRIPT_COLLECTE = """
(max) => {
  const IGNORES = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "OPTION"]);

  const selecteur = (el) => {
    const parties = [];
    for (; el && el !== document.documentElement; el = el.parentElement) {
      if (el.id) { parties.unshift("#" + CSS.escape(el.id)); break; }
      let partie = el.localName;
      const freres = el.parentElement
        ? [...el.parentElement.children].filter((e) => e.localName === el.localName)
        : [el];
      if (freres.length > 1) partie += `:nth-of-type(${freres.indexOf(el) + 1})`;
      parties.unshift(partie);
    }
    return parties.join(" > ");
  };

  const fonds = (el) => {
    const chaine = [];
    for (let n = el; n; n = n.parentElement) {
      const style = getComputedStyle(n);
      chaine.push({ couleur: style.backgroundColor, image: style.backgroundImage });
    }
    return chaine;
  };

  const vus = new Set();
  const textes = [];
  if (!document.body) return textes;
  const parcours = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (textes.length < max && parcours.nextNode()) {
    const texte = parcours.currentNode.textContent.trim();
    const el = parcours.currentNode.parentElement;
    if (!texte || !el || vus.has(el) || IGNORES.has(el.tagName) || el instanceof SVGElement) {
      continue;
    }
    vus.add(el);
    const style = getComputedStyle(el);
    if (style.visibility !== "visible" || el.getClientRects().length === 0) continue;
    textes.push({
      selecteur: selecteur(el),
      texte: texte.slice(0, 80),
      couleur: style.color,
      taille_px: parseFloat(style.fontSize),
      graisse: parseInt(style.fontWeight, 10) || 400,
      fonds: fonds(el),
    });
  }
  return textes;
}
"""


class Rgba(NamedTuple):
    r: float
    g: float
    b: float
    a: float = 1.0

    def en_hex(self) -> str:
        return "#{:02x}{:02x}{:02x}".format(*(round(c) for c in self[:3]))


BLANC = Rgba(255, 255, 255)


@dataclass(frozen=True)
class TexteMesure:
    """Styles calculés d'un élément texte, du plus proche au plus lointain pour les fonds."""

    selecteur: str
    texte: str
    couleur: str
    taille_px: float
    graisse: int
    fonds: list[dict[str, str]]


def verifier_contraste(page: Page, max_elements: int = MAX_ELEMENTS) -> list[CheckResult]:
    """Évalue le contraste des `max_elements` premiers textes visibles de la page."""
    # Un texte de plus que la limite, pour savoir si elle est atteinte
    collectes = page.evaluate(_SCRIPT_COLLECTE, max_elements + 1)
    textes = [TexteMesure(**donnees) for donnees in collectes[:max_elements]]
    if not textes:
        return [_resultat(None, "non_applicable", "La page ne contient aucun texte visible.")]

    resultats = [evaluer_texte(texte) for texte in textes]
    if len(collectes) > max_elements:
        resultats.append(
            _resultat(
                None,
                "a_verifier",
                f"Limite de {max_elements} textes atteinte : les textes suivants de la page "
                "n'ont pas été vérifiés.",
            )
        )
    return resultats


def evaluer_texte(texte: TexteMesure) -> CheckResult:
    extrait = f'Texte "{texte.texte}"'
    couleur = parser_couleur(texte.couleur)
    if couleur is None:
        return _resultat(
            texte, "a_verifier", f"{extrait} : couleur non prise en charge ({texte.couleur})."
        )

    fond, raison = resoudre_fond(texte.fonds)
    if fond is None:
        return _resultat(texte, "a_verifier", f"{extrait} : contraste non calculable, {raison}.")

    couleur = fusionner(couleur, fond)
    ratio = ratio_contraste(couleur, fond)
    large = est_texte_large(texte.taille_px, texte.graisse)
    seuil = SEUIL_TEXTE_LARGE if large else SEUIL_TEXTE_NORMAL
    statut: Statut = "conforme" if ratio >= seuil else "non_conforme"
    return _resultat(
        texte,
        statut,
        f"{extrait} : ratio {ratio:.2f}:1 ({couleur.en_hex()} sur {fond.en_hex()}), "
        f"minimum {seuil}:1 pour du texte {'large' if large else 'normal'} "
        f"({texte.taille_px:g} px, graisse {texte.graisse}).",
    )


def parser_couleur(css: str) -> Rgba | None:
    """Lit une couleur calculée `rgb(...)` / `rgba(...)` ; None pour les autres formats."""
    correspondance = _MOTIF_RGB.fullmatch(css.strip())
    if correspondance is None:
        return None
    r, g, b, alpha, pourcentage = correspondance.groups()
    a = 1.0 if alpha is None else float(alpha) / (100 if pourcentage else 1)
    return Rgba(float(r), float(g), float(b), a)


def resoudre_fond(fonds: list[dict[str, str]]) -> tuple[Rgba | None, str | None]:
    """Premier fond opaque en remontant les parents (blanc à défaut), ou la raison de l'échec."""
    for fond in fonds:
        if fond["image"] != "none":
            return None, "image de fond ou dégradé sur un parent"
        couleur = parser_couleur(fond["couleur"])
        if couleur is None:
            return None, f"couleur de fond non prise en charge ({fond['couleur']})"
        if couleur.a >= 1:
            return couleur, None
        if couleur.a > 0:
            return None, "fond semi-transparent sur un parent"
    return BLANC, None


def fusionner(couleur: Rgba, fond: Rgba) -> Rgba:
    """Couleur perçue d'un texte semi-transparent posé sur un fond opaque."""
    if couleur.a >= 1:
        return couleur
    canaux = zip(couleur[:3], fond[:3], strict=True)
    return Rgba(*(couleur.a * c + (1 - couleur.a) * f for c, f in canaux))


def luminance_relative(couleur: Rgba) -> float:
    """Luminance relative sRGB (WCAG 2.1)."""

    def lineariser(canal: float) -> float:
        c = canal / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lineariser(c) for c in couleur[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio_contraste(premiere: Rgba, seconde: Rgba) -> float:
    claire, foncee = sorted(
        (luminance_relative(premiere), luminance_relative(seconde)), reverse=True
    )
    return (claire + 0.05) / (foncee + 0.05)


def est_texte_large(taille_px: float, graisse: int) -> bool:
    return taille_px >= TAILLE_LARGE_PX or (
        taille_px >= TAILLE_LARGE_GRAS_PX and graisse >= GRAISSE_GRAS
    )


def _resultat(texte: TexteMesure | None, statut: Statut, justification: str) -> CheckResult:
    return CheckResult(
        critere=CRITERE,
        titre=TITRE,
        methode="regle",
        statut=statut,
        element=texte.selecteur if texte is not None else None,
        justification=justification,
    )
