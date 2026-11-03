import pytest
from pydantic import ValidationError

from rgaa_audit.models import LONGUEUR_MAX_ELEMENT, CheckResult


def creer_resultat(**surcharges) -> CheckResult:
    champs = {
        "critere": "RGAA 1.1",
        "titre": "Chaque image porteuse d'information a-t-elle une alternative textuelle ?",
        "methode": "regle",
        "statut": "non_conforme",
        "element": '<img src="logo.png">',
        "justification": "L'image n'a pas d'attribut alt.",
    }
    return CheckResult(**(champs | surcharges))


def test_element_long_est_tronque():
    resultat = creer_resultat(element="x" * 500)
    assert len(resultat.element) == LONGUEUR_MAX_ELEMENT


def test_justification_vide_refusee():
    with pytest.raises(ValidationError):
        creer_resultat(justification="   ")


def test_confiance_refusee_pour_methode_regle():
    with pytest.raises(ValidationError):
        creer_resultat(confiance=0.9)


def test_confiance_acceptee_pour_methode_llm():
    resultat = creer_resultat(methode="llm", statut="conforme", confiance=0.8)
    assert resultat.confiance == 0.8
