# Voice transcription

Voice input is optional. The core installation boots without speech-to-text:

```powershell
uv sync --group dev
```

Install the faster-whisper extra when voice answers are needed:

```powershell
uv sync --extra voice --group dev
```

The first transcription downloads the `small` faster-whisper model. It is
cached in `data/models/`, not the operating system temporary directory. To
download it ahead of time without starting the app, run:

```powershell
uv run python -m src.aac_app.providers.model_download
```

The browser records WAV/WebM audio with `MediaRecorder` and uploads it to the
learning API. PyAV, included by faster-whisper, decodes those containers.
Server-side microphone capture and text-to-speech are not required.
