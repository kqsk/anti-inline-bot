# quickstart для Aiogram

import logging
import os
from pathlib import Path
from dotenv import load_dotenv
import configparser

from aiogram import Bot, Dispatcher, executor, types, utils
import aiogram

BASE_DIR = Path(__file__).resolve().parent
START = (BASE_DIR / "res" / "start").read_text(encoding="utf-8")

# Load environment variables from .env files (repo root first, then src/)
PROJECT_ROOT = BASE_DIR.parent
load_dotenv(str(PROJECT_ROOT / ".env"))
load_dotenv(str(BASE_DIR / ".env"))

# Token resolution: env vars first, then src/secret_data/config.ini
token = os.getenv("TELEGRAM_API") or os.getenv("BOT_TOKEN")
if not token:
    cfg_path = BASE_DIR / "secret_data" / "config.ini"
    if cfg_path.exists():
        parser = configparser.ConfigParser()
        parser.read(cfg_path, encoding="utf-8")
        token = parser.get("credentials", "telegram-api", fallback=None)
if not token:
    raise RuntimeError("Telegram bot token not provided. Create .env with TELEGRAM_API=... (or set BOT_TOKEN), or put it into src/secret_data/config.ini under [credentials] telegram-api=")

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s', datefmt='%y-%m-%d %H:%M')
bot = Bot(token=token)
dp = Dispatcher(bot)

# ================= File-based settings storage =================
SETTINGS_DIR = BASE_DIR / "settings"


def _ensure_chat_dir(chat_id: int) -> Path:
    chat_dir = SETTINGS_DIR / str(chat_id)
    chat_dir.mkdir(parents=True, exist_ok=True)
    return chat_dir


def _read_text(path: Path, default: str) -> str:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return default


def _write_text(path: Path, value: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    except Exception:
        pass


def _list_path(chat_id: int, list_name: str) -> Path:
    chat_dir = _ensure_chat_dir(chat_id)
    filename = f"{list_name}.txt"
    return chat_dir / filename


def _read_list(chat_id: int, list_name: str) -> set:
    path = _list_path(chat_id, list_name)
    if not path.exists():
        return set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return set(item.strip().lower() for item in lines if item.strip())
    except Exception:
        return set()


def _write_list(chat_id: int, list_name: str, items: set) -> None:
    path = _list_path(chat_id, list_name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(sorted(items)) + ("\n" if items else ""), encoding="utf-8")
    except Exception:
        pass


def set_add(chat_id: int, list_name: str, username: str) -> None:
    items = _read_list(chat_id, list_name)
    items.add(username.strip().lower())
    _write_list(chat_id, list_name, items)


def set_remove(chat_id: int, list_name: str, username: str) -> None:
    items = _read_list(chat_id, list_name)
    items.discard(username.strip().lower())
    _write_list(chat_id, list_name, items)


def set_members(chat_id: int, list_name: str) -> set:
    return _read_list(chat_id, list_name)


def set_contains(chat_id: int, list_name: str, username: str) -> bool:
    if not username:
        return False
    return username.strip().lower() in _read_list(chat_id, list_name)


NAME = "anti-inline-bot"

async def get_chat_dict(chat_id: int) -> dict:
    chat_dir = _ensure_chat_dir(chat_id)
    # defaults
    policy = _read_text(chat_dir / "policy.txt", "all")
    deletion = _read_text(chat_dir / "deletion.txt", "1")
    q = _read_text(chat_dir / "q.txt", "1")

    # persist defaults if files did not exist
    _write_text(chat_dir / "policy.txt", policy)
    _write_text(chat_dir / "deletion.txt", deletion)
    _write_text(chat_dir / "q.txt", q)

    # keep bytes API for minimal code changes
    return {b'deletion': deletion.encode(), b'q': q.encode(), b'policy': policy.encode()}





def save_chat_dict(chat_id: int, chat_dict: dict) -> None:
    chat_dir = _ensure_chat_dir(chat_id)
    policy = (chat_dict.get(b'policy', b'all') or b'all').decode()
    deletion = (chat_dict.get(b'deletion', b'1') or b'1').decode()
    q = (chat_dict.get(b'q', b'1') or b'1').decode()
    _write_text(chat_dir / "policy.txt", policy)
    _write_text(chat_dir / "deletion.txt", deletion)
    _write_text(chat_dir / "q.txt", q)


@dp.my_chat_member_handler()
async def send(event: types.ChatMemberUpdated):
    if hasattr(event, 'new_chat_member') and event.new_chat_member.status == "member":
        await event.bot.send_message(event.chat.id, START, parse_mode="html")
        await get_chat_dict(event.chat.id)


@dp.message_handler(commands=['start', 'help'])
async def send(message: types.Message):
    await message.answer(START, parse_mode="html")


@dp.message_handler(commands=['toggle'])
async def send(message: types.Message):
    if message.chat.type == types.ChatType.PRIVATE:
        await message.answer("Ошибка, вы не можете изменить эту настройку в личном чате")
    else:
        member = await message.chat.get_member(message.from_user.id)
        if (hasattr(member, 'status') and member.status != "member"):
            chat_dict = await get_chat_dict(message.chat.id)
            to_set = b'0' if chat_dict[b'deletion'] == b'1' else b'1'
            chat_dict[b'deletion'] = to_set
            save_chat_dict(message.chat.id, chat_dict)
            await message.answer(f"Теперь я <b>{'буду' if to_set == b'1' else 'не буду'}</b> удалять сообщения от инлайн-ботов", parse_mode="html")
        else:
            try:
                await message.delete()
            except:
                pass

@dp.message_handler(commands=['q'])
async def send(message: types.Message):
    if message.chat.type == types.ChatType.PRIVATE:
        await message.answer("Ошибка, вы не можете изменить эту настройку в личном чате")
    else:
        member = await message.chat.get_member(message.from_user.id)
        if (hasattr(member, 'status') and member.status != "member"):
            chat_dict = await get_chat_dict(message.chat.id)
            to_set = b'0' if chat_dict[b'q'] == b'1' else b'1'
            chat_dict[b'q'] = to_set
            save_chat_dict(message.chat.id, chat_dict)
            await message.answer(f"Теперь я <b>{'буду' if to_set == b'1' else 'не буду'}</b> скрывать предупреждения", parse_mode="html")
        else:
            try:
                await message.delete()
            except:
                pass


# ================= Admin helpers and commands for policies and lists =================

def _normalize_username(raw: str) -> str:
    if not raw:
        return ''
    raw = raw.strip()
    if raw.startswith('@'):
        raw = raw[1:]
    return raw.lower()


async def _ensure_group_admin(message: types.Message) -> bool:
    logging.info(f"Checking admin rights for user {message.from_user.id} in chat {message.chat.id}")
    if message.chat.type == types.ChatType.PRIVATE:
        await message.answer("Ошибка, вы не можете изменить эту настройку в личном чате")
        return False
    member = await message.chat.get_member(message.from_user.id)
    logging.info(f"Member object type: {type(member)}, status: {getattr(member, 'status', 'NO STATUS')}")
    if (hasattr(member, 'status') and member.status != "member"):
        logging.info(f"User is admin (status: {member.status})")
        return True
    logging.info(f"User is NOT admin")
    try:
        await message.delete()
    except:
        pass
    return False


@dp.message_handler(commands=['mode'])
async def set_mode(message: types.Message):
    logging.info(f"Received /mode command from user {message.from_user.id}")
    if not await _ensure_group_admin(message):
        logging.info("Admin check failed for /mode")
        return
    chat_dict = await get_chat_dict(message.chat.id)
    # Extract arguments from message text
    args = ''
    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            args = parts[1].strip().lower()

    logging.info(f"Mode command args: '{args}'")
    if args in ('all', 'blacklist', 'whitelist'):
        chat_dict[b'policy'] = args.encode()
        save_chat_dict(message.chat.id, chat_dict)
        mode_names = {'all': 'все боты', 'blacklist': 'чёрный список', 'whitelist': 'белый список'}
        await message.answer(f"Режим установлен: <b>{mode_names.get(args, args)}</b>.", parse_mode="html")
    else:
        current = chat_dict.get(b'policy', b'all').decode()
        mode_names = {'all': 'все боты', 'blacklist': 'чёрный список', 'whitelist': 'белый список'}
        await message.answer(
            "Использование: /mode all|blacklist|whitelist\n"
            f"Текущий режим: <b>{mode_names.get(current, current)}</b>", parse_mode="html")


@dp.message_handler(commands=['blacklist_add', 'blacklist_remove', 'blacklist_list'])
async def manage_blacklist(message: types.Message):
    logging.info(f"Received blacklist command from user {message.from_user.id}")
    if not await _ensure_group_admin(message):
        logging.info("Admin check failed for blacklist command")
        return
    # Extract command and arguments from message text
    cmd = ''
    args = ''
    if message.text:
        parts = message.text.split(maxsplit=1)
        if parts:
            cmd = parts[0].lstrip('/').lower()
        if len(parts) > 1:
            args = parts[1].strip()

    logging.info(f"Blacklist command: {cmd}, args: '{args}'")
    key_name = "blacklist"

    if cmd == 'blacklist_add':
        username = _normalize_username(args)
        if not username:
            await message.answer("Использование: /blacklist_add <имя_бота>")
            return
        set_add(message.chat.id, key_name, username)
        await message.answer(f"Бот @{username} добавлен в чёрный список.")
    elif cmd == 'blacklist_remove':
        username = _normalize_username(args)
        if not username:
            await message.answer("Использование: /blacklist_remove <имя_бота>")
            return
        set_remove(message.chat.id, key_name, username)
        await message.answer(f"Бот @{username} удалён из чёрного списка.")
    else:  # blacklist_list
        members = sorted(set_members(message.chat.id, key_name))
        if not members:
            await message.answer("Чёрный список пуст.")
        else:
            await message.answer("Чёрный список:\n" + "\n".join(f"@{m}" for m in members))


@dp.message_handler(commands=['whitelist_add', 'whitelist_remove', 'whitelist_list'])
async def manage_whitelist(message: types.Message):
    logging.info(f"Received whitelist command from user {message.from_user.id}")
    if not await _ensure_group_admin(message):
        logging.info("Admin check failed for whitelist command")
        return
    # Extract command and arguments from message text
    cmd = ''
    args = ''
    if message.text:
        parts = message.text.split(maxsplit=1)
        if parts:
            cmd = parts[0].lstrip('/').lower()
        if len(parts) > 1:
            args = parts[1].strip()

    logging.info(f"Whitelist command: {cmd}, args: '{args}'")
    key_name = "whitelist"

    if cmd == 'whitelist_add':
        username = _normalize_username(args)
        if not username:
            await message.answer("Использование: /whitelist_add <имя_бота>")
            return
        set_add(message.chat.id, key_name, username)
        await message.answer(f"Бот @{username} добавлен в белый список.")
    elif cmd == 'whitelist_remove':
        username = _normalize_username(args)
        if not username:
            await message.answer("Использование: /whitelist_remove <имя_бота>")
            return
        set_remove(message.chat.id, key_name, username)
        await message.answer(f"Бот @{username} удалён из белого списка.")
    else:  # whitelist_list
        members = sorted(set_members(message.chat.id, key_name))
        if not members:
            await message.answer("Белый список пуст.")
        else:
            await message.answer("Белый список:\n" + "\n".join(f"@{m}" for m in members))


# ================= Catch-all handler for inline bot messages (MUST BE LAST) =================
@dp.message_handler(content_types=types.ContentType.ANY)
async def handle_inline_bots(message: types.Message):
    chat_dict = await get_chat_dict(message.chat.id)
    logging.debug(f"Processing message: {message}")
    via_bot_user = getattr(message, 'via_bot', None)
    if chat_dict[b'deletion'] == b'1' and via_bot_user:
        policy = chat_dict.get(b'policy', b'all').decode()
        bot_username = (via_bot_user.username or '').lower()

        should_delete = False
        if policy == 'all':
            should_delete = True
        elif policy == 'blacklist':
            if bot_username:
                should_delete = bool(set_contains(message.chat.id, "blacklist", bot_username))
        elif policy == 'whitelist':
            if bot_username:
                should_delete = not bool(set_contains(message.chat.id, "whitelist", bot_username))

        if should_delete:
            try:
                await message.delete()
            except:
                pass
            if chat_dict[b'q'] == b'0':
                if policy == 'all':
                    text = f"<b>Предупреждение</b>, {message.from_user.get_mention(as_html=True)}, инлайн-боты запрещены в этом чате!"
                elif policy == 'blacklist':
                    text = f"<b>Предупреждение</b>, {message.from_user.get_mention(as_html=True)}, этот инлайн-бот заблокирован здесь!"
                else:
                    text = f"<b>Предупреждение</b>, {message.from_user.get_mention(as_html=True)}, разрешены только инлайн-боты из белого списка!"
                await message.answer(text, parse_mode="html")


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
