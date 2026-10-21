"""Logs structurés JSON. Ne jamais y mettre de mot de passe, de clé ni de contenu de mail."""

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog

CLES_SENSIBLES = {"password", "mot_de_passe", "token", "cookie", "corps", "corps_texte", "corps_html", "key"}


def _masquer(_: Any, __: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for cle in list(event):
        if any(s in cle.lower() for s in CLES_SENSIBLES):
            event[cle] = "***"
    return event


def configurer_logs(niveau: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", level=niveau)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _masquer,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(niveau)),
    )


log = structlog.get_logger()
