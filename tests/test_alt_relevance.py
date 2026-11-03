from pathlib import Path

import pytest

from rgaa_audit.checks.alt_relevance import statut_depuis_verdict, verifier_pertinence_alt
from rgaa_audit.fetch import charger_page
from rgaa_audit.llm import ContexteImage, ErreurLLM

FIXTURES = Path(__file__).parent / "fixtures"
URL_FIXTURE = (FIXTURES / "images_llm.html").as_uri()

# Réponses simulées du LLM, par alt : aucun vrai appel dans les tests
REPONSES = {
    "Ventes en hausse de 20 % en 2025": ("pertinent", 0.9),
    "image": ("insuffisant", 0.95),
    "Bordure": ("decoratif_mal_balise", 0.4),
}


class FauxLLM:
    def __init__(self):
        self.appels: list[tuple[str, ContexteImage]] = []

    def __call__(self, image_bytes: bytes, alt: str, contexte: ContexteImage) -> dict:
        assert image_bytes.startswith(b"\x89PNG")
        self.appels.append((alt, contexte))
        verdict, confiance = REPONSES[alt]
        return {"verdict": verdict, "justification": "Raison simulée.", "confiance": confiance}


@pytest.mark.parametrize(
    ("verdict", "confiance", "attendu"),
    [
        ("pertinent", 0.9, "conforme"),
        ("insuffisant", 0.9, "non_conforme"),
        ("decoratif_mal_balise", 0.9, "non_conforme"),
        ("pertinent", 0.59, "a_verifier"),
        ("insuffisant", 0.6, "non_conforme"),
    ],
)
def test_mapping_verdict_vers_statut(verdict, confiance, attendu):
    assert statut_depuis_verdict(verdict, confiance) == attendu


def test_evalue_uniquement_les_images_visibles_avec_alt():
    faux_llm = FauxLLM()
    with charger_page(URL_FIXTURE) as chargee:
        resultats, stats = verifier_pertinence_alt(chargee.page, evaluer=faux_llm)

    assert [r.statut for r in resultats] == ["conforme", "non_conforme", "a_verifier"]
    assert all(r.methode == "llm" and r.critere == "RGAA 1.3" for r in resultats)
    assert [r.confiance for r in resultats] == [0.9, 0.95, 0.4]
    assert "vérification humaine" in resultats[2].justification
    assert "data-rgaa-image" not in resultats[0].element
    assert stats.appels == 3


def test_contexte_envoye_au_llm():
    faux_llm = FauxLLM()
    with charger_page(URL_FIXTURE) as chargee:
        verifier_pertinence_alt(chargee.page, evaluer=faux_llm)

    contextes = dict(faux_llm.appels)
    assert "évolution des ventes" in contextes["Ventes en hausse de 20 % en 2025"].texte_environnant
    assert contextes["image"].dans_un_lien is True
    assert contextes["Bordure"].dans_un_lien is False


def test_plafond_d_appels_llm():
    faux_llm = FauxLLM()
    with charger_page(URL_FIXTURE) as chargee:
        resultats, stats = verifier_pertinence_alt(chargee.page, max_images=1, evaluer=faux_llm)

    assert stats.appels == 1
    assert resultats[-1].statut == "a_verifier"
    assert "2 image(s)" in resultats[-1].justification
    assert "--max-llm" in resultats[-1].justification


def test_erreur_llm_donne_a_verifier():
    def llm_en_panne(image_bytes, alt, contexte):
        raise ErreurLLM("réponse JSON invalide")

    with charger_page(URL_FIXTURE) as chargee:
        resultats, stats = verifier_pertinence_alt(chargee.page, evaluer=llm_en_panne)

    assert {r.statut for r in resultats} == {"a_verifier"}
    assert "réponse JSON invalide" in resultats[0].justification
    assert resultats[0].confiance is None
    assert stats.appels == 3


def test_page_sans_image_avec_alt():
    with charger_page((FIXTURES / "page_simple.html").as_uri()) as chargee:
        resultats, stats = verifier_pertinence_alt(chargee.page, evaluer=FauxLLM())

    assert [r.statut for r in resultats] == ["non_applicable"]
    assert stats.appels == 0
