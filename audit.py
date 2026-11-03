"""Point d'entrée CLI : python audit.py <url> [--max-llm 5] [--no-llm] [--out rapports/]"""

import argparse
import logging
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup
from dotenv import load_dotenv

from rgaa_audit.checks.alt_relevance import MAX_IMAGES, StatsLLM, verifier_pertinence_alt
from rgaa_audit.checks.contrast import verifier_contraste
from rgaa_audit.checks.headings import verifier_titres
from rgaa_audit.checks.images_alt import verifier_images_alt
from rgaa_audit.fetch import ErreurChargement, charger_page
from rgaa_audit.models import CheckResult
from rgaa_audit.report import ecrire_rapports


def analyser_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parseur = argparse.ArgumentParser(
        description="Audit d'accessibilité RGAA 4.1 : critères 1.1, 9.1, 3.2 (règles) et 1.3 (LLM)."
    )
    parseur.add_argument("url", help="page à auditer (http://, https:// ou file://)")
    parseur.add_argument(
        "--max-llm",
        type=int,
        default=MAX_IMAGES,
        metavar="N",
        help=f"nombre maximal d'images évaluées par le LLM (défaut : {MAX_IMAGES})",
    )
    parseur.add_argument(
        "--no-llm", action="store_true", help="ne pas évaluer le critère 1.3 (aucun appel LLM)"
    )
    parseur.add_argument(
        "--out", type=Path, default=Path("rapports"), help="dossier de sortie (défaut : rapports/)"
    )
    return parseur.parse_args(arguments)


def auditer(url: str, max_llm: int, avec_llm: bool) -> tuple[list[CheckResult], StatsLLM]:
    with charger_page(url) as chargee:
        soup = BeautifulSoup(chargee.html, "html.parser")
        resultats = verifier_images_alt(soup) + verifier_titres(soup)
        resultats += verifier_contraste(chargee.page)
        if not avec_llm:
            return resultats, StatsLLM()
        resultats_llm, stats = verifier_pertinence_alt(chargee.page, max_llm)
        return resultats + resultats_llm, stats


def main(arguments: list[str] | None = None) -> int:
    args = analyser_arguments(arguments)
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    debut = time.perf_counter()
    try:
        resultats, stats = auditer(args.url, args.max_llm, avec_llm=not args.no_llm)
    except ErreurChargement as erreur:
        print(f"Erreur : {erreur}", file=sys.stderr)
        return 1
    chemin_json, chemin_md = ecrire_rapports(args.url, resultats, args.out)

    print(f"Rapports : {chemin_json} et {chemin_md}")
    print(f"{len(resultats)} résultat(s) en {time.perf_counter() - debut:.1f} s")
    llm = (
        "désactivé (--no-llm)" if args.no_llm else f"{stats.appels} appel(s), {stats.duree_s:.1f} s"
    )
    print(f"LLM : {llm}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
