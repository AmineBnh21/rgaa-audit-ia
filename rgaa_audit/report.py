"""Export des résultats d'audit : rapport.json (données) et rapport.md (lecture humaine)."""

import json
import re
from collections import Counter
from datetime import datetime
from itertools import groupby
from pathlib import Path

from rgaa_audit.models import CheckResult, Statut

LIBELLES_STATUT: dict[Statut, str] = {
    "conforme": "Conforme",
    "non_conforme": "Non conforme",
    "a_verifier": "À vérifier",
    "non_applicable": "Non applicable",
}


def ecrire_rapports(
    url: str, resultats: list[CheckResult], dossier: Path, date: datetime | None = None
) -> tuple[Path, Path]:
    """Écrit rapport.json et rapport.md dans `dossier` (créé au besoin) et renvoie leurs chemins."""
    dossier.mkdir(parents=True, exist_ok=True)
    chemin_json = dossier / "rapport.json"
    chemin_md = dossier / "rapport.md"
    donnees = [resultat.model_dump() for resultat in trier(resultats)]
    chemin_json.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    chemin_md.write_text(generer_markdown(url, resultats, date or datetime.now()), encoding="utf-8")
    return chemin_json, chemin_md


def generer_markdown(url: str, resultats: list[CheckResult], date: datetime) -> str:
    resultats = trier(resultats)
    lignes = [
        "# Rapport d'audit RGAA 4.1",
        "",
        f"- Page auditée : {url}",
        f"- Date : {date:%d/%m/%Y %H:%M}",
        "",
        "## Résumé par critère",
        "",
        "| Critère | Méthode | Conformes | Non conformes | À vérifier | Non applicables |",
        "|---|---|---|---|---|---|",
    ]
    groupes = [(critere, list(groupe)) for critere, groupe in groupby(resultats, _critere)]
    for critere, groupe in groupes:
        comptes = Counter(resultat.statut for resultat in groupe)
        lignes.append(
            f"| {critere} | {groupe[0].methode} | {comptes['conforme']} | "
            f"{comptes['non_conforme']} | {comptes['a_verifier']} | {comptes['non_applicable']} |"
        )

    lignes += ["", "## Détail", ""]
    for critere, groupe in groupes:
        lignes += [f"### {critere} : {groupe[0].titre}", ""]
        lignes += [_ligne_detail(resultat) for resultat in groupe]
        lignes.append("")
    return "\n".join(lignes)


def trier(resultats: list[CheckResult]) -> list[CheckResult]:
    """Ordre des critères (1.1 < 1.3 < 3.2 < 9.1), ordre du document conservé à l'intérieur."""
    return sorted(resultats, key=lambda resultat: _numero(resultat.critere))


def _ligne_detail(resultat: CheckResult) -> str:
    ligne = f"- **{LIBELLES_STATUT[resultat.statut]}**"
    if resultat.element:
        # Une seule ligne, sans accent grave qui fermerait le bloc de code
        element = " ".join(resultat.element.split()).replace("`", "'")
        ligne += f" `{element}`"
    ligne += f" : {resultat.justification}"
    if resultat.confiance is not None:
        ligne += f" (confiance {resultat.confiance:.2f})"
    return ligne


def _critere(resultat: CheckResult) -> str:
    return resultat.critere


def _numero(critere: str) -> tuple[int, ...]:
    return tuple(int(nombre) for nombre in re.findall(r"\d+", critere))
