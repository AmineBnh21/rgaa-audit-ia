from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from rgaa_audit.checks.images_alt import verifier_images_alt

FIXTURES = Path(__file__).parent / "fixtures"


def statuts(html: str) -> list[str]:
    return [resultat.statut for resultat in verifier_images_alt(BeautifulSoup(html, "html.parser"))]


def test_fixture_image_ok_sans_alt_et_alt_vide():
    html = (FIXTURES / "images.html").read_text(encoding="utf-8")
    resultats = verifier_images_alt(BeautifulSoup(html, "html.parser"))

    assert [r.statut for r in resultats] == ["conforme", "non_conforme", "a_verifier"]
    assert all(r.critere == "RGAA 1.1" and r.methode == "regle" for r in resultats)
    assert "graphique.png" in resultats[1].element
    assert "décorative" in resultats[2].justification


def test_page_sans_image_non_applicable():
    assert statuts("<p>Texte seul</p>") == ["non_applicable"]


@pytest.mark.parametrize(
    ("html", "attendu"),
    [
        ('<map><area href="/a" alt="Accueil"></map>', "conforme"),
        ('<map><area href="/a"></map>', "non_conforme"),
        ('<input type="image" src="ok.png" alt="Rechercher">', "conforme"),
        ('<input type="IMAGE" src="ok.png" aria-label="Rechercher">', "conforme"),
        ('<input type="image" src="ok.png" alt="">', "non_conforme"),
        ('<svg role="img" aria-label="Graphique des ventes"></svg>', "conforme"),
        ('<svg role="img"><title>Graphique des ventes</title></svg>', "conforme"),
        ('<svg role="img" aria-labelledby="legende"></svg>', "conforme"),
        ('<svg role="img"><title> </title></svg>', "non_conforme"),
    ],
)
def test_types_d_images(html, attendu):
    assert statuts(html) == [attendu]


def test_svg_sans_role_img_ignore():
    assert statuts("<svg><path d='M0 0'/></svg>") == ["non_applicable"]
