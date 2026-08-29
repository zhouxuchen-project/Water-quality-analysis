from __future__ import annotations

import requests

from project_config import STATIONS_CSV, ensure_directories


STATIONS_WFS_URL = (
    "https://datamap.gov.wales/geoserver/ows?"
    "service=WFS&version=2.0.0&request=GetFeature&"
    "typeNames=geonode:nrw_water_quality_archive_stations&outputFormat=csv"
)


def main() -> None:
    ensure_directories()
    response = requests.get(STATIONS_WFS_URL, timeout=60)
    response.raise_for_status()
    STATIONS_CSV.write_bytes(response.content)
    print(f"Downloaded station metadata to: {STATIONS_CSV}")
    print(f"File size: {STATIONS_CSV.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
