"""Modèle de résultat commun à tous les critères."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_ELEMENT_LENGTH = 200

Methode = Literal["regle", "llm"]
Statut = Literal["conforme", "non_conforme", "a_verifier", "non_applicable"]


class CheckResult(BaseModel):
    """Verdict justifié sur un élément pour un critère RGAA."""

    critere: str = Field(description='Identifiant du critère, ex. "RGAA 1.1"')
    titre: str = Field(description="Intitulé officiel du critère")
    methode: Methode
    statut: Statut
    element: str | None = Field(
        default=None,
        description="Sélecteur CSS ou extrait HTML tronqué",
    )
    justification: str = Field(min_length=1, description="Explication lisible du verdict")
    confiance: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("element")
    @classmethod
    def _truncate_element(cls, value: str | None) -> str | None:
        if value is None or len(value) <= MAX_ELEMENT_LENGTH:
            return value
        return value[: MAX_ELEMENT_LENGTH - 1] + "…"

    @field_validator("justification")
    @classmethod
    def _justification_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("un résultat doit toujours être justifié")
        return value.strip()

    @model_validator(mode="after")
    def _confiance_only_for_llm(self) -> "CheckResult":
        if self.methode == "regle" and self.confiance is not None:
            raise ValueError("la confiance est réservée à la méthode llm")
        return self
