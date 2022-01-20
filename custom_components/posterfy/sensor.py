"""Posterfy sensor platform."""
import logging
import datetime
import re
import aiohttp
from typing import Any, Callable, Dict, Optional
from xml.etree import ElementTree

from .const import (
    FANDANGO_COMINGSOON_RSS,
    FANDANGO_NEWMOVIES_RSS,
)

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import (
    ConfigType,
    DiscoveryInfoType,
    HomeAssistantType,
)

_LOGGER = logging.getLogger(__name__)

# Time between updating data from movie feeds
SCAN_INTERVAL = datetime.timedelta(minutes=120)

# Use a regex to parse the fandago image renderer url
FANDANGO_IMAGERENDERER_LINK_RE = re.compile(
    r"(?P<prefix>https://images.fandango.com/)(?P<version>[^/]+)/ImageRenderer/(?P<width>\d+)/(?P<height>\d+)(?P<suffix>.+)"
)

async def async_setup_platform(
    hass: HomeAssistantType,
    config: ConfigType,
    async_add_entities: Callable,
    discovery_info: Optional[DiscoveryInfoType] = None,
) -> None:
    """Set up the sensor platform."""
    session = async_get_clientsession(hass)
    sensors = [PosterfySensor(session)]
    async_add_entities(sensors, update_before_add=True)

class PosterfySensor(Entity):
    """Representation of a posterfy sensor."""

    def __init__(self, session: aiohttp.client.ClientSession):
        super().__init__()
        self.session = session
        self.attrs: Dict[str, Any] = {
            "movies": []
        }
        self._name = "Posterfy Feed"
        self._state = None
        self._available = True

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return "d730055a-2c26-486a-b3b9-80bb86946f75"

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

    def fixUpPosterImage(self, url: str) -> str:
        match = FANDANGO_IMAGERENDERER_LINK_RE.match(url)
        if match is not None:
            url = match.group("prefix") + "/" + match.group("version") + "/ImageRenderer/500/1000" + match.group("suffix")
        return url

    async def fillFandangoFeed(self, category, rss, movies):
        # get the updated feed data
        async with self.session.get(rss) as resp:
            rss = await resp.text()
            root = ElementTree.fromstring(rss)
            channel = root.find("channel")
            for item in channel.iter("item"):
                title = item.find("title").text
                poster = item.find("enclosure").get("url")
                poster = self.fixUpPosterImage(poster)
                movies.append({
                    "platform": "Fandango",
                    "category": category,
                    "title": title,
                    "poster": poster,
                })


    async def async_update(self):
        try:
            # make a new movie list
            movies = []
            
            # get the updated feed data
            await self.fillFandangoFeed("coming_soon", FANDANGO_COMINGSOON_RSS, movies)
            await self.fillFandangoFeed("in_theaters", FANDANGO_NEWMOVIES_RSS, movies)

            # Set state to something meaningful? new date?
            self._state = datetime.datetime.now()
            self.attrs["movies"] = movies
            self._available = True
        except:
            self._available = False
            _LOGGER.exception("Error retrieving data from movie feeds.")
