"""Leitet aus Agent-Rolle/Name und zugewiesenem Modell eine Fähigkeitsklasse ab."""

_ROLE_KEYWORDS = {
    "coding": ("engineering", "developer", "coder", "vp engineering", "blender", "drehbuch"),
    "reasoning": ("recherche", "rechercheur", "cto", "ceo", "research", "analyst", "strateg"),
    "classification": ("sekretär", "triage", "router", "office", "admin", "label"),
}
_MODEL_HINTS = {
    "coding": ("coder",),
    "classification": ("0.5b", "0.6b"),
}


def capability_class(role_or_name: str, model: str) -> str:
    role = (role_or_name or "").lower()
    mdl = (model or "").lower()
    for cls, hints in _MODEL_HINTS.items():
        if any(h in mdl for h in hints):
            return cls
    for cls, kws in _ROLE_KEYWORDS.items():
        if any(k in role for k in kws):
            return cls
    return "general"
