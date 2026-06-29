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
- [ ] В stdout есть строка `Solution started`

Замените чеклист под своё решение, но оставьте **конкретные и проверяемые** критерии.

## Остановка и очистка

```bash
docker compose down --rmi local -v
```
