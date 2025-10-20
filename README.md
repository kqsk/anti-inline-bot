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

# Instalation
- install requirements
- create bot via BotFather
- put token in src/secret_data/config.ini
- start redis on 10001 port
- start main.py with python
- enjoy


# Telegram
You can find working one [here](https://t.me/anti_inline_bot)