from dataclasses import dataclass
from enum import StrEnum


class JobProfile(StrEnum):
    CN_MEETING = "cn_meeting"
    MULTILINGUAL_RICH = "multilingual_rich"


@dataclass(frozen=True, slots=True)
class ProfileSpec:
    name: JobProfile
    display_name: str
    asr_model_id: str
    vad_model_id: str
    punc_model_id: str | None
    speaker_model_id: str | None
    default_language: str
    supports_hotwords: bool
    enable_rich_tags: bool


PROFILE_SPECS: dict[JobProfile, ProfileSpec] = {
    JobProfile.CN_MEETING: ProfileSpec(
        name=JobProfile.CN_MEETING,
        display_name="Chinese Meeting",
        asr_model_id="iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        vad_model_id="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        punc_model_id="iic/punc_ct-transformer_cn-en-common-vocab471067-large",
        speaker_model_id="iic/speech_campplus_sv_zh-cn_16k-common",
        default_language="zh",
        supports_hotwords=True,
        enable_rich_tags=False,
    ),
    JobProfile.MULTILINGUAL_RICH: ProfileSpec(
        name=JobProfile.MULTILINGUAL_RICH,
        display_name="Multilingual Rich",
        asr_model_id="iic/SenseVoiceSmall",
        vad_model_id="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        punc_model_id=None,
        speaker_model_id="iic/speech_campplus_sv_zh-cn_16k-common",
        default_language="auto",
        supports_hotwords=False,
        enable_rich_tags=True,
    ),
}


def resolve_profile(value: str | JobProfile | None) -> JobProfile:
    if value is None:
        return JobProfile.CN_MEETING
    if isinstance(value, JobProfile):
        return value
    return JobProfile(value)


def get_profile_spec(value: str | JobProfile | None) -> ProfileSpec:
    return PROFILE_SPECS[resolve_profile(value)]
