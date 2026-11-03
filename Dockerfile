# Image officielle Playwright : Chromium et ses dépendances système déjà installés.
# La version DOIT correspondre à celle de playwright dans requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rgaa_audit/ rgaa_audit/
COPY audit.py .

# Dossier de sortie par défaut, inscriptible par l'utilisateur non root
RUN mkdir rapports && chown pwuser:pwuser rapports

# Utilisateur non root (déjà présent dans l'image Playwright)
USER pwuser

ENTRYPOINT ["python", "audit.py"]
CMD ["--help"]
