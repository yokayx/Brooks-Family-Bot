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
VZP_SOURCE_NOTE = "vzp-launcher.pro · не официальный API GTA5RP"

HEAD_VZP_ROLE_ID = 1551727304382611476
RECRUITER_ROLE_ID = 1453123003645952254
TEST_ROLE_ID = 1550827936641454141
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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    discord_token: str
    database_url: str = "sqlite+aiosqlite:///data/brooks.db"


def load_settings() -> Settings:
    return Settings()
