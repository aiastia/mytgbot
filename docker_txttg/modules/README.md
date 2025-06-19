# 业务功能模块

所有功能模块都放在本目录下，便于统一管理和维护。

# modules 目录详细说明

本目录包含了项目的主要功能模块，按功能分为 config、core、db、handlers 等子目录。下述为各子目录及其主要内容的详细说明。

---

## config
- **功能**：配置管理，集中存放所有环境变量、常量、路径等配置项。
- **主要文件**：
  - `config.py`：加载环境变量，定义全局常量（如 TOKEN、ADMIN_USER_ID、TXT_ROOT、ALLOWED_EXTENSIONS、数据库配置等）。

---

## core
- **功能**：业务核心逻辑，包括文件检索、文档处理、积分系统、机器人任务等。
- **主要文件**：
  - `bot_tasks.py`：机器人异步任务（如定时/批量发送文件）。
  - `document_handler.py`：文档上传、审核、批量处理。
  - `file_utils.py`：文件扫描、未发送文件筛选等工具。
  - `license_handler.py`：兑换码、授权、API 相关。
  - `points_system.py`：积分、VIP、签到、兑换等。
  - `search_file.py`：文件/文档检索、分页、回调、消息分割等。

---

## db
- **功能**：数据库相关，负责 ORM 模型定义、数据库工具函数、迁移等。
- **主要文件**：
  - `base.py`：SQLAlchemy Base 类。
  - `migrations.py`：数据库迁移脚本。
  - `models.py`/`orm_models.py`：ORM 数据模型。
  - `orm_utils.py`：数据库连接、Session 管理、通用操作。
  - `db_utils.py`：数据库操作工具函数。

---

## handlers
- **功能**：Telegram 机器人命令与消息处理器，按功能拆分。
- **主要文件**：
  - `handlers_file.py`：文件相关命令处理。
  - `handlers_help.py`：帮助命令处理。
  - `handlers_user.py`：用户相关命令处理。
  - `handlers_vip.py`：VIP 相关命令处理。

---

如需了解每个子目录下的详细函数和类说明，请查阅对应子目录下的 README.md 或源码注释。
