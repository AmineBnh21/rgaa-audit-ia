import json
from pathlib import Path

from audit import main

PAGE_TEST = (Path(__file__).parent / "fixtures" / "page_test.html").as_uri()


def test_audit_complet_sans_llm(tmp_path, capsys):
    assert main([PAGE_TEST, "--no-llm", "--out", str(tmp_path / "rapports")]) == 0

    donnees = json.loads((tmp_path / "rapports" / "rapport.json").read_text(encoding="utf-8"))
    non_conformes = {d["critere"] for d in donnees if d["statut"] == "non_conforme"}
    assert non_conformes == {"RGAA 1.1", "RGAA 3.2", "RGAA 9.1"}
    assert all(d["methode"] == "regle" for d in donnees)
    assert (tmp_path / "rapports" / "rapport.md").exists()
    assert "LLM : désactivé (--no-llm)" in capsys.readouterr().out


def test_url_inaccessible_code_de_sortie_1(tmp_path, capsys):
    assert main(["http://127.0.0.1:9/", "--no-llm", "--out", str(tmp_path)]) == 1
    assert "Erreur : URL inaccessible" in capsys.readouterr().err
    assert not (tmp_path / "rapport.json").exists()
