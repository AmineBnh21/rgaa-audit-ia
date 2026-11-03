import pytest
from pydantic import ValidationError

from rgaa_audit.models import MAX_ELEMENT_LENGTH, CheckResult


def make_result(**overrides) -> CheckResult:
    fields = {
        "critere": "RGAA 1.1",
        "titre": "Chaque image porteuse d'information a-t-elle une alternative textuelle ?",
        "methode": "regle",
        "statut": "non_conforme",
        "element": '<img src="logo.png">',
        "justification": "L'image n'a pas d'attribut alt.",
    }
    return CheckResult(**(fields | overrides))


def test_long_element_is_truncated():
    result = make_result(element="x" * 500)
    assert len(result.element) == MAX_ELEMENT_LENGTH


def test_blank_justification_is_rejected():
    with pytest.raises(ValidationError):
        make_result(justification="   ")


def test_confiance_is_rejected_for_rule_method():
    with pytest.raises(ValidationError):
        make_result(confiance=0.9)


def test_confiance_is_accepted_for_llm_method():
    result = make_result(methode="llm", statut="conforme", confiance=0.8)
    assert result.confiance == 0.8
