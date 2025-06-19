# db 目录详细说明

本目录包含与数据库相关的所有 Python 脚本，主要负责 ORM 模型定义、数据库工具函数等。下述为每个文件的详细函数和类说明。

---

## orm_models.py
- **功能**：定义所有数据库表的 ORM 模型。
- **主要类**：
  - `User`：用户表，字段有 user_id, vip_level, vip_date, vip_expiry_date, points, last_checkin。
  - `File`：文件表，字段有 file_id, file_path, tg_file_id, file_size。
  - `SentFile`：已发送文件记录表，字段有 user_id, file_id, date, source。
  - `FileFeedback`：文件反馈表，字段有 user_id, file_id, feedback, date。
  - `UploadedDocument`：用户上传文档表，字段有 id, user_id, file_name, file_size, tg_file_id, upload_time, status, approved_by, is_downloaded, download_path。
  - `LicenseCode`：兑换码表，字段有 id, code, user_id, points, redeemed_at, license_info。

---

## orm_utils.py
- **功能**：数据库工具函数，负责数据库连接、Session 管理、初始化等。
- **主要内容**：
  - `get_engine()`：根据配置返回 SQLAlchemy Engine。
  - `engine`：数据库引擎实例。
  - `SessionLocal`：Session 工厂。
  - `init_db()`：初始化数据库，自动建表。

---

## db_utils.py
- **功能**：数据库操作工具函数，通常为业务层提供便捷操作接口。
- **主要函数**：
  - `get_or_create_file(file_path, tg_file_id=None)`：查找或新建文件记录，返回 file_id。
  - `ensure_user(user_id)`：确保用户存在。
  - `set_user_vip_level(user_id, vip_level, days=30)`：设置用户 VIP 等级和有效期。
  - `get_user_vip_level(user_id)`：获取用户 VIP 等级和每日限额。
  - `get_sent_file_ids(user_id)`：获取用户已发送文件数量。
  - `mark_file_sent(user_id, file_id, source='file')`：记录文件已发送。
  - `get_today_sent_count(user_id)`：获取用户今日已发送文件数量。
  - `record_feedback(user_id, file_id, feedback)`：记录用户对文件的反馈。

---

如需进一步了解每个函数和类的实现细节，请查阅源码注释。
