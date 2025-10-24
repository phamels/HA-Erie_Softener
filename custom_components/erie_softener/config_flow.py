"""Config flow for Coronavirus integration."""
import logging
from typing import Dict

import voluptuous as vol

from homeassistant import config_entries, exceptions
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from collections import OrderedDict

# from . import get_coordinator
from .const import DOMAIN, OPTION_EMAIL  # pylint:disable=unused-import
from erie_connect.api_client import ErieConnect

from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_BASE_URL,
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_ID,
    CONF_UID,
    CONF_EXPIRY,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    PRESET_BASE_URLS
)

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Erie Watertreatment IQ26."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    _options = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""

        _LOGGER.debug(f'{DOMAIN}: async_step_user: {user_input}')

        errors = {}

        if user_input is None:
            return await self._show_setup_form(user_input, None)

        # Safely extract and validate user input
        email = (user_input.get("email") or "").strip()
        password = (user_input.get("password") or "").strip()
        base_url = (user_input.get("base_url") or "").strip()

        _LOGGER.debug(f"{DOMAIN}: Received user_input -> email set: {bool(email)}, password set: {bool(password)}, base_url: {base_url}")

        # Basic validation to prevent empty values
        if not email or not password or not base_url:
            errors["base"] = "missing_data"
            return await self._show_setup_form(user_input, errors)

        # Ensure base_url is one of the preset options
        if base_url not in PRESET_BASE_URLS:
            errors["base"] = "invalid_server"
            return await self._show_setup_form(user_input, errors)

        _LOGGER.info(f"{DOMAIN}: Received user_input -> email: {email}")
        _LOGGER.info(f"{DOMAIN}: Received user_input -> base_url: {base_url}")

        _LOGGER.warn(f'{DOMAIN}: erie_connect create for {email}')

        self.api = ErieConnect(email, password, base_url)

        try:
            device_id = await self.hass.async_add_executor_job(
                _login_and_select_first_active_device, self.api
            )
        except InvalidData:
            errors["base"] = "missing_data"

        if errors:
            _LOGGER.warn(f'{DOMAIN}: Errors {errors}')
            return await self._show_setup_form(user_input, errors)

            # Check if already configured
        # Ensure unique_id is a string, as required by Home Assistant
        await self.async_set_unique_id(str(device_id), raise_on_progress=False)
        self._abort_if_unique_id_configured()

        # Expect CONF_DEVICE_ID to be an int
        try:
            device_id_int = int(self.api.device.id)
        except (TypeError, ValueError):
            errors["base"] = "invalid_device_id"
            return await self._show_setup_form(user_input, errors)

        config_data = {
            CONF_EMAIL: email,
            CONF_PASSWORD: password,
            CONF_BASE_URL: base_url,
            CONF_ACCESS_TOKEN: self.api.auth.access_token,
            CONF_CLIENT_ID: self.api.auth.client,
            CONF_UID: self.api.auth.uid,
            CONF_EXPIRY: self.api.auth.expiry,
            CONF_DEVICE_ID: device_id_int,
            CONF_DEVICE_NAME: self.api.device.name
        }

        # coordinator = await get_coordinator(self.hass)

        return self.async_create_entry(title=DOMAIN, data=config_data)

    async def _show_setup_form(self, user_input=None, errors=None):
        """Show the setup form to the user."""
        if not user_input:
            user_input = {}

        _LOGGER.warn(f'{DOMAIN}: Show Setup Form: {user_input}')

        # Build schema with a dropdown list for base_url from PRESET_BASE_URLS
        options = [{"label": url, "value": url} for url in PRESET_BASE_URLS]

        schema = vol.Schema({
            vol.Required("email", default=user_input.get("email", "")): str,
            vol.Required("password", default=user_input.get("password", "")): str,
            vol.Required("base_url", default=user_input.get("base_url", PRESET_BASE_URLS[0])): SelectSelector(
                SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )


def _login_and_select_first_active_device(api):
    """Login Erie Connect and select first active device"""
    # These do i/o

    _LOGGER.debug(f'{DOMAIN}: erie_connect.login()')

    api.login()
    _LOGGER.debug(f'{DOMAIN}: erie_connect.select_first_active_device()')
    api.select_first_active_device()

    if (
            api.device is None
            or api.auth is None
    ):
        raise InvalidData

    return api.device.id


class InvalidData(exceptions.HomeAssistantError):
    """Error to indicate we get invalid data from the nas."""