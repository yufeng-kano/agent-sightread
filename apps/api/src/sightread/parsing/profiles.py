"""Preset parsing profiles (docs/parsing.md § Profiles).

A profile is a model choice + coordinate prompt template + response contract + version.
Model ids are never hard-coded: each profile matches the *live* OpenRouter catalog and
picks the newest model it recognises, so a retired id can never strand a profile. When the
catalog has no match the profile simply reports `available: false`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Coordinate contract for every preset: [ymin, xmin, ymax, xmax], normalized 0-1000,
# origin top-left. The service never converts coordinates (docs/parsing.md).
BBOX_FORMAT_YXYX = "yxyx_norm1000"

# Part of the dedup cache key; bump when the pipeline changes results (docs/jobs.md).
PIPELINE_VERSION = 1

# Placeholder wording — the phase that implements vision calls owns the final prompt.
YXYX_PROMPT_TEMPLATE = """Transcribe this page as GitHub-flavoured Markdown.
For every figure, chart, photo or diagram, emit a placeholder line
![fig{{n}}](sightread://p{{page}}/{{ymin}},{{xmin}},{{ymax}},{{xmax}}) followed by the
caption verbatim on the next line.
Bounding boxes must be [ymin, xmin, ymax, xmax], integers normalized to 0-1000 with the
origin at the top-left corner of the page image ({bbox_format}).
"""


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    description: str
    bbox_format: str
    prompt_template: str
    profile_version: int
    # Catalog matching: an id must match `model_pattern` and contain none of `excluded_terms`.
    model_pattern: re.Pattern[str]
    excluded_terms: tuple[str, ...] = field(default=())

    def resolve_model(self, catalog: list[dict]) -> str | None:
        """Newest catalog model this profile recognises, or None when the catalog has none."""
        candidates = [
            model
            for model in catalog
            if isinstance(model.get("id"), str)
            and self.model_pattern.search(model["id"])
            and not any(term in model["id"] for term in self.excluded_terms)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda model: (model.get("created") or 0, model["id"]), reverse=True)
        return candidates[0]["id"]


PRESET_PROFILES: tuple[Profile, ...] = (
    Profile(
        id="gemini-yxyx",
        name="Gemini (yxyx)",
        description=(
            "Current Gemini flash-tier vision model, prompted for Gemini-native "
            "[ymin, xmin, ymax, xmax] boxes normalized to 0-1000."
        ),
        bbox_format=BBOX_FORMAT_YXYX,
        prompt_template=YXYX_PROMPT_TEMPLATE,
        profile_version=1,
        model_pattern=re.compile(r"^google/gemini[\w.-]*flash"),
        excluded_terms=("lite", "thinking", ":free", "-exp"),
    ),
)


def get_profile(profile_id: str) -> Profile | None:
    return next((profile for profile in PRESET_PROFILES if profile.id == profile_id), None)
