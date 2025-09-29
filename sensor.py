
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN, CONF_TPI_ENTITY, CONF_HOURUSE_ENTITY, CONF_PRICE_ENTITY, CONF_THRESHOLD_ENTITY,
    CONF_T5, CONF_T10, CONF_T15, CONF_T20,
    SENSOR_HOUR, SENSOR_TODAY, SENSOR_MONTH,
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    data = hass.data[DOMAIN][entry.entry_id]
    store = data["store"]

    ctrl = AmsCostsController(hass, entry, store)
    data["controller"] = ctrl

    entities = [
        AmsCostHourSensor(ctrl, entry),
        AmsCostTodaySensor(ctrl, entry),
        AmsCostMonthSensor(ctrl, entry),
    ]
    async_add_entities(entities, True)

    await ctrl.async_initialize()

class AmsCostsController:
    '''Hovedlogikk: lytter på TPI, beregner delta og oppdaterer sensorer.'''

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, store):
        self.hass = hass
        self.entry = entry
        self.store = store

        cfg = entry.data
        self.tpi_entity = cfg[CONF_TPI_ENTITY]
        self.houruse_entity = cfg[CONF_HOURUSE_ENTITY]
        self.price_entity = cfg[CONF_PRICE_ENTITY]
        self.threshold_entity = cfg[CONF_THRESHOLD_ENTITY]

        self.t_map = {
            "5": float(cfg.get(CONF_T5, 160.0)),
            "10": float(cfg.get(CONF_T10, 395.0)),
            "15": float(cfg.get(CONF_T15, 656.0)),
            "20": float(cfg.get(CONF_T20, 923.0)),
        }

        self.prev_tpi: float | None = None
        self.day_cost_energy: float = 0.0
        self.month_cost_energy: float = 0.0
        self.last_day_key: str | None = None
        self.last_month_key: str | None = None

        self._price: float = 0.0
        self._houruse: float = 0.0
        self._threshold: str = "0"

        self.s_hour: AmsCostHourSensor | None = None
        self.s_today: AmsCostTodaySensor | None = None
        self.s_month: AmsCostMonthSensor | None = None

        self._remove_listener = None

    async def async_initialize(self):
        data = await self.store.async_load() or {}
        self.prev_tpi = data.get("prev_tpi")
        self.day_cost_energy = data.get("day_cost_energy", 0.0)
        self.month_cost_energy = data.get("month_cost_energy", 0.0)
        self.last_day_key = data.get("last_day_key")
        self.last_month_key = data.get("last_month_key")

        self._price = _as_float(self.hass.states.get(self.price_entity))
        self._houruse = _as_float(self.hass.states.get(self.houruse_entity))
        self._threshold = _as_str(self.hass.states.get(self.threshold_entity))

        self._remove_listener = async_track_state_change_event(
            self.hass, [self.tpi_entity], self._handle_tpi_event
        )

        await self._compute_and_push(delta_kwh=0.0, tpi=None)

    async def async_unload(self):
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None

    @callback
    async def _handle_tpi_event(self, event):
        new_state = event.data.get("new_state")
        if not new_state:
            return
        try:
            tpi = float(new_state.state)
        except (TypeError, ValueError):
            return
        await self._compute_and_push_from_tpi(tpi)

    async def _compute_and_push_from_tpi(self, tpi: float):
        now = datetime.now(timezone.utc)
        day_key = now.strftime("%Y-%m-%d")
        month_key = now.strftime("%Y-%m")
        if self.last_day_key != day_key:
            self.day_cost_energy = 0.0
            self.last_day_key = day_key
        if self.last_month_key != month_key:
            self.month_cost_energy = 0.0
            self.last_month_key = month_key

        delta = 0.0
        if self.prev_tpi is None:
            self.prev_tpi = tpi
        else:
            delta = tpi - self.prev_tpi
            if delta < 0 or delta > 10:
                delta = 0.0
            self.prev_tpi = tpi

        await self._compute_and_push(delta_kwh=delta, tpi=tpi)

    async def _compute_and_push(self, delta_kwh: float, tpi: float | None):
        self._price = _as_float(self.hass.states.get(self.price_entity), fallback=self._price)
        self._houruse = _as_float(self.hass.states.get(self.houruse_entity), fallback=self._houruse)
        self._threshold = _as_str(self.hass.states.get(self.threshold_entity), fallback=self._threshold)

        if delta_kwh > 0 and self._price > 0:
            add_cost = delta_kwh * self._price
            self.day_cost_energy += add_cost
            self.month_cost_energy += add_cost

        eff_month = self.t_map.get(self._threshold, 0.0)
        now = datetime.now(timezone.utc)
        days_in_month = _days_in_month(now.year, now.month)
        day_eff_part = (eff_month / days_in_month) if days_in_month else 0.0

        hour_cost = max(0.0, self._houruse) * max(0.0, self._price)

        if self.s_hour:
            self.s_hour._native_value = round(hour_cost, 2)
            self.s_hour._attrs = {
                "unit_of_measurement": "NOK",
                "price_nok_per_kwh": round(self._price, 4),
                "houruse_kwh": round(self._houruse, 3),
                "threshold": self._threshold,
                "effect_month_kr": eff_month,
            }
            self.s_hour.async_write_ha_state()

        if self.s_today:
            today = self.day_cost_energy + day_eff_part
            self.s_today._native_value = round(today, 2)
            self.s_today._attrs = {
                "unit_of_measurement": "NOK",
                "energy_cost_kr": round(self.day_cost_energy, 2),
                "day_effect_part_kr": round(day_eff_part, 2),
                "price_nok_per_kwh": round(self._price, 4),
                "threshold": self._threshold,
                "effect_month_kr": eff_month,
                "days_in_month": days_in_month,
            }
            self.s_today.async_write_ha_state()

        if self.s_month:
            month_total = self.month_cost_energy + eff_month
            self.s_month._native_value = round(month_total, 2)
            self.s_month._attrs = {
                "unit_of_measurement": "NOK",
                "energy_cost_kr": round(self.month_cost_energy, 2),
                "price_nok_per_kwh": round(self._price, 4),
                "threshold": self._threshold,
                "effect_month_kr": eff_month,
            }
            self.s_month.async_write_ha_state()

        await self.store.async_save({
            "prev_tpi": self.prev_tpi,
            "day_cost_energy": self.day_cost_energy,
            "month_cost_energy": self.month_cost_energy,
            "last_day_key": self.last_day_key,
            "last_month_key": self.last_month_key,
        })

def _as_float(state, fallback: float = 0.0) -> float:
    try:
        if state is None:
            return fallback
        return float(state.state)
    except (TypeError, ValueError):
        return fallback

def _as_str(state, fallback: str = "0") -> str:
    try:
        if state is None or state.state in (None, "", "unknown", "unavailable"):
            return fallback
        return str(state.state)
    except Exception:
        return fallback

def _days_in_month(y: int, m: int) -> int:
    from calendar import monthrange
    return monthrange(y, m)[1]

class _BaseAmsCostSensor(SensorEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "NOK"

    def __init__(self, ctrl, entry: ConfigEntry, name: str, unique_suffix: str):
        self.ctrl = ctrl
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._native_value: float | None = None
        self._attrs: dict[str, Any] = {}

    @property
    def native_value(self):
        return self._native_value

    @property
    def extra_state_attributes(self):
        return self._attrs

class AmsCostHourSensor(_BaseAmsCostSensor):
    def __init__(self, ctrl, entry: ConfigEntry):
        super().__init__(ctrl, entry, "Kostnad denne timen", "cost_hour")
        ctrl.s_hour = self

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown", "unavailable", None):
            try:
                self._native_value = float(last.state)
            except ValueError:
                pass

class AmsCostTodaySensor(_BaseAmsCostSensor):
    def __init__(self, ctrl, entry: ConfigEntry):
        super().__init__(ctrl, entry, "Kostnad i dag", "cost_today")
        ctrl.s_today = self

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown", "unavailable", None):
            try:
                self._native_value = float(last.state)
            except ValueError:
                pass

class AmsCostMonthSensor(_BaseAmsCostSensor):
    def __init__(self, ctrl, entry: ConfigEntry):
        super().__init__(ctrl, entry, "Kostnad denne måneden", "cost_month")
        ctrl.s_month = self

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in ("unknown", "unavailable", None):
            try:
                self._native_value = float(last.state)
            except ValueError:
                pass
