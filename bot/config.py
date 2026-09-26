from pydantic_settings import BaseSettings, SettingsConfigDict

# Каналы
ROSTER_CHANNEL_ID = 1552347393993867274
OWNER_CHANNEL_ID = 1453123004484554990
VZP_CHANNEL_ID = 1552367826906521620
APPLICATIONS_CHANNEL_ID = 1453123004308390116
TICKETS_CATEGORY_ID = 1552394606975516804
CLOSED_TICKETS_CATEGORY_ID = 1552394634616111178

# Ранги состава сверху вниз: (role_id, заголовок секции)
RANK_ROLES: tuple[tuple[int, str], ...] = (
    (1453123003645952260, "Owner"),
    (1508501848347377835, "AFK Owner"),
    (1453123003645952259, "Dep. Owner"),
    (1551727304382611476, "Head VZP"),
    (1453123003645952254, "Recruiter (ПИШИТЕ ИМ ПО ВОПРОСАМ ВСТУПЛЕНИЯ)"),
    (1550834570134298624, "Пенсия"),
    (1453123003645952255, "High"),
    (1453123003566264611, "Main"),
    (1550827936641454141, "Test"),
)

RANK_ROLE_IDS: frozenset[int] = frozenset(role_id for role_id, _ in RANK_ROLES)

# Руководство: /refresh и тег при ошибке.
# Последний id — вне состава.
LEADERSHIP_ROLE_IDS: tuple[int, ...] = (
    1453123003645952260,  # Owner
    1508501848347377835,  # AFK Owner
    1453123003645952259,  # Dep. Owner
    1550837284927180882,  # руководство вне состава
)

FAMILY_NAME = "Brooks"
FALLBACK_NICK = "ник по форме"
PLACEHOLDER = "."
ERROR_CHANNEL_TEXT = "Возникла проблема при отправке состава"
MAX_SEND_ATTEMPTS = 3
DISCORD_MESSAGE_LIMIT = 2000
SEND_GAP_SECONDS = 0.4
MOSCOW_TZ = "Europe/Moscow"

VZP_API_BASE = "https://vzp-launcher.pro/api"
VZP_FAMILY_NAME = "Brooks"
VZP_SERVER_NAME = "RICHMAN"
VZP_POLL_SECONDS = 300
VZP_FETCH_LIMIT = 100
VZP_FETCH_PAGES = 3
VZP_HTTP_TIMEOUT = 25
VZP_RETRIES = 3
# Окно, в котором считаем активную войну «свежим забивом» (список иногда
# хранит протухшие active-записи за несколько дней).
VZP_DEF_WINDOW_MINUTES = 45
# Канал для авто-уведомления и авто-сбора на деф.
PLUS_DEF_CHANNEL_ID = VZP_CHANNEL_ID
VZP_SOURCE_NOTE = "vzp-launcher.pro · не официальный API GTA5RP"

HEAD_VZP_ROLE_ID = 1551727304382611476
RECRUITER_ROLE_ID = 1453123003645952254
TEST_ROLE_ID = 1550827936641454141
# Роль состава «онли VZP» (тег в сообщении заявок)
APPLICATION_VZP_ROLE_ID = 1553233826451431494
# Канал с панелью управления
CONTROL_PANEL_CHANNEL_ID = 1553239900176908289
APPLICATION_KIND_MAIN = "main"
APPLICATION_KIND_VZP = "vzp"
APPLICATION_KIND_LABELS = {
    APPLICATION_KIND_MAIN: "Main",
    APPLICATION_KIND_VZP: "VZP",
}
APPLICATION_KIND_ROLE_IDS = {
    APPLICATION_KIND_MAIN: TEST_ROLE_ID,
    APPLICATION_KIND_VZP: APPLICATION_VZP_ROLE_ID,
}
APPLICATION_KIND_REQUIREMENTS = {
    APPLICATION_KIND_MAIN: "Нужны откаты с Арены.",
    APPLICATION_KIND_VZP: "Нужны откаты с VZP и Арены.",
}
APPLICATION_MAX_QUESTIONS = 5
# Сколько ждём ответ заявителя на вопрос анкеты в тикете (секунды).
APPLICATION_ANSWER_TIMEOUT_SECONDS = 1800
APPLICATIONS_MESSAGE_KEY = "applications_menu"
CONTROL_MESSAGE_KEY = "control_panel"
APPLICATION_MEMBER_ROLE_ID = 1552378409211142174
APPLICATION_ACCEPT_ROLE_IDS: tuple[int, ...] = (
    TEST_ROLE_ID,
    APPLICATION_MEMBER_ROLE_ID,
)
PLUS_PING_GENERAL_ROLE_ID = 1552378409211142174
PLUS_PING_VZP_ROLE_ID = 1551727236812640359
PLUS_KIND_GENERAL = "general"
PLUS_KIND_VZP = "vzp"
PLUS_KIND_LABELS = {
    PLUS_KIND_GENERAL: "Общий",
    PLUS_KIND_VZP: "VZP",
}
PLUS_KIND_PINGS = {
    PLUS_KIND_GENERAL: PLUS_PING_GENERAL_ROLE_ID,
    PLUS_KIND_VZP: PLUS_PING_VZP_ROLE_ID,
}

# --- Логи (ког bot/cogs/logs.py) ---------------------------------------------------
# ID каналов подставить, когда руководство выдаст: 0 = канал не настроен, лог
# для него просто не отправляется.
LOG_TEXT_CHANNEL_ID = 0
LOG_VOICE_CHANNEL_ID = 0
LOG_MEMBER_CHANNEL_ID = 0
LOG_MODERATION_CHANNEL_ID = 0
LOG_SERVER_CHANNEL_ID = 0
LOG_INVITE_CHANNEL_ID = 0
LOG_AUDIT_CHANNEL_ID = 0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    discord_token: str
    database_url: str = "sqlite+aiosqlite:///data/brooks.db"
    # Привилегированный интент: включать, только если он отмечен в Discord
    # Developer Portal (Bot -> Message Content Intent), иначе бот не залогинится.
    message_content_intent: bool = False


def load_settings() -> Settings:
    return Settings()
