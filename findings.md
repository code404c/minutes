# Findings

- The workspace started empty, so the backend is being created from scratch.
- Local `modelscope` cache already contains `Paraformer-large`, `SenseVoiceSmall`, `FSMN-VAD`, `CT-Punc`, and `CAM++`.
- `speaches` is a strong reference for API shape and model lifecycle management.
- `MinerU` is a strong reference for model source abstraction and runtime configuration, but not for long-running audio jobs.

