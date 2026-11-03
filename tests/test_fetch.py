from pathlib import Path

import pytest

from rgaa_audit.fetch import ErreurChargement, charger_page

FIXTURES = Path(__file__).parent / "fixtures"


def test_charge_le_html_rendu_apres_javascript():
    with charger_page((FIXTURES / "page_simple.html").as_uri()) as chargee:
        assert "<h1>Bonjour</h1>" in chargee.html
        assert "Ajouté par JS" in chargee.html
        assert chargee.page.title() == "Page simple"


def test_url_inaccessible_leve_une_erreur_claire():
    # Port 9 (discard) : connexion refusée immédiatement en local
    with pytest.raises(ErreurChargement, match="URL inaccessible"):
        with charger_page("http://127.0.0.1:9/"):
            pass
