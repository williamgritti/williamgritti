"""Sample of the legacy patterns this tool exists to find. Deliberately wrong."""

import re

CNPJ_RE = re.compile(r"^\d{14}$")


def salvar(payload):
    cnpj = payload["cnpj"]
    if not CNPJ_RE.match(cnpj):
        raise ValueError("CNPJ invalido")
    return int(cnpj)
