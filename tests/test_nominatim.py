import json
from unittest.mock import patch, MagicMock

import requests

from bin.fetch_nominatim import fetch_details
from bin.search_nominatim import search


def test_fetch_details_success(monkeypatch):
    class DummyResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"place_id": 1234, "display_name": "Dummy Place"}

    def dummy_get(*args, **kwargs):
        return DummyResponse()

    monkeypatch.setattr(requests, "get", dummy_get)
    res = fetch_details("N", 1234, c="railway", addressdetails=1)
    assert res["place_id"] == 1234
    assert "Dummy Place" in res["display_name"]


def test_search_nominatim_returns_raw(monkeypatch):
    mock_loc = MagicMock()
    mock_loc.raw = {"display_name": "Tai Po, Hong Kong"}

    class DummyGeolocator:
        def geocode(self, *args, **kwargs):
            return [mock_loc]

    monkeypatch.setattr(
        "bin.search_nominatim.Nominatim", lambda user_agent: DummyGeolocator()
    )
    results = search("Tai Po", limit=1, polygon_geojson=False)
    assert isinstance(results, list)
    assert results[0]["display_name"].startswith("Tai Po")
