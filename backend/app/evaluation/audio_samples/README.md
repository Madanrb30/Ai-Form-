# Benchmark Audio Samples Directory

This directory stores real speech audio recordings used for empirical accuracy and latency benchmarking across STT models:
- Groq Whisper Large v3 Turbo (`whisper-large-v3-turbo`)
- Groq Whisper Large v3 (`whisper-large-v3`)
- Sarvam AI Saaras v4 (`saaras:v4`)

## Prerequisites & Rules
1. Every audio sample evaluated must be a real audio recording (.wav, .webm, .mp3, .m4a).
2. Synthetic audio or identical self-predictions are strictly forbidden.
3. Audio files must correspond to the definitions in `samples_manifest.json`.
4. If an audio file is missing, the benchmark marks the sample as `INCOMPLETE (MISSING_AUDIO)`.
5. Do not commit sensitive recordings containing personal identifying information (PII) to git without explicit user authorization.

## Expected Sample Files:
- `sample_en_01.wav`: English utterance with name, email, register number
- `sample_tanglish_01.wav`: Tamil-English code-switched utterance with Tamil grammar + English department
- `sample_tanglish_02.wav`: Tanglish utterance with location, phone number, pincode
- `sample_tanglish_03.wav`: Tanglish date and radio selection
- `sample_ta_01.wav`: Pure Tamil script spoken utterance
