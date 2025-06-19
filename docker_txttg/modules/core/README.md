# core 目录详细说明

本目录包含与业务核心相关的所有 Python 脚本。下述为每个文件的详细函数说明。

---

## bot_tasks.py

### send_file_job(context)
- **功能**：异步任务，向指定用户发送文件（支持 Telegram 文件ID、本地文件等），并记录发送状态。
- **参数**：
  - `context`：Telegram 任务上下文，包含任务数据（chat_id, file_id_or_path, user_id, prep_message_id, source）。
- **返回值**：无（异步函数，直接发送消息）。
- **典型用途**：定时或批量推送文件给用户。

---

## document_handler.py

### handle_document(update, context)
- **功能**：处理用户上传的文档，校验类型、查重、入库，并通知管理员审核。
- **参数**：
  - `update`：Telegram Update 对象。
  - `context`：Telegram Context。
- **返回值**：无（异步函数，直接回复消息）。

### handle_document_callback(update, context)
- **功能**：管理员审核文档（收录、收录并下载、拒绝），并通知用户。
- **参数**：同上。
- **返回值**：无。

### batch_approve_command(update, context)
- **功能**：管理员批量批准所有待审核文档。
- **参数**：同上。
- **返回值**：无。

---

## file_utils.py

### reload_txt_files()
- **功能**：扫描 TXT_ROOT 目录下所有文本文件，入库并记录文件大小。
- **参数**：无。
- **返回值**：`(inserted, skipped)`，分别为新入库和跳过的文件数。

### get_unsent_files(user_id)
- **功能**：获取当前用户未发送过的文件或已上传文档。
- **参数**：`user_id` 用户ID。
- **返回值**：字典，包含文件ID、来源、tg_file_id 或 file_path。

---

## license_handler.py

### query_license(code)
- **功能**：通过 API 查询兑换码状态。
- **参数**：`code` 兑换码。
- **返回值**：字典，API 返回内容。

### activate_license(code)
- **功能**：激活兑换码。
- **参数**：`code` 兑换码。
- **返回值**：字典，API 返回内容。

### redeem_license_code(user_id, code)
- **功能**：兑换积分码，激活后为用户加积分并记录。
- **参数**：`user_id` 用户ID，`code` 兑换码。
- **返回值**：`(bool, str)`，是否成功及提示信息。

### redeem_command(update, context)
- **功能**：处理 /redeem 命令，用户输入兑换码。
- **参数**：同上。
- **返回值**：无。

---

## points_system.py

### get_user_points(user_id)
- **功能**：查询用户积分。
- **参数**：`user_id` 用户ID。
- **返回值**：积分数（int）。

### add_points(user_id, points)
- **功能**：为用户增加积分。
- **参数**：`user_id` 用户ID，`points` 增加的积分。
- **返回值**：最新积分数。

### can_checkin(user_id)
- **功能**：判断用户今日是否可签到。
- **参数**：`user_id` 用户ID。
- **返回值**：布尔值。

### update_last_checkin(user_id)
- **功能**：更新用户最后签到日期。
- **参数**：`user_id` 用户ID。
- **返回值**：无。

### calculate_points_for_days(level, days, current_level=0)
- **功能**：根据套餐配置计算指定等级和天数的积分价值。
- **参数**：VIP等级、天数、当前等级。
- **返回值**：所需积分。

### checkin_command(update, context)
- **功能**：处理 /checkin 签到命令。
- **参数**：同上。
- **返回值**：无。

### points_command(update, context)
- **功能**：处理 /points 查询积分命令。
- **参数**：同上。
- **返回值**：无。

### exchange_callback(update, context)
- **功能**：处理积分兑换 VIP 的回调。
- **参数**：同上。
- **返回值**：无。

### cancel_callback(update, context)
- **功能**：处理取消兑换操作。
- **参数**：同上。
- **返回值**：无。

### upgrade_vip_level(user_id, target_level, target_days)
- **功能**：升级或续费 VIP。
- **参数**：用户ID、目标等级、天数。
- **返回值**：`(bool, str)`，是否成功及提示。

### is_vip_active(user_id)
- **功能**：判断用户 VIP 是否有效。
- **参数**：用户ID。
- **返回值**：布尔值。

### get_vip_info(user_id)
- **功能**：获取用户 VIP 信息。
- **参数**：用户ID。
- **返回值**：字典，包含等级、有效性、起止日期。

### get_package_points(level, days)
- **功能**：获取指定等级和天数的套餐积分。
- **参数**：VIP等级、天数。
- **返回值**：积分数。

---

## search_file.py

### split_message(text, max_length=MAX_TG_MSG_LEN)
- **功能**：分割长消息为多段。
- **参数**：文本、最大长度。
- **返回值**：字符串列表。

### set_bot_username(username)
- **功能**：设置全局机器人用户名。
- **参数**：用户名。
- **返回值**：无。

### get_user_vip_level(user_id)
- **功能**：获取用户 VIP 等级。
- **参数**：用户ID。
- **返回值**：VIP 等级（int）。

### get_file_by_id(file_id)
- **功能**：通过ID查找文件。
- **参数**：文件ID。
- **返回值**：`(tg_file_id, file_path)` 或 None。

### get_uploaded_file_by_id(file_id)
- **功能**：通过ID查找已上传文档。
- **参数**：文件ID。
- **返回值**：`(tg_file_id, download_path)` 或 None。

### search_files_by_name(keyword)
- **功能**：按文件名模糊搜索文件。
- **参数**：关键词。
- **返回值**：文件元组列表。

### search_uploaded_files_by_name(keyword)
- **功能**：按文件名模糊搜索已上传文档。
- **参数**：关键词。
- **返回值**：文档元组列表。

### update_file_tg_id(file_id, tg_file_id)
- **功能**：更新文件的 tg_file_id。
- **参数**：文件ID、tg_file_id。
- **返回值**：无。

### update_uploaded_file_tg_id(file_id, tg_file_id)
- **功能**：更新已上传文档的 tg_file_id。
- **参数**：文件ID、tg_file_id。
- **返回值**：无。

### build_search_keyboard(results, page, keyword)
- **功能**：构建文件搜索结果的分页键盘。
- **参数**：结果列表、页码、关键词。
- **返回值**：InlineKeyboardMarkup。

### build_uploaded_search_keyboard(results, page, keyword)
- **功能**：构建已上传文档搜索结果的分页键盘。
- **参数**：同上。
- **返回值**：InlineKeyboardMarkup。

### search_command(update, context)
- **功能**：处理 /s 文件搜索命令。
- **参数**：同上。
- **返回值**：无。

### search_callback(update, context)
- **功能**：处理搜索分页和文件获取回调。
- **参数**：同上。
- **返回值**：无。

### ss_command(update, context)
- **功能**：处理 /ss 文件超级搜索命令。
- **参数**：同上。
- **返回值**：无。

### ss_callback(update, context)
- **功能**：处理超级搜索分页回调。
- **参数**：同上。
- **返回值**：无。

### send_ss_page(update, context, keyword, page=0, edit=False)
- **功能**：分页展示超级搜索结果。
- **参数**：update, context, keyword, page, edit。
- **返回值**：无。

---

如需进一步了解每个函数的实现细节，请查阅源码注释。
