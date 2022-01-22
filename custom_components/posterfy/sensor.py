"""Posterfy sensor platform."""
import logging
import datetime
from dateutil.relativedelta import relativedelta
import aiohttp
from typing import Any, Callable, Dict, Optional
import voluptuous as vol
import datetime

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)

import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    CONF_NAME,
    CONF_API_KEY,
    CONF_URL,
    CONF_SERVICE,
)

from .const import SERVICE_TYPE_TMDB, SERVICE_TYPES

_LOGGER = logging.getLogger(__name__)

# Time between updating data from movie feeds
SCAN_INTERVAL = datetime.timedelta(minutes=120)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_API_KEY): cv.string,
        vol.Required(CONF_URL): cv.url,
        vol.Required(CONF_SERVICE): vol.All(cv.string, vol.In(SERVICE_TYPES)),
    }
)


async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: Callable,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the sensor platform."""
    session = async_get_clientsession(hass)

    sensors = []
    _LOGGER.info("Found config for posterfy " + config[CONF_SERVICE])
    if config[CONF_SERVICE] == SERVICE_TYPE_TMDB:
        sensors.append(
            PosterfyTmdbSensor(
                config[CONF_NAME], session, config[CONF_URL], config[CONF_API_KEY]
            )
        )

    if len(sensors) > 0:
        async_add_entities(sensors, update_before_add=True)


class PosterfyTmdbSensor(Entity):
    """Representation of a TMDB posterfy sensor."""

    def __init__(
        self,
        name: str,
        session: aiohttp.client.ClientSession,
        base_url: str,
        api_key: str,
    ):
        super().__init__()
        self.session = session
        self.base_url = base_url
        self.api_key = api_key
        self.attrs: Dict[str, Any] = {"movies": []}
        self._name = name
        self._state = None
        self._available = True

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self._name

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def state(self) -> Optional[str]:
        return self._state

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return self.attrs

    async def fillFeed(self, platform, category, url, movies):
        # get the updated feed data
        async with self.session.get(url) as resp:
            data = await resp.json()
            min_date = None
            if "dates" in data:
                min_date = datetime.datetime.strptime(
                    data["dates"]["minimum"], "%Y-%m-%d"
                )

            results = data["results"]
            for item in results:
                if (
                    not item["adult"]
                    and not item["video"]
                    and item["original_language"] == "en"
                    and item["poster_path"] is not None
                ):
                    release_date = datetime.datetime.strptime(
                        item["release_date"], "%Y-%m-%d"
                    )
                    if min_date is None or release_date > min_date:
                        movies.append(
                            {
                                "platform": platform,
                                "category": category,
                                "title": item["title"],
                                "release_date": item["release_date"],
                                "poster": "https://image.tmdb.org/t/p/w780"
                                + item["poster_path"],
                            }
                        )

    def getRecentMovieProviderMoviesUrl(self, provider, release_date_gte):
        return f"{self.base_url}/discover/movie?api_key={self.api_key}&language=en-US&sort_by=popularity.asc&include_adult=false&include_video=false&page=1&primary_release_date.gte={release_date_gte}&with_original_language=en&with_watch_providers={provider}&watch_region=US&with_watch_monetization_types=flatrate"

    async def async_update(self):
        try:
            # make a new movie list
            movies = []

            # coming soon
            await self.fillFeed(
                "tmdb",
                "coming_soon",
                f"{self.base_url}/movie/upcoming?api_key={self.api_key}&language=en-US&page=1",
                movies,
            )

            # in theaters
            await self.fillFeed(
                "tmdb",
                "in_theaters",
                f"{self.base_url}/movie/now_playing?api_key={self.api_key}&language=en-US&page=1",
                movies,
            )

            previous_month = datetime.datetime.today() - relativedelta(months=1)
            previous_month = previous_month.strftime("%Y-%m-%d")

            # netflix
            await self.fillFeed(
                "netflix",
                "streaming",
                self.getRecentMovieProviderMoviesUrl(8, previous_month),
                movies,
            )

            # prime
            await self.fillFeed(
                "prime",
                "streaming",
                self.getRecentMovieProviderMoviesUrl(9, previous_month),
                movies,
            )

            # hbomax
            await self.fillFeed(
                "hbomax",
                "streaming",
                self.getRecentMovieProviderMoviesUrl(384, previous_month),
                movies,
            )

            # TODO: The disney feed data isn't looking right. Leaving out for now.
            # # disneyplus
            # await self.fillFeed(
            #     "disneyplus",
            #     "streaming",
            #     self.getRecentMovieProviderMoviesUrl(337, previous_month),
            #     movies,
            # )

            # Set state to something meaningful? new date?
            self._state = datetime.datetime.now()
            self.attrs["movies"] = movies
            self._available = True
        except:
            self._available = False
            _LOGGER.exception("Error retrieving data from movie feeds.")
