# Cortes IA

Projeto simples que usa IA para gerar cortes de vídeos de diferentes fontes. Você manda um link (YouTube, X, Facebook, Reddit, Instagram, TikTok e outros sites suportados pelo `yt-dlp`) ou faz upload de um arquivo, escolhe uma categoria, e o Gemini assiste ao vídeo inteiro (imagem e áudio) e aponta os melhores trechos. O `ffmpeg` corta cada trecho e os cortes ficam disponíveis para assistir e baixar no navegador.

Inspirado no [bradautomates/claude-video](https://github.com/bradautomates/claude-video), que foi a base da ideia deste projeto. Vale conferir o repositório original.

## Como funciona

1. **Entrada:** link (baixado com `yt-dlp`, até 720p) ou upload de arquivo.
2. **Análise:** o vídeo é enviado ao Gemini, que devolve até 8 cortes de 15 a 90 segundos com título, motivo e nota de 1 a 10.
3. **Corte:** o `ffmpeg` gera um `.mp4` para cada trecho em `jobs/<id>/`.

Categorias disponíveis: humor, tecnologia, curiosidades, educação, polêmica, emocionante, esportes e games.

## Requisitos

- Python 3.10+
- `ffmpeg` instalado no sistema
- Uma chave da API do Gemini

## Como rodar

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# preencha GEMINI_API_KEY no .env (GEMINI_MODEL é opcional)

uvicorn app:app --reload
```

Depois é só abrir http://localhost:8000.

## Estrutura

- `app.py`: backend FastAPI (download, análise com Gemini, corte com ffmpeg e API de jobs)
- `static/index.html`: interface web
- `requirements.txt`: dependências Python
- `jobs/`: vídeos e cortes gerados (ignorado pelo git)

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE).
