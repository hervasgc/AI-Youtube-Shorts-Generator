# PROJECT_CONTEXT.md

> Documento de contexto e histórico deste projeto. Escrito para servir dois propósitos:
> 1. Contexto para quem (ou qual IA) continuar o desenvolvimento deste repositório.
> 2. Playbook de referência para futuros projetos a serem colocados em produção no GCP dentro da organização Media.Monks — os padrões de segurança e as armadilhas encontradas aqui tendem a se repetir em qualquer novo deploy.
>
> Última atualização: 2026-09-09.

---

## 1. O que é este projeto

**AI YouTube Shorts Generator** — fork pessoal (`hervasgc/AI-Youtube-Shorts-Generator`) do projeto open-source [SamurAIGPT/AI-Youtube-Shorts-Generator](https://github.com/SamurAIGPT/AI-Youtube-Shorts-Generator).

**Objetivo:** dado um vídeo longo do YouTube (ou um arquivo local), gerar automaticamente N cortes verticais (9:16) "virais" — os melhores momentos do vídeo, cada um com título, hook de abertura, score e justificativa — prontos para TikTok/Reels/Shorts. É uma alternativa self-hosted a ferramentas como Opus Clip/Vidyo.ai/Klap.

### Como funciona (pipeline)

1. **Download** do vídeo de origem.
2. **Transcrição** com timestamps (Whisper).
3. **Classificação do conteúdo** (podcast, entrevista, tutorial, vlog...) por um LLM, para ajustar o prompt.
4. **Chunking** de vídeos longos (>30min) em janelas de 20min com overlap.
5. **Ranking de highlights**: um LLM varre a transcrição usando um framework de "viralidade" (hook, pico emocional, opinião polêmica, revelação, conflito, quotable, pico narrativo, valor prático) e retorna candidatos com score 0-100.
6. **Dedupe** de candidatos sobrepostos (>50% overlap → mantém o de maior score).
7. **Top-N** são selecionados.
8. **Auto-crop vertical** de cada highlight.

### Dois modos de execução (`--mode` / seletor na UI)

| Etapa | `api` (padrão do projeto original) | `local` (o que rodamos e colocamos em produção) |
|---|---|---|
| Download | MuAPI `/youtube-download` | `yt-dlp` |
| Transcrição | MuAPI `/openai-whisper` | `faster-whisper` (CPU) |
| LLM de highlights | MuAPI `gpt-5-mini` | OpenAI ou Gemini (`LLM_PROVIDER`) |
| Crop vertical | MuAPI `/autocrop` | `ffmpeg` + OpenCV (detecção de rosto) |
| Dependência externa | `MUAPI_API_KEY` (pago) | `OPENAI_API_KEY` ou `GEMINI_API_KEY` + `ffmpeg` |

**Decisão deste projeto: só `--mode local` foi levado para produção.** Não depende da MuAPI; roda inteiramente no próprio container.

### Estrutura do código

```
app.py                          UI Streamlit (sidebar de config + geração)
main.py                         CLI: python main.py <url> --mode local
shorts_generator/
  config.py                    todas as env vars do projeto (ver seção 4)
  pipeline.py                  dispatcher api ↔ local (generate_shorts())
  highlights.py                framework de viralidade (prompt, chunking, dedupe) — compartilhado pelos 2 modos
  muapi.py / downloader.py / transcriber.py / clipper.py   backend do modo api
  local/
    downloader.py               yt-dlp (+ suporte a cookies, ver seção 3.3)
    transcriber.py               faster-whisper
    llm.py                       seleciona OpenAI ou Gemini
    clipper.py                    ffmpeg cut + OpenCV crop vertical + mux final
    storage.py                    upload opcional pro GCS + signed URL (só ativa se GCS_OUTPUT_BUCKET setado)
```

### Rodando localmente

```bash
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-local.txt
streamlit run app.py
```
Precisa de `ffmpeg` no PATH (`brew install ffmpeg`) e de `GEMINI_API_KEY` ou `OPENAI_API_KEY` no `.env` (ver `.env.example`).

---

## 2. Histórico desta sessão de trabalho

Ordem cronológica do que foi feito e por quê — útil para entender *decisões*, não só o estado final.

1. **Avaliação inicial e primeira execução local.** O projeto já tinha um `app.py` (Streamlit) não commitado. Rodamos a interface, confirmamos que as dependências do modo local já estavam instaladas na venv.
2. **Achado de segurança:** o `.env.example` (arquivo de exemplo que vai pro git) tinha sido alterado localmente para conter uma **chave real do Gemini** em texto puro, no lugar do placeholder. Revertido antes de qualquer commit. **Ação pendente do usuário:** revogar/rotacionar essa chave no Google AI Studio, já que ela chegou a existir em texto puro no working tree.
3. **Apontamos o remote do git** para o fork pessoal do usuário (`hervasgc/AI-Youtube-Shorts-Generator`) e sincronizamos (pull fast-forward de 13 commits + push do `app.py`/fixes locais).
4. **Bug encontrado e corrigido: vídeo sem imagem no player.** O passo de reframe vertical (`shorts_generator/local/clipper.py`) usava OpenCV `VideoWriter` com fourcc `mp4v` (MPEG-4 Part 2) para escrever os frames recortados, e depois o mux final fazia `-c:v copy` — ou seja, **copiava esse codec incompatível direto pro arquivo final**, em vez de reconverter para H.264. Nenhum navegador decodifica `mp4v` em `<video>`; o áudio (AAC) tocava normalmente, dando a falsa impressão de "só áudio, sem vídeo". Fix: reencodar para `libx264`/`yuv420p` no mux final, com `+faststart`. Confirmado via `ffprobe` e visualmente no navegador.
5. **Deploy no GCP (Cloud Run).** Ver detalhes completos na seção 3. Resumo das decisões tomadas com o usuário:
   - Só modo `local` (sem MuAPI).
   - Acesso **privado** (IAM), nunca `allUsers` — para não deixar estranhos gerando custo de LLM/CPU na conta.
   - CI/CD via GitHub Actions, reaproveitando a service account `github-sentimento-analise@radiant-tide-401723.iam.gserviceaccount.com` já usada por outros serviços do mesmo projeto GCP (em vez de criar SAs novas — decisão do usuário, por conveniência, abrindo mão do "least privilege" que eu tinha proposto inicialmente).
6. **Limitação descoberta em produção: bloqueio anti-bot do YouTube.** `yt-dlp` rodando do IP de datacenter do Cloud Run leva "Sign in to confirm you're not a bot" — isso não acontece rodando do Mac do usuário (IP residencial/corporativo). Mitigação implementada: cookies de sessão do YouTube (exportados do navegador, arquivo scoped só a `youtube.com` — nunca o export "todos os cookies", que continha sessões de dezenas de outros sites e é sensível demais para guardar em qualquer lugar). Os cookies são montados como secret read-only no Cloud Run; o código copia pra um scratch file gravável em `/tmp` antes de usar, porque o `yt-dlp` tenta regravar o cookiejar ao final da execução. **Mesmo assim, a mitigação não é 100% confiável**: funcionou uma vez, falhou de novo poucos minutos depois (o Google parece sinalizar a sessão após uso automatizado detectado). Decisão do usuário: aceitar essa instabilidade por ora, documentada no README.
7. **Limpeza:** processos locais (Streamlit, `gcloud run services proxy`) encerrados a pedido do usuário ao final da sessão.

### Coisas que ficaram para depois (não resolvidas)
- Rotacionar a `GEMINI_API_KEY` que foi exposta em texto puro no `.env.example` (item 2 acima).
- Acesso via a URL real do Cloud Run (hoje só funciona via `gcloud run services proxy`, que exige terminal aberto). Duas opções discutidas e ainda não implementadas:
  - **IAP (Identity-Aware Proxy)** no Cloud Run — login Google normal ao abrir a URL. Requer configurar tela de consentimento OAuth do projeto.
  - Extensão de navegador (ModHeader) injetando `Authorization: Bearer <identity-token>` — mais simples, mas o token expira em ~1h.
- Instabilidade do download de YouTube via `yt-dlp` a partir de IP de datacenter (seção 6 acima) — sem solução definitiva.

---

## 3. Configuração de produção (GCP) — referência exata

### 3.1 Recursos criados

| Recurso | Valor |
|---|---|
| Projeto GCP | `radiant-tide-401723` (org Media.Monks, billing ativo) |
| Região | `southamerica-east1` (mesma região dos outros serviços do projeto) |
| Serviço Cloud Run | `ai-youtube-shorts-generator` |
| URL do serviço | `https://ai-youtube-shorts-generator-zj2e5a77ka-rj.a.run.app` (privada — ver seção 4) |
| Bucket GCS (output) | `gs://radiant-tide-401723-ai-shorts` (privado, uniform bucket-level access) |
| Secret: Gemini key | `ai-shorts-gemini-api-key` |
| Secret: cookies YouTube | `ai-shorts-youtube-cookies` (montado como arquivo, não env var) |
| Service account (deploy + runtime) | `github-sentimento-analise@radiant-tide-401723.iam.gserviceaccount.com` (reaproveitada de outros serviços do projeto) |

### 3.2 Recursos: como foram criados (para recriar/replicar)

```bash
# Bucket privado
gcloud storage buckets create gs://radiant-tide-401723-ai-shorts \
  --project=radiant-tide-401723 --location=southamerica-east1 \
  --uniform-bucket-level-access --public-access-prevention

# Secret com a chave do Gemini
gcloud secrets create ai-shorts-gemini-api-key --project=radiant-tide-401723 \
  --data-file=- --replication-policy=automatic   # valor via stdin, nunca em texto no comando

# Secret com cookies do YouTube (arquivo scoped a youtube.com, NUNCA o export "todos os cookies")
gcloud secrets create ai-shorts-youtube-cookies --project=radiant-tide-401723 \
  --data-file=/caminho/para/www.youtube.com_cookies.txt --replication-policy=automatic

# Permissões na service account compartilhada
gcloud secrets add-iam-policy-binding ai-shorts-gemini-api-key --project=radiant-tide-401723 \
  --member="serviceAccount:github-sentimento-analise@radiant-tide-401723.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding ai-shorts-youtube-cookies --project=radiant-tide-401723 \
  --member="serviceAccount:github-sentimento-analise@radiant-tide-401723.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud iam service-accounts add-iam-policy-binding \
  github-sentimento-analise@radiant-tide-401723.iam.gserviceaccount.com --project=radiant-tide-401723 \
  --member="serviceAccount:github-sentimento-analise@radiant-tide-401723.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"   # necessário pra gerar signed URLs do bucket sem chave privada
```

### 3.3 Deploy (o que o GitHub Actions roda a cada push em `main`)

Ver [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml). Comando equivalente manual:

```bash
gcloud run deploy ai-youtube-shorts-generator \
  --source . --project radiant-tide-401723 --region southamerica-east1 \
  --no-allow-unauthenticated \
  --service-account github-sentimento-analise@radiant-tide-401723.iam.gserviceaccount.com \
  --cpu=4 --memory=8Gi --timeout=3600 --concurrency=1 --min-instances=0 \
  --set-secrets=GEMINI_API_KEY=ai-shorts-gemini-api-key:latest,/secrets/youtube-cookies.txt=ai-shorts-youtube-cookies:latest \
  --set-env-vars=LLM_PROVIDER=gemini,GEMINI_MODEL=gemini-2.5-flash,LOCAL_OUTPUT_DIR=/tmp/output,LOCAL_WHISPER_MODEL=base,LOCAL_WHISPER_DEVICE=cpu,GCS_OUTPUT_BUCKET=radiant-tide-401723-ai-shorts,YOUTUBE_COOKIES_FILE=/secrets/youtube-cookies.txt
```

Autenticação do GitHub Actions: secret de repositório `GCP_SA_KEY` (chave JSON da mesma service account acima), consumido via `google-github-actions/auth@v2`.

### 3.4 Acessando o serviço (privado — sem `allUsers`)

```bash
gcloud run services proxy ai-youtube-shorts-generator \
  --project=radiant-tide-401723 --region=southamerica-east1 --port=8502
# depois abrir http://127.0.0.1:8502
```
Funciona porque quem roda o comando (`gustavo.hervas@monks.com`) já é `roles/owner` do projeto — não foi necessário nenhum binding de IAM adicional para o próprio dono. Ver seção 2 ("coisas que ficaram para depois") para as duas alternativas de acesso via URL direta.

### 3.5 Variáveis de ambiente relevantes (`shorts_generator/config.py`)

| Variável | Uso |
|---|---|
| `LLM_PROVIDER` | `openai` ou `gemini` |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | chave do provedor de LLM escolhido |
| `LOCAL_WHISPER_MODEL` / `LOCAL_WHISPER_DEVICE` | tamanho do modelo whisper / `cpu`/`cuda`/`auto` |
| `LOCAL_OUTPUT_DIR` | onde os mp4s são escritos antes do upload (local: `output/`; Cloud Run: `/tmp/output`, filesystem efêmero) |
| `GCS_OUTPUT_BUCKET` | **opcional** — se setado, os clipes finais são enviados pro bucket e `clip_url` vira uma signed URL em vez de path local. Vazio = comportamento local inalterado |
| `GCS_SIGNED_URL_EXPIRY_SECONDS` | validade da signed URL (padrão 3600s) |
| `YOUTUBE_COOKIES_FILE` | **opcional** — path pro cookies.txt (Netscape format) que o `yt-dlp` usa. Necessário em produção (Cloud Run); não precisa localmente |

---

## 4. Playbook de segurança GCP — Media.Monks (para replicar em novos projetos)

Regras e padrões que emergiram nesta sessão e que devem ser o ponto de partida para **qualquer novo projeto** que este usuário for colocar em produção no GCP, dentro da organização Media.Monks:

1. **Nunca deixar um Cloud Run service público sem necessidade.** Deploy sempre com `--no-allow-unauthenticated` por padrão. Só liberar `allUsers` se houver uma razão de produto explícita (ex: site público) — e mesmo assim, considerar autenticação na camada da aplicação.
2. **Segredos nunca em `.env.example`, nunca em texto plano no repo, nunca em variável de ambiente comum.** Sempre Secret Manager, injetado via `--set-secrets` (env var *ou* arquivo montado, conforme o caso). Chave vista em texto puro (mesmo que não commitada) deve ser tratada como potencialmente comprometida e rotacionada.
3. **Nunca commitar uma chave de service account (`.json`) no repositório.** Vai como secret do GitHub (`GCP_SA_KEY`), configurado manualmente na UI do GitHub pelo usuário — nunca colado no chat/nunca deixado em disco depois de usado.
4. **Least privilege é o ideal, mas este projeto conscientemente abriu mão dele por conveniência**, reaproveitando uma service account de projeto já existente (`github-sentimento-analise`) com roles amplas (`run.admin`, `storage.admin`, `artifactregistry.admin`, `cloudbuild.admin` a nível de projeto). Isso significa que **qualquer repo que use essa SA tem, na prática, acesso amplo ao projeto `radiant-tide-401723` inteiro**. Para um projeto novo com dados mais sensíveis, o correto é criar uma service account dedicada com roles mínimas (só o necessário: `run.admin` OU escopo por serviço, `artifactregistry.writer`, `secretmanager.secretAccessor` só nos secrets daquele projeto, `storage.objectAdmin` só no bucket daquele projeto).
5. **Alterações de política de IAM (`add-iam-policy-binding`, criação de service account, criação de chave) são bloqueadas automaticamente** pelo classificador de permissões do Claude Code neste ambiente — sempre que um agente for configurar um projeto GCP novo, esperar que esses comandos específicos precisem ser rodados manualmente pelo usuário, e ter a lista pronta.
6. **Buckets de output/dados gerados: sempre privados** (`--uniform-bucket-level-access --public-access-prevention`), conteúdo servido via **signed URL** de curta duração, nunca por objeto público. Assinar via `roles/iam.serviceAccountTokenCreator` (a SA assina como ela mesma via `signBlob`), nunca via chave privada baixada dentro do container.
7. **Testar downloads/scraping de terceiros (YouTube, etc.) a partir do IP real de produção antes de assumir que "funciona igual ao local".** IPs de datacenter GCP são frequentemente tratados como tráfego suspeito por serviços como YouTube — algo que nunca aparece rodando do Mac/escritório do desenvolvedor.
8. **Padrão de projeto GCP identificado:** `radiant-tide-401723`, região `southamerica-east1`, com Cloud Run + Cloud Build + Artifact Registry + Secret Manager já habilitados — esse é o projeto "casa" para novos protótipos/demos da organização; confirmar com o usuário se um novo projeto deve ir para esse mesmo projeto GCP ou para um novo.
9. **Antes de qualquer deploy real (custo, IAM, infraestrutura), validar o plano com o usuário** (uso de plan mode) — não criar recursos faturáveis ou alterar permissões sem aprovação explícita do escopo.
