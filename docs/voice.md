# Voice transcription

Voice input is optional. The core installation boots without speech-to-text:

```powershell
uv sync --group dev
```

Install the faster-whisper extra when voice answers are needed:

```powershell
uv sync --extra voice --group dev
```

On Windows source checkouts, an administrator can also install the missing
voice extra from Settings -> Voice with one click. The packaged installer
bundles the `tiny` model, so the installed app needs no first-use download for
the default voice model; selecting another model size falls back to on-demand
download into `data/models/`.

On a source checkout the first transcription downloads the `tiny` faster-whisper model by default (about 39M parameters / 75 MB; the compatible CTranslate2 conversion of OpenAI's `openai/whisper-tiny`). Administrators can choose `tiny`, `base`, `small`, `medium`, or `large-v3` in Settings → Voice. It is
cached in `data/models/`, not the operating system temporary directory. To
download it ahead of time without starting the app, run:

```powershell
uv run python -m src.aac_app.providers.model_download
```

The browser records WAV/WebM audio with `MediaRecorder` and uploads it to the
learning API. PyAV, included by faster-whisper, decodes those containers.
Server-side microphone capture and text-to-speech are not required.
