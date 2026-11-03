from pathlib import Path

import pytest

from rgaa_audit.checks.contrast import (
    BLANC,
    Rgba,
    TexteMesure,
    est_texte_large,
    evaluer_texte,
    parser_couleur,
    ratio_contraste,
    resoudre_fond,
    verifier_contraste,
)
from rgaa_audit.fetch import charger_page

FIXTURES = Path(__file__).parent / "fixtures"
NOIR = Rgba(0, 0, 0)
SANS_FOND = {"couleur": "rgba(0, 0, 0, 0)", "image": "none"}


def mesure(couleur: str, fonds: list[dict[str, str]], taille_px=16.0, graisse=400) -> TexteMesure:
    return TexteMesure("p", "Bonjour", couleur, taille_px, graisse, fonds)


def test_ratio_noir_sur_blanc_vaut_21():
    assert ratio_contraste(NOIR, BLANC) == pytest.approx(21.0)


def test_ratio_777_sur_blanc_vaut_environ_4_48():
    assert ratio_contraste(Rgba(0x77, 0x77, 0x77), BLANC) == pytest.approx(4.48, abs=0.01)


def test_ratio_est_symetrique():
    assert ratio_contraste(BLANC, NOIR) == ratio_contraste(NOIR, BLANC)


@pytest.mark.parametrize(
    ("css", "attendu"),
    [
        ("rgb(119, 119, 119)", Rgba(119, 119, 119, 1.0)),
        ("rgba(0, 0, 0, 0.5)", Rgba(0, 0, 0, 0.5)),
        ("rgb(0 0 0 / 50%)", Rgba(0, 0, 0, 0.5)),
        ("oklch(0.5 0.1 200)", None),
    ],
)
def test_parser_couleur(css, attendu):
    assert parser_couleur(css) == attendu


@pytest.mark.parametrize(
    ("taille_px", "graisse", "attendu"),
    [(16, 400, False), (24, 400, True), (18.66, 700, True), (18.66, 400, False), (18, 700, False)],
)
def test_texte_large(taille_px, graisse, attendu):
    assert est_texte_large(taille_px, graisse) is attendu


def test_fond_par_defaut_blanc():
    assert resoudre_fond([SANS_FOND, SANS_FOND]) == (BLANC, None)


def test_premier_fond_opaque_retenu():
    fonds = [SANS_FOND, {"couleur": "rgb(34, 34, 34)", "image": "none"}]
    assert resoudre_fond(fonds) == (Rgba(34, 34, 34), None)


@pytest.mark.parametrize(
    "fond",
    [
        {"couleur": "rgba(0, 0, 0, 0)", "image": 'url("fond.png")'},
        {"couleur": "rgba(0, 0, 0, 0)", "image": "linear-gradient(red, blue)"},
        {"couleur": "rgba(0, 0, 0, 0.5)", "image": "none"},
    ],
)
def test_fond_non_calculable_a_verifier(fond):
    resultat = evaluer_texte(mesure("rgb(0, 0, 0)", [SANS_FOND, fond]))
    assert resultat.statut == "a_verifier"


def test_777_normal_non_conforme_mais_large_conforme():
    normal = evaluer_texte(mesure("rgb(119, 119, 119)", [SANS_FOND]))
    large = evaluer_texte(mesure("rgb(119, 119, 119)", [SANS_FOND], taille_px=24))

    assert normal.statut == "non_conforme"
    assert "4.48:1 (#777777 sur #ffffff), minimum 4.5:1 pour du texte normal" in (
        normal.justification
    )
    assert large.statut == "conforme"


def test_texte_semi_transparent_fusionne_avec_le_fond():
    # Noir à 50 % sur blanc : gris #808080, ratio ≈ 3.95
    resultat = evaluer_texte(mesure("rgba(0, 0, 0, 0.5)", [SANS_FOND]))
    assert resultat.statut == "non_conforme"
    assert "#808080" in resultat.justification


def test_page_reelle():
    with charger_page((FIXTURES / "contraste.html").as_uri()) as chargee:
        resultats = verifier_contraste(chargee.page)

    statuts = {r.element: r.statut for r in resultats}
    assert statuts == {
        "#ok": "conforme",
        "body > p:nth-of-type(2)": "non_conforme",
        "body > div:nth-of-type(1) > p": "conforme",
        "body > p:nth-of-type(3)": "conforme",
        "body > div:nth-of-type(2) > span": "a_verifier",
    }


def test_limite_atteinte_signalee():
    with charger_page((FIXTURES / "contraste.html").as_uri()) as chargee:
        resultats = verifier_contraste(chargee.page, max_elements=2)

    assert [r.element for r in resultats[:2]] == ["#ok", "body > p:nth-of-type(2)"]
    assert resultats[2].statut == "a_verifier"
    assert resultats[2].element is None
    assert "Limite de 2 textes atteinte" in resultats[2].justification


def test_limite_non_atteinte_pas_de_signalement():
    with charger_page((FIXTURES / "contraste.html").as_uri()) as chargee:
        assert len(verifier_contraste(chargee.page, max_elements=5)) == 5
