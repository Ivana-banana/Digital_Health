# Развёртывание для агента-оценщика

> Этот файл — **только для агента-оценщика**. Все шаги должны быть воспроизводимыми без ручных действий.

## Предусловия

- Docker Engine 24+
- Docker Compose v2 (`docker compose`)

## Сборка

```bash
docker compose build
```

## Запуск

```bash
docker compose run --rm app
```

## Проверки

Повторный запуск для проверки воспроизводимости:

```bash
docker compose run --rm app
```

## Критерии «всё работает»

- [ ] `docker compose build` завершается без ошибок
- [ ] `docker compose run --rm app` завершается с кодом `0`
- [ ] В stdout есть строка `Solution started` и ход анализа (retrieve → screen → extract → meta → report)
- [ ] Отчёт содержит уровень доказательности (`strength`), направление эффекта и провенанс ссылок

## Остановка и очистка

```bash
docker compose down --rmi local -v
```

---

## Демо-UI (Streamlit) — опционально

Чат врача со стримингом прогресса и human-in-the-loop чекпойнтами (уточнение PICO,
scoping этап-1 → этап-2). Офлайн-режим (StubLLM + замороженный корпус) работает без ключей.

```bash
docker compose up ui            # → http://localhost:8501
```

Образ UI (`Dockerfile.ui`) отделён от судья-образа, чтобы тот оставался лёгким.

## Деплой в Yandex Cloud (генерация по AI Studio API — GPU не нужен)

**🟢 Развёрнуто (Compute VM):** http://89.169.147.169:8501 — health `/_stcore/health` → 200.
Инстанс `ai-v-massy-ui`, зона `ru-central1-a`, 2 vCPU / 4 GB, Ubuntu 22.04, публичный IP.
Как поднято: `yc compute instance create` → на VM `curl -fsSL https://get.docker.com | sudo sh`
→ доставка кода `git archive | scp` → `.env` со секретами → `docker compose up -d --build ui`
(порт 8501 наружу, 8080 внутри). Порт 8501 в дефолтной security-group открыт.

UI — это обычный веб-сервис; инференс идёт по AI Studio OpenAI-совместимому API,
поэтому GPU для демо не требуется (plan §12).

> **Важно:** Streamlit держит постоянный WebSocket (`/_stcore/stream`), поэтому рабочий
> путь — **Compute VM**, а не Serverless Container. Варианты ниже:

- **Serverless Container:** собрать образ `Dockerfile.ui`, запушить в Container Registry,
  создать контейнер (порт `8501`), выдать публичный endpoint.

  ```bash
  yc container registry create --name ai-v-massy || true
  REG=$(yc container registry get --name ai-v-massy --format json | jq -r .id)
  docker build -f Dockerfile.ui -t cr.yandex/$REG/ui:latest .
  docker push cr.yandex/$REG/ui:latest
  yc serverless container create --name ai-v-massy-ui
  yc serverless container revision deploy \
      --container-name ai-v-massy-ui \
      --image cr.yandex/$REG/ui:latest \
      --cores 2 --memory 2GB --concurrency 4 \
      --execution-timeout 300s \
      --environment YANDEX_API_KEY=$YANDEX_API_KEY,YANDEX_FOLDER_ID=$YANDEX_FOLDER_ID,OPENAI_BASE_URL=https://ai.api.cloud.yandex.net/v1,NCBI_API_KEY=$NCBI_API_KEY
  ```

- **Compute VM:** `docker compose up -d ui` на ВМ с открытым портом `8501`.

**Секреты** (live-режим, мед-данные): задать в окружении контейнера, не в образе —
`YANDEX_API_KEY`, `YANDEX_FOLDER_ID`, `OPENAI_BASE_URL=https://ai.api.cloud.yandex.net/v1`
(шаблон — `config/.env.example`). Опционально `NCBI_API_KEY` для 10 rps PubMed (без ключа
адаптер уходит в лимит 3 rps NCBI — на демо-нагрузке возможен транзиентный HTTP 429; на
день питча ключ **необходим**). Логирование запросов AI Studio — **выключить** (plan §5, §9).

## Live smoke после деплоя

```bash
curl -f https://<endpoint>/_stcore/health          # → 200 OK
curl -f https://<endpoint>/                         # → 200 OK, HTML Streamlit
# в UI: переключатель «Живые данные» → гипотеза BRAF+MEK → отчёт HR ~0.70 ≡ Cochrane
```

## Frozen-eval (детерминированный quality-gate)

```bash
make eval                       # hallucination-rate=0, воспроизводимость пула — exit 0/1
```
