from __future__ import annotations

import unittest

import httpx

from weather.providers import fetch_nws_hourly_forecast


class WeatherProvidersTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_nws_hourly_forecast_follows_points_redirect(self):
        requests: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            if str(request.url) == "https://api.weather.gov/points/40.77945,-73.88027":
                return httpx.Response(
                    301,
                    headers={"Location": "/points/40.7795,-73.8803"},
                    request=request,
                )
            if str(request.url) == "https://api.weather.gov/points/40.7795,-73.8803":
                return httpx.Response(
                    200,
                    json={
                        "properties": {
                            "forecastHourly": "https://api.weather.gov/gridpoints/OKX/33,37/forecast/hourly",
                        }
                    },
                    request=request,
                )
            if str(request.url) == "https://api.weather.gov/gridpoints/OKX/33,37/forecast/hourly":
                return httpx.Response(
                    200,
                    json={"properties": {"periods": [{"temperature": 71}, {"temperature": 68}]}},
                    request=request,
                )
            return httpx.Response(404, request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            payload = await fetch_nws_hourly_forecast(client, lat=40.77945, lon=-73.88027)

        self.assertEqual(payload["properties"]["periods"][0]["temperature"], 71)
        self.assertEqual(
            requests,
            [
                "https://api.weather.gov/points/40.77945,-73.88027",
                "https://api.weather.gov/points/40.7795,-73.8803",
                "https://api.weather.gov/gridpoints/OKX/33,37/forecast/hourly",
            ],
        )
