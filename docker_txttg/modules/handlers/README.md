# handlers 目录详细说明

本目录包含所有 Telegram 机器人命令与消息的处理器，按功能拆分为不同文件。下述为每个文件的详细函数说明。

---

## handlers_file.py
- **功能**：处理文件相关命令，如随机获取文件、通过文件ID获取文件等。
- **主要函数**：
  - `send_random_txt(update, context)`：随机发送一个未领取的文件给用户。
  - `getfile(update, context)`：通过 tg_file_id 获取并发送文件。

---

## handlers_help.py
- **功能**：处理 /help 帮助命令，展示机器人所有可用命令和说明。
- **主要函数**：
  - `help_command(update, context)`：发送详细的帮助信息和常用命令说明。

---

## handlers_user.py
- **功能**：处理用户相关命令，如个人统计、文件领取统计、欢迎消息等。
- **主要函数**：
  - `user_stats(update, context)`：展示用户个人统计信息（VIP、积分、领取数等）。
  - `stats(update, context)`：展示用户已领取文件总数。
  - `on_start(update, context)`：处理 /start 命令，发送欢迎信息。

---

## handlers_vip.py
- **功能**：处理管理员设置用户 VIP 相关命令。
- **主要函数**：
  - `setvip_command(update, context)`：管理员设置用户 VIP 等级和有效期。

---

如需进一步了解每个函数的参数、返回值和实现细节，请查阅源码注释。
