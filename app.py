import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import yt_dlp
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv()

BASE = Path(__file__).parent
JOBS_DIR = BASE / "jobs"
JOBS_DIR.mkdir(exist_ok=True)
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

CATEGORIES = {
    "humor": "momentos engraçados: piadas, reações, situações cômicas, timing de comédia",
    "tecnologia": "explicações, novidades, opiniões ou demonstrações sobre tecnologia",
    "curiosidades": "fatos surpreendentes, curiosidades e informações que prendem a atenção",
    "educacao": "trechos que ensinam algo de forma clara e completa",
    "polemica": "opiniões fortes, debates e falas que geram discussão",
    "emocionante": "momentos emocionantes, inspiradores ou marcantes",
    "esportes": "lances, jogadas, reações e comentários esportivos marcantes",
    "games": "jogadas, reações e momentos marcantes de gameplay",
}

jobs: dict[str, dict] = {}


class Clip(BaseModel):
    start: str
    end: str
    title: str
    reason: str
    score: int


def to_seconds(ts: str) -> float:
    parts = [float(p) for p in ts.strip().split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def download(url: str, dest: Path) -> Path:
    opts = {
        "format": "bv*[height<=720]+ba/b[height<=720]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(dest / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return next(dest.glob("source.*"))


def analyze(video: Path, category: str) -> list[Clip]:
    client = genai.Client()
    f = client.files.upload(file=str(video))
    while not f.state or f.state.name != "ACTIVE":
        if f.state and f.state.name == "FAILED":
            raise RuntimeError("Gemini falhou ao processar o vídeo")
        time.sleep(5)
        f = client.files.get(name=f.name)
    prompt = (
        f"Você é um editor de vídeos curtos. Assista ao vídeo inteiro (imagem e áudio) "
        f"e encontre os melhores trechos da categoria '{category}': {CATEGORIES[category]}.\n"
        "Regras:\n"
        "- Cada corte deve ter entre 15 e 90 segundos e funcionar sozinho, com começo e fim naturais "
        "(não começar nem terminar no meio de uma frase).\n"
        "- Timestamps no formato MM:SS (ou HH:MM:SS se passar de 1 hora), relativos ao início do vídeo.\n"
        "- Até 8 cortes, ordenados do melhor para o pior. Se nada se encaixar, devolva lista vazia.\n"
        "- title: título curto e chamativo em português. reason: por que o trecho se encaixa. "
        "score: nota de 1 a 10."
    )
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=[f, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=list[Clip],
                media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
                http_options=types.HttpOptions(
                    timeout=300_000,
                    retry_options=types.HttpRetryOptions(attempts=6, initial_delay=5, max_delay=60),
                ),
            ),
        )
    finally:
        client.files.delete(name=f.name)
    return resp.parsed or []


def cut(src: Path, out: Path, start: float, end: float):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start}", "-i", str(src), "-t", f"{end - start}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-movflags", "+faststart", str(out)],
        check=True,
    )


def run_job(job_id: str, category: str, url: str | None, upload: Path | None):
    job = jobs[job_id]
    dest = JOBS_DIR / job_id
    try:
        if url:
            job["status"] = "baixando o vídeo"
            video = download(url, dest)
        else:
            video = upload
        job["status"] = f"analisando com {MODEL}"
        clips = analyze(video, category)
        job["status"] = "cortando"
        results = []
        for i, c in enumerate(clips, 1):
            start, end = to_seconds(c.start), to_seconds(c.end)
            if end <= start:
                continue
            name = f"corte_{i:02d}.mp4"
            cut(video, dest / name, start, end)
            results.append({**c.model_dump(), "file": f"/jobs/{job_id}/{name}"})
        job["clips"] = results
        job["status"] = "pronto"
    except Exception as e:
        job["status"] = "erro"
        job["error"] = str(e)


app = FastAPI()
app.mount("/jobs", StaticFiles(directory=JOBS_DIR), name="jobs")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/categories")
def categories():
    return list(CATEGORIES)


@app.post("/api/jobs")
def create_job(category: str = Form(...), url: str = Form(""), file: UploadFile | None = None):
    if category not in CATEGORIES:
        raise HTTPException(400, "categoria inválida")
    if not url and not (file and file.filename):
        raise HTTPException(400, "envie um arquivo ou um link")
    job_id = uuid.uuid4().hex[:12]
    dest = JOBS_DIR / job_id
    dest.mkdir()
    upload = None
    if not url:
        upload = dest / f"source{Path(file.filename).suffix or '.mp4'}"
        with upload.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    jobs[job_id] = {"status": "na fila", "clips": [], "error": None}
    threading.Thread(target=run_job, args=(job_id, category, url or None, upload), daemon=True).start()
    return {"id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404)
    return jobs[job_id]
