# Alembic 数据库迁移

```bash
# 生成迁移
alembic revision --autogenerate -m "init"

# 升级
alembic upgrade head

# 回滚
alembic downgrade -1
```
