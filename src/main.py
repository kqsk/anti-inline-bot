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

# Admin IDs — comma-separated list of Telegram user IDs who can manage the bot
_admin_ids_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: set = set()
if _admin_ids_raw:
    for uid in _admin_ids_raw.split(","):
        uid = uid.strip()
        if uid.isdigit():
            ADMIN_IDS.add(int(uid))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s', datefmt='%y-%m-%d %H:%M')
bot = Bot(token=token)
dp = Dispatcher(bot)

# ================= File-based settings storage =================
SETTINGS_DIR = BASE_DIR / "settings"

# Track which group a DM user is currently editing (user_id -> chat_id)
_dm_active_chat: dict = {}


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
    if message.chat.type == types.ChatType.PRIVATE:
        # In DM: show group selector if admin
        await _show_dm_panel(message)
    else:
        await message.answer(START, parse_mode="html")


# ================= Inline keyboard builders =================

MODE_NAMES = {'all': 'Все боты', 'blacklist': 'Чёрный список', 'whitelist': 'Белый список'}


def _settings_keyboard(chat_dict: dict, pv_prefix: str = '') -> types.InlineKeyboardMarkup:
    """Build main settings menu keyboard. pv_prefix embeds chat_id for DM callbacks."""
    deletion_on = chat_dict[b'deletion'] == b'1'
    warnings_shown = chat_dict[b'q'] == b'0'  # q=0 -> show warnings
    policy = chat_dict.get(b'policy', b'all').decode()

    def cb(action: str) -> str:
        return f"{pv_prefix}{action}"

    kb = types.InlineKeyboardMarkup()

    # Deletion toggle
    del_label = f"{'✅' if deletion_on else '❌'} Удаление: {'ВКЛ' if deletion_on else 'ВЫКЛ'}"
    kb.add(types.InlineKeyboardButton(del_label, callback_data=cb("toggle:deletion")))

    # Warning toggle
    q_label = f"{'✅' if warnings_shown else '❌'} Предупреждения: {'ВКЛ' if warnings_shown else 'ВЫКЛ'}"
    kb.add(types.InlineKeyboardButton(q_label, callback_data=cb("toggle:q")))

    # Mode buttons — 3 in one row
    kb.row(
        types.InlineKeyboardButton(
            f"{'✅ ' if policy == 'all' else ''}Все боты",
            callback_data=cb("mode:all")
        ),
        types.InlineKeyboardButton(
            f"{'✅ ' if policy == 'blacklist' else ''}Чёрный список",
            callback_data=cb("mode:blacklist")
        ),
        types.InlineKeyboardButton(
            f"{'✅ ' if policy == 'whitelist' else ''}Белый список",
            callback_data=cb("mode:whitelist")
        ),
    )

    # List management
    kb.add(types.InlineKeyboardButton("📋 Чёрный список", callback_data=cb("list:blacklist")))
    kb.add(types.InlineKeyboardButton("📋 Белый список", callback_data=cb("list:whitelist")))

    # In DM: add "back to group selector" button
    if pv_prefix:
        kb.add(types.InlineKeyboardButton("📋 Выбрать другую группу", callback_data="group_selector"))

    return kb


def _list_keyboard(list_name: str, members: set, pv_prefix: str = '') -> types.InlineKeyboardMarkup:
    """Build list view with per-item remove buttons."""
    kb = types.InlineKeyboardMarkup(row_width=1)

    def cb(action: str) -> str:
        return f"{pv_prefix}{action}"

    for username in sorted(members):
        kb.add(types.InlineKeyboardButton(
            f"❌ @{username}",
            callback_data=cb(f"remove:{list_name}:{username}")
        ))

    kb.add(types.InlineKeyboardButton(
        "➕ Добавить бота",
        callback_data=cb(f"add_hint:{list_name}")
    ))
    kb.add(types.InlineKeyboardButton(
        "↩ Назад к настройкам",
        callback_data=cb("menu")
    ))

    return kb


def _group_selector_keyboard(groups: list) -> types.InlineKeyboardMarkup:
    """Build group selector for DM panel. `groups` is list of (chat_id, title)."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    for chat_id, title in groups:
        short_title = title[:50] + "…" if len(title) > 50 else title
        kb.add(types.InlineKeyboardButton(
            f"💬 {short_title}",
            callback_data=f"select_group:{chat_id}"
        ))
    return kb


# ================= Admin helpers =================

def _normalize_username(raw: str) -> str:
    if not raw:
        return ''
    raw = raw.strip()
    if raw.startswith('@'):
        raw = raw[1:]
    return raw.lower()


def _is_bot_admin(user_id: int) -> bool:
    """Check if user is in the global ADMIN_IDS list from ENV."""
    if not ADMIN_IDS:
        # No ADMIN_IDS configured — fall back to group-admin-only check
        return True
    return user_id in ADMIN_IDS


async def _get_admin_groups(user_id: int) -> list:
    """Scan settings dirs and return list of (chat_id, title) where user is admin.
    Only checks groups that already have settings (bot was added there)."""
    groups = []
    if not SETTINGS_DIR.exists():
        return groups
    for chat_dir in sorted(SETTINGS_DIR.iterdir()):
        if not chat_dir.is_dir():
            continue
        try:
            chat_id = int(chat_dir.name)
        except ValueError:
            continue
        try:
            chat = await bot.get_chat(chat_id)
            member = await chat.get_member(user_id)
            if hasattr(member, 'status') and member.status in ('creator', 'administrator'):
                title = chat.title or f"Чат {chat_id}"
                groups.append((chat_id, title))
        except Exception:
            pass
    return groups


async def _show_dm_panel(message: types.Message):
    """Show group selector or reject if user is not a bot admin."""
    if not _is_bot_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к управлению ботом.")
        return
    groups = await _get_admin_groups(message.from_user.id)
    if not groups:
        await message.answer(
            "🔍 Вы не являетесь администратором ни в одной группе, где есть бот.\n\n"
            "Добавьте бота в группу и сделайте себя администратором."
        )
        return
    await message.answer(
        "📋 <b>Выберите группу для настройки:</b>",
        parse_mode="html",
        reply_markup=_group_selector_keyboard(groups)
    )


async def _resolve_chat(message: types.Message):
    """Resolve effective chat_id for text commands. Returns (chat_id, ok).
    In DM: uses the last group selected via inline panel.
    In group: uses message.chat.id.
    Returns (0, False) when user has no access."""
    if message.chat.type != types.ChatType.PRIVATE:
        # Group chat
        if not _is_bot_admin(message.from_user.id):
            try:
                await message.delete()
            except:
                pass
            return 0, False
        member = await message.chat.get_member(message.from_user.id)
        if hasattr(member, 'status') and member.status != "member":
            return message.chat.id, True
        try:
            await message.delete()
        except:
            pass
        return 0, False

    # DM: check active group
    if not _is_bot_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к управлению ботом.")
        return 0, False

    active_chat = _dm_active_chat.get(message.from_user.id)
    if active_chat is None:
        await _show_dm_panel(message)
        return 0, False

    # Verify still admin in the active group
    try:
        member = await bot.get_chat_member(active_chat, message.from_user.id)
        if not (hasattr(member, 'status') and member.status in ('creator', 'administrator')):
            await message.answer("⚠️ Вы больше не администратор выбранной группы.")
            await _show_dm_panel(message)
            return 0, False
    except Exception:
        await message.answer("⚠️ Не удалось проверить права. Возможно, бот удалён из группы.")
        await _show_dm_panel(message)
        return 0, False

    return active_chat, True


async def _ensure_admin_callback(call: types.CallbackQuery) -> bool:
    """Admin check for inline button presses. DM callbacks check via embedded chat_id."""
    logging.info(f"Checking admin rights for callback user {call.from_user.id}, data: {call.data}")

    # Global admin check first
    if not _is_bot_admin(call.from_user.id):
        await call.answer("⛔ У вас нет доступа к управлению ботом.", show_alert=True)
        return False

    # DM callbacks — data starts with "pv:" or is "group_selector" or "select_group:"
    if call.message.chat.type == types.ChatType.PRIVATE:
        # These are always allowed (admin already checked above, groups verified on selection)
        if call.data in ("group_selector",) or call.data.startswith("select_group:") or call.data.startswith("pv:"):
            return True
        # Unknown callback in DM — deny
        await call.answer("Неизвестная команда.", show_alert=True)
        return False

    # Group chat callback — verify group admin
    member = await call.message.chat.get_member(call.from_user.id)
    if hasattr(member, 'status') and member.status != "member":
        return True
    await call.answer("Только администраторы могут изменять настройки.", show_alert=True)
    return False


# ================= Settings commands =================

@dp.message_handler(commands=['settings', 'menu'])
async def cmd_settings(message: types.Message):
    """Show unified settings panel or DM group selector."""
    logging.info(f"Received /settings from user {message.from_user.id}")

    # DM panel
    if message.chat.type == types.ChatType.PRIVATE:
        await _show_dm_panel(message)
        return

    chat_id, ok = await _resolve_chat(message)
    if not ok:
        return
    chat_dict = await get_chat_dict(chat_id)
    pv_prefix = f"pv:{chat_id}:" if message.chat.type == types.ChatType.PRIVATE else ""
    await message.answer(
        _settings_header(pv_prefix),
        parse_mode="html",
        reply_markup=_settings_keyboard(chat_dict, pv_prefix)
    )


@dp.message_handler(commands=['toggle'])
async def cmd_toggle(message: types.Message):
    """Toggle deletion — shows keyboard."""
    chat_id, ok = await _resolve_chat(message)
    if not ok:
        return

    args = ''
    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            args = parts[1].strip().lower()

    chat_dict = await get_chat_dict(chat_id)
    pv_prefix = f"pv:{chat_id}:" if message.chat.type == types.ChatType.PRIVATE else ""
    if args in ('on', '1', 'вкл', 'enable'):
        to_set = b'1'
    elif args in ('off', '0', 'выкл', 'disable'):
        to_set = b'0'
    else:
        await message.answer(
            f"⚙️ <b>Удаление сообщений от инлайн-ботов</b>\n"
            f"Сейчас: <b>{'ВКЛЮЧЕНО' if chat_dict[b'deletion'] == b'1' else 'ВЫКЛЮЧЕНО'}</b>",
            parse_mode="html",
            reply_markup=_settings_keyboard(chat_dict, pv_prefix)
        )
        return

    chat_dict[b'deletion'] = to_set
    save_chat_dict(chat_id, chat_dict)
    await message.answer(
        f"Теперь я <b>{'буду' if to_set == b'1' else 'не буду'}</b> удалять сообщения от инлайн-ботов",
        parse_mode="html",
        reply_markup=_settings_keyboard(chat_dict, pv_prefix)
    )


@dp.message_handler(commands=['q'])
async def cmd_q(message: types.Message):
    """Toggle warnings — shows keyboard."""
    chat_id, ok = await _resolve_chat(message)
    if not ok:
        return

    args = ''
    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            args = parts[1].strip().lower()

    chat_dict = await get_chat_dict(chat_id)
    pv_prefix = f"pv:{chat_id}:" if message.chat.type == types.ChatType.PRIVATE else ""
    if args in ('on', '1', 'вкл', 'enable', 'show'):
        to_set = b'0'  # q=0 means show warnings
    elif args in ('off', '0', 'выкл', 'disable', 'hide'):
        to_set = b'1'  # q=1 means hide warnings
    else:
        await message.answer(
            f"⚙️ <b>Предупреждения при удалении</b>\n"
            f"Сейчас: <b>{'ВЫКЛЮЧЕНЫ' if chat_dict[b'q'] == b'1' else 'ВКЛЮЧЕНЫ'}</b>",
            parse_mode="html",
            reply_markup=_settings_keyboard(chat_dict, pv_prefix)
        )
        return

    chat_dict[b'q'] = to_set
    save_chat_dict(chat_id, chat_dict)
    await message.answer(
        f"Теперь я <b>{'буду' if to_set == b'1' else 'не буду'}</b> скрывать предупреждения",
        parse_mode="html",
        reply_markup=_settings_keyboard(chat_dict, pv_prefix)
    )


@dp.message_handler(commands=['mode'])
async def set_mode(message: types.Message):
    logging.info(f"Received /mode command from user {message.from_user.id}")
    chat_id, ok = await _resolve_chat(message)
    if not ok:
        return
    chat_dict = await get_chat_dict(chat_id)
    pv_prefix = f"pv:{chat_id}:" if message.chat.type == types.ChatType.PRIVATE else ""
    args = ''
    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            args = parts[1].strip().lower()

    if args in ('all', 'blacklist', 'whitelist'):
        chat_dict[b'policy'] = args.encode()
        save_chat_dict(chat_id, chat_dict)
        await message.answer(
            f"Режим установлен: <b>{MODE_NAMES.get(args, args)}</b>.",
            parse_mode="html",
            reply_markup=_settings_keyboard(chat_dict, pv_prefix)
        )
    else:
        current = chat_dict.get(b'policy', b'all').decode()
        await message.answer(
            f"<b>Режим обработки инлайн-ботов</b>\nТекущий: <b>{MODE_NAMES.get(current, current)}</b>",
            parse_mode="html",
            reply_markup=_settings_keyboard(chat_dict, pv_prefix)
        )


# ================= Blacklist / Whitelist text commands =================

@dp.message_handler(commands=['blacklist_add', 'blacklist_remove', 'blacklist_list'])
async def manage_blacklist(message: types.Message):
    logging.info(f"Received blacklist command from user {message.from_user.id}")
    chat_id, ok = await _resolve_chat(message)
    if not ok:
        return
    cmd = ''
    args = ''
    if message.text:
        parts = message.text.split(maxsplit=1)
        if parts:
            cmd = parts[0].lstrip('/').lower()
        if len(parts) > 1:
            args = parts[1].strip()

    key_name = "blacklist"
    list_label = "чёрный список"
    pv_prefix = f"pv:{chat_id}:" if message.chat.type == types.ChatType.PRIVATE else ""

    if cmd == 'blacklist_add':
        username = _normalize_username(args)
        if not username:
            await message.answer("Использование: /blacklist_add <имя_бота>")
            return
        set_add(chat_id, key_name, username)
        await message.answer(f"Бот @{username} добавлен в {list_label}.")
    elif cmd == 'blacklist_remove':
        username = _normalize_username(args)
        if not username:
            await message.answer("Использование: /blacklist_remove <имя_бота>")
            return
        set_remove(chat_id, key_name, username)
        await message.answer(f"Бот @{username} удалён из {list_label}.")
    else:  # blacklist_list
        members = sorted(set_members(chat_id, key_name))
        if not members:
            await message.answer("Чёрный список пуст.", reply_markup=_list_keyboard(key_name, set(), pv_prefix))
        else:
            await message.answer(
                "📋 <b>Чёрный список</b>",
                parse_mode="html",
                reply_markup=_list_keyboard(key_name, set(members), pv_prefix)
            )


@dp.message_handler(commands=['whitelist_add', 'whitelist_remove', 'whitelist_list'])
async def manage_whitelist(message: types.Message):
    logging.info(f"Received whitelist command from user {message.from_user.id}")
    chat_id, ok = await _resolve_chat(message)
    if not ok:
        return
    cmd = ''
    args = ''
    if message.text:
        parts = message.text.split(maxsplit=1)
        if parts:
            cmd = parts[0].lstrip('/').lower()
        if len(parts) > 1:
            args = parts[1].strip()

    key_name = "whitelist"
    list_label = "белый список"
    pv_prefix = f"pv:{chat_id}:" if message.chat.type == types.ChatType.PRIVATE else ""

    if cmd == 'whitelist_add':
        username = _normalize_username(args)
        if not username:
            await message.answer("Использование: /whitelist_add <имя_бота>")
            return
        set_add(chat_id, key_name, username)
        await message.answer(f"Бот @{username} добавлен в {list_label}.")
    elif cmd == 'whitelist_remove':
        username = _normalize_username(args)
        if not username:
            await message.answer("Использование: /whitelist_remove <имя_бота>")
            return
        set_remove(chat_id, key_name, username)
        await message.answer(f"Бот @{username} удалён из {list_label}.")
    else:  # whitelist_list
        members = sorted(set_members(chat_id, key_name))
        if not members:
            await message.answer("Белый список пуст.", reply_markup=_list_keyboard(key_name, set(), pv_prefix))
        else:
            await message.answer(
                "📋 <b>Белый список</b>",
                parse_mode="html",
                reply_markup=_list_keyboard(key_name, set(members), pv_prefix)
            )


# ================= Unified callback query handler =================

@dp.callback_query_handler()
async def handle_callback(call: types.CallbackQuery):
    """Handle all inline button presses — both group chat and DM."""
    logging.info(f"Callback from user {call.from_user.id}, data: {call.data}")

    data = call.data

    # --- Group selector (DM only) ---
    if data == "group_selector":
        if not _is_bot_admin(call.from_user.id):
            await call.answer("⛔ Доступ запрещён.", show_alert=True)
            return
        groups = await _get_admin_groups(call.from_user.id)
        if not groups:
            await call.message.edit_text(
                "🔍 Вы не являетесь администратором ни в одной группе, где есть бот."
            )
            await call.answer()
            return
        await call.message.edit_text(
            "📋 <b>Выберите группу для настройки:</b>",
            parse_mode="html",
            reply_markup=_group_selector_keyboard(groups)
        )
        await call.answer()
        return

    # --- Select group (DM only) ---
    if data.startswith("select_group:"):
        if not _is_bot_admin(call.from_user.id):
            await call.answer("⛔ Доступ запрещён.", show_alert=True)
            return
        try:
            chat_id = int(data.split(":", 1)[1])
        except (ValueError, IndexError):
            await call.answer("Ошибка: неверный ID группы.")
            return
        # Verify user is still admin in this group
        try:
            member = await bot.get_chat_member(chat_id, call.from_user.id)
            if not (hasattr(member, 'status') and member.status in ('creator', 'administrator')):
                await call.answer("Вы больше не администратор этой группы.", show_alert=True)
                return
        except Exception:
            await call.answer("Не удалось проверить права в группе.", show_alert=True)
            return
        _dm_active_chat[call.from_user.id] = chat_id  # remember for text commands in DM
        chat_dict = await get_chat_dict(chat_id)
        chat = await bot.get_chat(chat_id)
        pv_prefix = f"pv:{chat_id}:"
        await call.message.edit_text(
            f"⚙️ <b>Настройки — {chat.title or f'Чат {chat_id}'}</b>",
            parse_mode="html",
            reply_markup=_settings_keyboard(chat_dict, pv_prefix)
        )
        await call.answer()
        return

    # --- Determine if this is a DM callback ---
    pv_prefix = ''
    target_chat_id = call.message.chat.id
    if data.startswith("pv:"):
        # Format: "pv:<chat_id>:<action>"
        try:
            _, chat_id_str, action = data.split(":", 2)
            target_chat_id = int(chat_id_str)
            pv_prefix = f"pv:{target_chat_id}:"
            data = action  # strip prefix for matching below
        except (ValueError, IndexError):
            await call.answer("Ошибка: неверный формат данных.", show_alert=True)
            return
        # Verify user can manage this group
        if not _is_bot_admin(call.from_user.id):
            await call.answer("⛔ Доступ запрещён.", show_alert=True)
            return
    else:
        # Group chat callback — admin check
        if not await _ensure_admin_callback(call):
            return

    try:
        # --- Toggle deletion ---
        if data == "toggle:deletion":
            chat_dict = await get_chat_dict(target_chat_id)
            to_set = b'0' if chat_dict[b'deletion'] == b'1' else b'1'
            chat_dict[b'deletion'] = to_set
            save_chat_dict(target_chat_id, chat_dict)
            await call.message.edit_text(
                _settings_header(pv_prefix),
                parse_mode="html",
                reply_markup=_settings_keyboard(chat_dict, pv_prefix)
            )
            await call.answer(f"Удаление {'включено' if to_set == b'1' else 'выключено'}")

        # --- Toggle warnings ---
        elif data == "toggle:q":
            chat_dict = await get_chat_dict(target_chat_id)
            to_set = b'0' if chat_dict[b'q'] == b'1' else b'1'
            chat_dict[b'q'] = to_set
            save_chat_dict(target_chat_id, chat_dict)
            warnings_on = to_set == b'0'
            await call.message.edit_text(
                _settings_header(pv_prefix),
                parse_mode="html",
                reply_markup=_settings_keyboard(chat_dict, pv_prefix)
            )
            await call.answer(f"Предупреждения {'включены' if warnings_on else 'выключены'}")

        # --- Set mode ---
        elif data in ("mode:all", "mode:blacklist", "mode:whitelist"):
            mode = data.split(":", 1)[1]
            chat_dict = await get_chat_dict(target_chat_id)
            chat_dict[b'policy'] = mode.encode()
            save_chat_dict(target_chat_id, chat_dict)
            await call.message.edit_text(
                _settings_header(pv_prefix),
                parse_mode="html",
                reply_markup=_settings_keyboard(chat_dict, pv_prefix)
            )
            await call.answer(f"Режим: {MODE_NAMES[mode]}")

        # --- Show list ---
        elif data in ("list:blacklist", "list:whitelist"):
            list_name = data.split(":", 1)[1]
            list_label = "Чёрный список" if list_name == "blacklist" else "Белый список"
            members = set_members(target_chat_id, list_name)
            if not members:
                await call.message.edit_text(
                    f"📋 <b>{list_label}</b>\n\nСписок пуст.\n"
                    f"Используйте /{list_name}_add &lt;имя_бота&gt; чтобы добавить.",
                    parse_mode="html",
                    reply_markup=_list_keyboard(list_name, set(), pv_prefix)
                )
            else:
                await call.message.edit_text(
                    f"📋 <b>{list_label}</b>",
                    parse_mode="html",
                    reply_markup=_list_keyboard(list_name, members, pv_prefix)
                )
            await call.answer()

        # --- Remove from list ---
        elif data.startswith("remove:blacklist:") or data.startswith("remove:whitelist:"):
            parts = data.split(":", 2)
            list_name = parts[1]
            username = parts[2]
            list_label = "чёрного списка" if list_name == "blacklist" else "белого списка"
            list_title = "Чёрный список" if list_name == "blacklist" else "Белый список"
            set_remove(target_chat_id, list_name, username)
            members = set_members(target_chat_id, list_name)
            if not members:
                await call.message.edit_text(
                    f"📋 <b>{list_title}</b>\n\nСписок пуст.\n"
                    f"Используйте /{list_name}_add &lt;имя_бота&gt; чтобы добавить.",
                    parse_mode="html",
                    reply_markup=_list_keyboard(list_name, set(), pv_prefix)
                )
            else:
                await call.message.edit_text(
                    f"📋 <b>{list_title}</b>",
                    parse_mode="html",
                    reply_markup=_list_keyboard(list_name, members, pv_prefix)
                )
            await call.answer(f"@{username} удалён из {list_label}")

        # --- Add hint ---
        elif data.startswith("add_hint:"):
            list_name = data.split(":", 1)[1]
            cmd = f"/{list_name}_add"
            await call.answer(
                f"Используйте команду: {cmd} <имя_бота>",
                show_alert=True
            )

        # --- Back to settings menu ---
        elif data == "menu":
            chat_dict = await get_chat_dict(target_chat_id)
            await call.message.edit_text(
                _settings_header(pv_prefix),
                parse_mode="html",
                reply_markup=_settings_keyboard(chat_dict, pv_prefix)
            )
            await call.answer()

        else:
            logging.warning(f"Unknown callback data: {call.data}")
            await call.answer("Неизвестная команда")

    except Exception as e:
        logging.error(f"Callback error: {e}")
        await call.answer("Произошла ошибка. Попробуйте снова.", show_alert=True)


def _settings_header(pv_prefix: str = '') -> str:
    """Build settings panel header."""
    if pv_prefix:
        return "⚙️ <b>Настройки группы</b>"
    return "⚙️ <b>Настройки Anti-Inline бота</b>"


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
