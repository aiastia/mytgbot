# 数据库迁移指南

本项目使用 SQLAlchemy ORM 进行数据库管理，支持 SQLite 和 MySQL。使用自动化迁移脚本来处理数据库结构变更，保证数据安全。

## 开发环境使用

1. 直接在本地执行迁移：
```powershell
python db_migrate.py
```

## Docker 环境使用

### 方式一：进入容器执行

1. 进入运行中的容器：
```powershell
docker exec -it docker_txttg-app-1 bash
```

2. 在容器内执行迁移脚本：
```bash
python db_migrate.py
```

### 方式二：使用 Docker Compose 命令（推荐）

直接使用 docker compose run 执行迁移：
```powershell
docker compose run --rm app python db_migrate.py
```

## 添加新字段的流程

1. 在 `orm_models.py` 中添加新字段，例如：
```python
class User(Base):
    __tablename__ = 'users'
    # ...现有字段...
    new_field = Column(String(255))  # 添加新字段
```

2. 执行迁移脚本（根据环境选择上述命令之一）

迁移脚本会：
- 自动检测新增的字段
- 自动添加到数据库
- 保留现有数据
- 支持重复执行

## 注意事项

1. 迁移前建议备份数据库
2. 支持 SQLite 和 MySQL
3. 迁移过程不会删除或修改现有数据
4. 如果使用 MySQL，请确保环境变量正确配置：
   - DB_TYPE=mysql
   - DB_USER=your_username
   - DB_PASS=your_password
   - DB_HOST=your_host
   - DB_NAME=your_database

## 常见问题

1. 如果遇到权限问题，确保容器内有数据库文件的写入权限
2. 如果使用 MySQL，确保数据库连接信息正确
3. 迁移脚本可以重复执行，不会影响已存在的数据

## 技术细节

- 使用 SQLAlchemy ORM 管理数据库模型
- 自动检测模型变更
- 支持 SQLite 和 MySQL 数据库
- 使用安全的字段添加方式
- 保留所有现有数据
