# Anti Inline Bot
Telegram bot for deleting messages sent via inline bots in groups. 

Commands(only for admins):
/start - show this text
/toggle - toggle deletion messages via inline bots
/q - toggle showing warning, when message sended via inline bot

Modes and lists:
- /mode all|blacklist|whitelist - set policy for handling inline bots
  - all: delete all messages sent via inline bots (default)
  - blacklist: delete messages only from bots listed in blacklist
  - whitelist: allow only bots listed in whitelist, delete the rest
- /blacklist_add <bot_username>
- /blacklist_remove <bot_username>
- /blacklist_list
- /whitelist_add <bot_username>
- /whitelist_remove <bot_username>
- /whitelist_list

# Installation

## Local Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create bot via BotFather and get token

3. Configure token (choose one method):
   - Create `.env` file in project root:
     ```
     TELEGRAM_API=your_token_here
     ```
   - Or put token in `src/secret_data/config.ini`:
     ```ini
     [credentials]
     telegram-api=your_token_here
     ```

4. Run the bot:
   ```bash
   python -m src.main
   ```

## Deploy on Railway

1. Create new project on Railway
2. Connect your repository
3. Set environment variable: `TELEGRAM_API` or `BOT_TOKEN` with your bot token
4. Railway will automatically use `Procfile` or `railway.toml` to start the bot

## Storage
- Settings are stored in `src/settings/<chat_id>/` directory
- Each chat has separate files: `policy.txt`, `deletion.txt`, `q.txt`, `blacklist.txt`, `whitelist.txt`
- No Redis or external database required


# Telegram
You can find working one [here](https://t.me/anti_inline_bot)