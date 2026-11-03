import json
from datetime import datetime

from rgaa_audit.models import CheckResult
from rgaa_audit.report import ecrire_rapports, generer_markdown, trier

DATE = datetime(2026, 11, 3, 14, 30)


def resultat(critere: str, statut: str, methode: str = "regle", **autres) -> CheckResult:
    return CheckResult(
        critere=critere,
        titre=f"Titre du critère {critere}",
        methode=methode,
        statut=statut,
        justification=f"Justification {statut}.",
        **autres,
    )


RESULTATS = [
    resultat("RGAA 9.1", "non_conforme", element="<h4>Détails</h4>"),
    resultat("RGAA 1.1", "conforme", element='<img alt="Logo">'),
    resultat("RGAA 1.1", "non_conforme", element='<img\n   src="a`b.png">'),
    resultat("RGAA 1.3", "a_verifier", methode="llm", confiance=0.42),
]


def test_tri_par_numero_de_critere_puis_ordre_du_document():
    assert [(r.critere, r.statut) for r in trier(RESULTATS)] == [
        ("RGAA 1.1", "conforme"),
        ("RGAA 1.1", "non_conforme"),
        ("RGAA 1.3", "a_verifier"),
        ("RGAA 9.1", "non_conforme"),
    ]


def test_markdown_resume_et_detail():
    markdown = generer_markdown("https://exemple.fr", RESULTATS, DATE)

    assert "- Page auditée : https://exemple.fr" in markdown
    assert "- Date : 03/11/2026 14:30" in markdown
    assert "| RGAA 1.1 | regle | 1 | 1 | 0 | 0 |" in markdown
    assert "| RGAA 1.3 | llm | 0 | 0 | 1 | 0 |" in markdown
    assert "### RGAA 9.1 : Titre du critère RGAA 9.1" in markdown
    assert "- **Non conforme** `<h4>Détails</h4>` : Justification non_conforme." in markdown
    assert "(confiance 0.42)" in markdown


def test_element_markdown_sur_une_ligne_sans_accent_grave():
    markdown = generer_markdown("https://exemple.fr", RESULTATS, DATE)
    assert '`<img src="a\'b.png">`' in markdown


def test_ecrire_rapports_cree_le_dossier(tmp_path):
    dossier = tmp_path / "sortie" / "audit"
    chemin_json, chemin_md = ecrire_rapports("https://exemple.fr", RESULTATS, dossier, DATE)

    donnees = json.loads(chemin_json.read_text(encoding="utf-8"))
    assert [d["critere"] for d in donnees] == ["RGAA 1.1", "RGAA 1.1", "RGAA 1.3", "RGAA 9.1"]
    assert donnees[0]["element"] == '<img alt="Logo">'
    assert chemin_md.read_text(encoding="utf-8").startswith("# Rapport d'audit RGAA 4.1")
