"""Outbound HTTP clients for the three upstream metadata providers."""

from .omdb import OMDbClient
from .poiskkino import PoiskkinoClient
from .tmdb import TMDBClient

__all__ = ["OMDbClient", "PoiskkinoClient", "TMDBClient"]
