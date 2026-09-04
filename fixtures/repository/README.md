# Fixture repository

Минимальный безопасный вход для процесса `repository-change`. Он не содержит
credentials, внешних зависимостей и сетевых тестов. M1 будет создавать из этой
директории immutable snapshot и отдельный writable workspace.

Проверка:

```bash
cd fixtures/repository/project
python3 -m unittest -v
```

