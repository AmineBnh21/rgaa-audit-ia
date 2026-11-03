import pytest

from rgaa_audit import llm
from rgaa_audit.llm import ContexteImage, ErreurLLM, analyser_reponse, evaluer_alt

CONTEXTE = ContexteImage(texte_environnant="Nos résultats 2025", dans_un_lien=False)
JSON_VALIDE = '{"verdict": "pertinent", "justification": "Décrit le graphique.", "confiance": 0.8}'


def test_analyser_reponse_valide():
    assert analyser_reponse(JSON_VALIDE) == {
        "verdict": "pertinent",
        "justification": "Décrit le graphique.",
        "confiance": 0.8,
    }


def test_analyser_reponse_tolere_un_bloc_markdown():
    assert analyser_reponse(f"```json\n{JSON_VALIDE}\n```")["verdict"] == "pertinent"


@pytest.mark.parametrize(
    "texte",
    [
        "Le alt est pertinent.",
        '{"verdict": "bon", "justification": "x", "confiance": 0.8}',
        '{"verdict": "pertinent", "justification": "x", "confiance": 1.5}',
        '{"verdict": "pertinent", "justification": "", "confiance": 0.8}',
        '{"verdict": "pertinent", "confiance": 0.8}',
    ],
)
def test_analyser_reponse_invalide(texte):
    with pytest.raises(ErreurLLM, match="JSON invalide"):
        analyser_reponse(texte)


@pytest.mark.parametrize("fournisseur", ["none", "", "mistral"])
def test_fournisseur_non_pris_en_charge(monkeypatch, fournisseur):
    monkeypatch.setenv("LLM_PROVIDER", fournisseur)
    with pytest.raises(ErreurLLM, match="non pris en charge"):
        evaluer_alt(b"\x89PNG", "Logo", CONTEXTE)


def test_cle_api_absente(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ErreurLLM, match="GEMINI_API_KEY absente"):
        evaluer_alt(b"\x89PNG", "Logo", CONTEXTE)


def test_appel_gemini_simule(monkeypatch):
    envois = []

    def faux_post(url, corps, entetes=None):
        envois.append((url, corps, entetes))
        return {"candidates": [{"content": {"parts": [{"text": JSON_VALIDE}]}}]}

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "cle-de-test")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setattr(llm, "_post", faux_post)

    assert evaluer_alt(b"\x89PNG", "Logo", CONTEXTE)["confiance"] == 0.8
    url, corps, entetes = envois[0]
    assert f"{llm.MODELES_PAR_DEFAUT['gemini']}:generateContent" in url
    assert "cle-de-test" not in url
    assert entetes == {"x-goog-api-key": "cle-de-test"}
    assert '"Logo"' in corps["contents"][0]["parts"][1]["text"]


class FausseReponse:
    def __init__(self, code: int, corps: dict | None = None):
        self.status_code = code
        self.ok = code < 400
        self.text = f"erreur {code}"
        self._corps = corps

    def json(self):
        return self._corps


@pytest.mark.parametrize(
    ("codes", "nb_appels_attendu", "succes"),
    [([200], 1, True), ([503, 200], 2, True), ([503, 503], 2, False), ([404], 1, False)],
)
def test_une_seule_nouvelle_tentative_si_erreur_temporaire(
    monkeypatch, codes, nb_appels_attendu, succes
):
    reponses = iter([FausseReponse(code, {"ok": True}) for code in codes])
    appels = []

    def faux_requests_post(url, **kwargs):
        appels.append(url)
        return next(reponses)

    monkeypatch.setattr(llm.requests, "post", faux_requests_post)
    monkeypatch.setattr(llm, "ATTENTE_AVANT_NOUVEL_ESSAI_S", 0)

    if succes:
        assert llm._post("https://exemple.test", {}) == {"ok": True}
    else:
        with pytest.raises(llm.requests.HTTPError, match=f"HTTP {codes[-1]}"):
            llm._post("https://exemple.test", {})
    assert len(appels) == nb_appels_attendu


def test_reponse_inattendue_du_fournisseur(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr(llm, "_post", lambda url, corps, entetes=None: {"error": "modèle absent"})
    with pytest.raises(ErreurLLM, match="réponse ollama inattendue"):
        evaluer_alt(b"\x89PNG", "Logo", CONTEXTE)
