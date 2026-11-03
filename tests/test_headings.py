from pathlib import Path

from bs4 import BeautifulSoup

from rgaa_audit.checks.headings import extraire_titres, verifier_titres

FIXTURES = Path(__file__).parent / "fixtures"


def verifier(html: str):
    return verifier_titres(BeautifulSoup(html, "html.parser"))


def verifier_fixture(nom: str):
    return verifier((FIXTURES / nom).read_text(encoding="utf-8"))


def test_saut_de_niveau_cite_le_titre_fautif_et_le_precedent():
    resultats = verifier_fixture("titres_saut.html")

    assert [r.statut for r in resultats] == ["conforme", "conforme", "non_conforme"]
    justification = resultats[2].justification
    assert 'h4 "Tarifs"' in justification
    assert 'h2 "Particuliers"' in justification


def test_page_sans_h1():
    resultats = verifier_fixture("titres_sans_h1.html")

    assert resultats[0].statut == "non_conforme"
    assert resultats[0].element is None
    assert "aucun titre h1" in resultats[0].justification
    assert [r.statut for r in resultats[1:]] == ["conforme", "conforme"]


def test_page_sans_aucun_titre():
    resultats = verifier("<p>Texte</p>")
    assert [r.statut for r in resultats] == ["non_conforme"]
    assert "aucun titre" in resultats[0].justification


def test_titre_vide():
    resultats = verifier("<h1>Accueil</h1><h2>  </h2>")
    assert resultats[1].statut == "non_conforme"
    assert "vide" in resultats[1].justification


def test_image_avec_alt_dans_un_titre_n_est_pas_vide():
    assert verifier('<h1><img src="logo.png" alt="Logo"></h1>')[0].statut == "conforme"


def test_remonter_de_plusieurs_niveaux_est_autorise():
    resultats = verifier("<h1>A</h1><h2>B</h2><h3>C</h3><h2>D</h2>")
    assert all(r.statut == "conforme" for r in resultats)


def test_role_heading_et_aria_level():
    titres = extraire_titres(
        BeautifulSoup(
            '<div role="heading" aria-level="3">A</div>'
            '<div role="heading">B</div>'
            '<h2 role="heading" aria-level="4">C</h2>'
            '<h1 role="presentation">D</h1>',
            "html.parser",
        )
    )
    assert [(t.niveau, t.texte) for t in titres] == [(3, "A"), (2, "B"), (4, "C")]
