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
# The default template below is covered by this version, since jobs that run a raw model
# instead of a preset carry no profile version of their own.
PIPELINE_VERSION = 2

# Transcription prompt for a rendered page. `{page}` is the real page number: the model is
# told what to write so the placeholder it emits already matches our own numbering.
DEFAULT_PROMPT_TEMPLATE = """Transcribe this page image into GitHub-flavoured Markdown.
Reproduce the text verbatim and in reading order, keeping headings, lists, tables and
formulas. Do not summarise, do not comment, and do not wrap your answer in a code fence.

Where a figure, chart, photograph, diagram or map appears, emit a line of the form
![fig](sightread://p{page}/YMIN,XMIN,YMAX,XMAX)
at that position, with the figure's caption verbatim on the very next line (an empty line
when it has none). YMIN, XMIN, YMAX and XMAX are integers in the {bbox_format} coordinate
space: [ymin, xmin, ymax, xmax] normalized to 0-1000, origin at the top-left corner of
this page image. Emit no other Markdown images.
"""


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    description: str
    bbox_format: str
    prompt_template: str
    profile_version: int
    # Catalog matching: an id must be a base id, match `model_pattern`, and contain none
    # of `excluded_terms`.
    model_pattern: re.Pattern[str]
    excluded_terms: tuple[str, ...] = field(default=())

    def resolve_model(self, catalog: list[dict]) -> str | None:
        """Newest base model this profile recognises, or None when the catalog has none.

        An id with a `:` suffix (`:batch`, `:free`, `:extended`, `:nitro`, ...) is a
        routing or pricing variant of a base model, not a model of its own, and none of
        them is ever a candidate: `:batch` is offline batch inference, which would break
        interactive parsing outright.
        """
        candidates = [
            model
            for model in catalog
            if isinstance(model.get("id"), str)
            and ":" not in model["id"]
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
        prompt_template=DEFAULT_PROMPT_TEMPLATE,
        # 2: the phase-1 placeholder wording was replaced by the shipped prompt above.
        profile_version=2,
        model_pattern=re.compile(r"^google/gemini[\w.-]*flash"),
        excluded_terms=("lite", "thinking", "-exp"),
    ),
    Profile(
        id="qwen-yxyx",
        name="Qwen VL (yxyx)",
        description=(
            "Current Qwen VL vision model, prompted for the same "
            "[ymin, xmin, ymax, xmax] boxes normalized to 0-1000."
        ),
        bbox_format=BBOX_FORMAT_YXYX,
        prompt_template=DEFAULT_PROMPT_TEMPLATE,
        profile_version=1,
        model_pattern=re.compile(r"^qwen/qwen[\w.-]*-vl"),
        excluded_terms=("thinking",),
    ),
)


def get_profile(profile_id: str) -> Profile | None:
    return next((profile for profile in PRESET_PROFILES if profile.id == profile_id), None)


def transcription_prompt_template(profile_id: str | None) -> str:
    """The prompt template a job runs when its user stores no custom prompt.

    A raw model that matches no preset runs the default template and is untested by us —
    output quality is then the user's own call (docs/parsing.md § Prompts).
    """
    profile = get_profile(profile_id) if profile_id else None
    return DEFAULT_PROMPT_TEMPLATE if profile is None else profile.prompt_template
