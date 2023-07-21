import json
import logging
from os import path, remove
import sys

from cryptography.fernet import Fernet, InvalidToken

from homeassistant.config_entries import STORAGE_VERSION, ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PATH,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import translation
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.json import JSONEncoder
from homeassistant.helpers.storage import Store

from ..common.consts import (
    CONFIGURATION_FILE,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
    INVALID_TOKEN_SECTION,
    LEGACY_KEY_FILE,
    PROTOCOLS,
    STORAGE_DATA_KEY,
    STORAGE_DATA_USE_ORIGINAL_STREAM,
    WS_PROTOCOLS,
)
from ..common.entity_descriptions import IntegrationEntityDescription

_LOGGER = logging.getLogger(__name__)


class ConfigManager:
    _encryption_key: str | None
    _crypto: Fernet | None
    _data: dict | None

    _store: Store | None
    _store_data: dict | None
    _entry_data: dict | None
    _translations: dict | None
    _password: str | None
    _entry_title: str
    _entry_id: str

    _is_set_up_mode: bool
    _is_initialized: bool

    def __init__(self, hass: HomeAssistant | None, entry: ConfigEntry | None = None):
        self._hass = hass
        self._encryption_key = None
        self._crypto = None

        self._data = None

        self._password = None

        self._store = None
        self._entry_data = None
        self._store_data = None
        self._translations = None

        self._is_set_up_mode = entry is None
        self._is_initialized = False
        self._entry = entry

        if self._is_set_up_mode:
            self._entry_data = {}
            self._entry_title = DEFAULT_NAME
            self._entry_id = "config"

        else:
            self._entry_data = entry.data
            self._entry_title = entry.title
            self._entry_id = entry.entry_id

        if hass is not None:
            self._store = Store(
                hass, STORAGE_VERSION, CONFIGURATION_FILE, encoder=JSONEncoder
            )

    @property
    def is_initialized(self) -> bool:
        is_initialized = self._is_initialized

        return is_initialized

    @property
    def data(self):
        return self._data

    @property
    def name(self):
        entry_title = self._entry_title

        return entry_title

    @property
    def use_original_stream(self):
        use_original_stream = self.data.get(STORAGE_DATA_USE_ORIGINAL_STREAM, False)

        return use_original_stream

    @property
    def host(self) -> str:
        host = self.data.get(CONF_HOST)

        return host

    @property
    def port(self) -> int:
        port = self.data.get(CONF_PORT, DEFAULT_PORT)

        return port

    @property
    def ssl(self) -> bool:
        port = self.data.get(CONF_SSL, False)

        return port

    @property
    def path(self) -> str | None:
        config_path = self.data.get(CONF_PATH)

        return config_path

    @property
    def username(self) -> str:
        username = self.data.get(CONF_USERNAME)

        return username

    @property
    def password_hashed(self) -> str:
        password_hashed = self._encrypt(self.password)

        return password_hashed

    @property
    def password(self) -> str:
        password = self._data.get(CONF_PASSWORD)

        return password

    @property
    def ws_url(self):
        protocol = WS_PROTOCOLS[self.ssl]

        url_path = "/" if self.path == "" else self.path

        url = f"{protocol}://{self.host}:{self.port}{url_path}"

        return url

    @property
    def api_url(self):
        protocol = PROTOCOLS[self.ssl]

        url_path = "/" if self.path == "" else self.path

        url = f"{protocol}://{self.host}:{self.port}{url_path}"

        return url

    @property
    def entry_id(self):
        entry_id = self._entry_id

        return entry_id

    @property
    def entry(self):
        entry = self._entry

        return entry

    async def initialize(self):
        try:
            await self._load()

            password = self._entry_data.get(CONF_PASSWORD)

            self._data = {
                key: self._entry_data[key]
                for key in self._entry_data
                if key != CONF_PASSWORD
            }

            if not self._is_set_up_mode:
                password = self._decrypt(password)

            self._data[CONF_PASSWORD] = password

            if self._hass is None:
                self._translations = {}

            else:
                self._translations = await translation.async_get_translations(
                    self._hass, self._hass.config.language, "entity", {DOMAIN}
                )

            _LOGGER.debug(
                f"Translations loaded, Data: {json.dumps(self._translations)}"
            )

            self._is_initialized = True

        except InvalidToken:
            self._is_initialized = False

            _LOGGER.error(
                f"Invalid encryption key, Please follow instructions in {INVALID_TOKEN_SECTION}"
            )

        except Exception as ex:
            self._is_initialized = False

            exc_type, exc_obj, tb = sys.exc_info()
            line_number = tb.tb_lineno

            _LOGGER.error(
                f"Failed to initialize configuration manager, Error: {ex}, Line: {line_number}"
            )

    def get_translation(
        self,
        platform: Platform,
        entity_key: str,
        attribute: str,
        default_value: str | None = None,
    ) -> str | None:
        translation_key = (
            f"component.{DOMAIN}.entity.{platform}.{entity_key}.{attribute}"
        )

        translated_value = self._translations.get(translation_key, default_value)

        _LOGGER.debug(
            "Translations requested, "
            f"Key: {translation_key}, "
            f"Default value: {default_value}, "
            f"Value: {translated_value}"
        )

        return translated_value

    def get_entity_name(
        self,
        entity_description: IntegrationEntityDescription,
        device_info: DeviceInfo,
    ) -> str:
        entity_key = entity_description.key

        device_name = device_info.get("name")
        platform = entity_description.platform

        translated_name = self.get_translation(
            platform, entity_key, CONF_NAME, entity_description.name
        )

        entity_name = (
            device_name
            if translated_name is None or translated_name == ""
            else f"{device_name} {translated_name}"
        )

        return entity_name

    def update_credentials(self, data: dict):
        self._entry_data = data

    async def update_original_stream(self, is_on: bool):
        _LOGGER.debug(f"Set use original stream to {is_on}")

        self.data[STORAGE_DATA_USE_ORIGINAL_STREAM] = is_on

        await self._save()

    async def _load(self):
        self._data = None

        await self._load_config_from_file()
        await self._load_encryption_key()

        if self._data is None:
            self._data = {}

        default_configuration = self._get_defaults()

        keys_before = len(self._data.keys())

        for key in default_configuration:
            value = default_configuration[key]

            if key not in self._data:
                self._data[key] = value

        if keys_before != len(self._data.keys()):
            await self._save()

    @staticmethod
    def _get_defaults() -> dict:
        data = {
            STORAGE_DATA_USE_ORIGINAL_STREAM: False,
        }

        return data

    async def _load_config_from_file(self):
        if self._store is not None:
            self._store_data = await self._store.async_load()

            if self._store_data is not None:
                self._data = self._store_data.get(self._entry_id)

    async def _load_encryption_key(self):
        if self._store_data is None:
            if self._hass is not None:
                await self._import_encryption_key()

        else:
            if STORAGE_DATA_KEY in self._store_data:
                self._encryption_key = self._store_data.get(STORAGE_DATA_KEY)

            else:
                for store_data_key in self._store_data:
                    if store_data_key == self._entry_id:
                        entry_configuration = self._store_data[store_data_key]

                        if STORAGE_DATA_KEY in entry_configuration:
                            self._encryption_key = entry_configuration.get(
                                STORAGE_DATA_KEY
                            )

                            entry_configuration.pop(STORAGE_DATA_KEY)

        if self._encryption_key is None:
            self._encryption_key = Fernet.generate_key().decode("utf-8")

        self._crypto = Fernet(self._encryption_key.encode())

    async def _import_encryption_key(self):
        """Load the retained data from store and return de-serialized data."""
        key = None

        legacy_key_path = self._hass.config.path(LEGACY_KEY_FILE)

        if path.exists(legacy_key_path):
            with open(legacy_key_path, "rb") as file:
                key = file.read().decode("utf-8")

            remove(legacy_key_path)

        else:
            store = Store(
                self._hass, STORAGE_VERSION, f".{DOMAIN}", encoder=JSONEncoder
            )

            data = await store.async_load()

            if data is not None:
                key = data.get("key")

                await store.async_remove()

        if key is not None:
            self._encryption_key = key

    async def remove(self):
        if self._entry_id in self._store_data:
            self._is_set_up_mode = True

            self._store_data.pop(self._entry_id)

            await self._save()

    async def _save(self):
        if self._store is None:
            return

        if self._store_data is None:
            self._store_data = {STORAGE_DATA_KEY: self._encryption_key}

        elif STORAGE_DATA_KEY not in self._store_data:
            self._store_data[STORAGE_DATA_KEY] = self._encryption_key

        if not self._is_set_up_mode:
            if self._entry_id not in self._store_data:
                self._store_data[self._entry_id] = {}

            for key in self._data:
                if key not in [CONF_PASSWORD, CONF_USERNAME]:
                    self._store_data[self._entry_id][key] = self._data[key]

            if CONF_USERNAME in self._store_data[self._entry_id]:
                self._store_data[self._entry_id].pop(CONF_USERNAME)

            if CONF_PASSWORD in self._store_data[self._entry_id]:
                self._store_data[self._entry_id].pop(CONF_PASSWORD)

        await self._store.async_save(self._store_data)

    def _encrypt(self, data: str) -> str:
        if data is not None:
            data = self._crypto.encrypt(data.encode()).decode()

        return data

    def _decrypt(self, data: str) -> str:
        if data is not None and len(data) > 0:
            data = self._crypto.decrypt(data.encode()).decode()

        return data
