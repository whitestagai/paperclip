"""Typisierte Entscheidungen gegen ein lokales LM-Studio-Modell.

Statt das Modell einen Text schreiben zu lassen, der danach geparst werden muss,
wird genau EIN Token erzeugt und die Wahrscheinlichkeitsverteilung darueber
ausgelesen. Die Masse auf den erlaubten Optionen wird renormiert — damit kann
das Modell keine Option erfinden und keinen Formatfehler machen.

Das Verfahren stammt aus der Jev-/System-One-Familie (SemIf liest Logits von
einem ungetunten Modell ab). Hier ohne neues Modell und ohne externen Dienst,
weil unsere Modelle die Logprobs selbst liefern.

★ FALLE: Ohne `reasoning_effort: "none"` denkt Gemma 4 im GGUF, `content` bleibt
leer — und dann ist auch `logprobs.content` leer. Das sieht aus, als koennte das
Modell keine Logprobs. Deshalb steht der Schalter hier fest im Request.
"""
from dataclasses import dataclass
from typing import Optional
import math

ABSTAIN_NO_LOGPROBS = "keine_logprobs"
ABSTAIN_LOW_MASS = "zu_wenig_masse_auf_optionen"
ABSTAIN_LOW_CONFIDENCE = "konfidenz_unter_schwelle"

TOP_LOGPROBS = 20


@dataclass
class Decision:
    option: Optional[str]
    confidence: float
    mass: float
    probs: dict
    abstained: bool
    reason: Optional[str] = None

    def require_option(self) -> str:
        """Die Option holen und dabei erzwingen, dass entschieden wurde."""
        if self.abstained or self.option is None:
            raise ValueError(f"keine Entscheidung getroffen: {self.reason}")
        return self.option


def build_request(model, state, instructions, options):
    """Den Chat-Completions-Request fuer eine typisierte Auswahl bauen."""
    legend = "\n".join(options)
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": f"{instructions}\n\nAntworte mit genau einem dieser Zeichen:\n{legend}"},
            {"role": "user", "content": state},
        ],
        "temperature": 0,
        "max_tokens": 1,
        "logprobs": True,
        "top_logprobs": TOP_LOGPROBS,
        # Nicht entfernen — siehe Modulkommentar.
        "reasoning_effort": "none",
    }


def extract_option_probs(top_logprobs, options):
    """Rohe Wahrscheinlichkeiten der erlaubten Optionen und ihre Gesamtmasse."""
    raw = {o: 0.0 for o in options}
    for entry in top_logprobs:
        label = entry["token"].strip()
        if label in raw:
            raw[label] += math.exp(entry["logprob"])
    mass = sum(raw.values())
    if mass <= 0:
        return raw, 0.0
    return {k: v / mass for k, v in raw.items()}, mass


def decide(top_logprobs, options, min_confidence=0.9, min_mass=0.5):
    """Eine typisierte Entscheidung mit Enthaltung bei Unsicherheit."""
    if not top_logprobs:
        return Decision(None, 0.0, 0.0, {}, True, ABSTAIN_NO_LOGPROBS)

    probs, mass = extract_option_probs(top_logprobs, options)
    if mass < min_mass:
        return Decision(None, 0.0, mass, probs, True, ABSTAIN_LOW_MASS)

    best = max(probs, key=probs.get)
    conf = probs[best]
    if conf < min_confidence:
        # Die Neigung bleibt sichtbar, damit ein Mensch sie bewerten kann.
        return Decision(best, conf, mass, probs, True, ABSTAIN_LOW_CONFIDENCE)
    return Decision(best, conf, mass, probs, False)
