import os
import re
import csv
import time
import hashlib
import logging
import requests
import signal
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from functools import lru_cache
from pymdi.pymdi import Client
from astral import LocationInfo
from astral.sun import sun
from tqdm import tqdm
from shapely.geometry import Point
import geopandas as gpd

# DSS client settings
token = os.getenv("MINING_TOKEN") or "75e40531-4760-4fa8-9e90-5b22e45ada20"
data_endpoint = os.getenv("DATA_ENDPOINT") or "https://mdi.cla.eu.momenta.works"

dss_client = Client(token=token, endpoint=data_endpoint, log_level='INFO')

# Configure logging
logging.basicConfig(filename='data_processing.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

processed_data = []
existing_md5s = set()

@lru_cache(maxsize=1000)
def get_location_details(latitude, longitude):
    base_url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": latitude,
        "lon": longitude,
        "format": "json"
    }
    headers = {
        "User-Agent": "YourAppName/1.0 (yourname@domain.com)"
    }

    try:
        start_time = time.time()
        response = requests.get(base_url, params=params, headers=headers)
        elapsed_time = time.time() - start_time
        logging.info(f"API call took {elapsed_time:.2f} seconds")

        response.raise_for_status()
        data = response.json()
        return data
    except requests.RequestException as e:
        logging.error(f"Request failed: {e}")
        return None

def categorize_location(location_info):
    if not location_info or location_info.get('error') == 'Unable to geocode':
        return "Unknown"

    location_type = location_info.get('type', '').lower()
    address = location_info.get('address', {})

    if location_type == 'motorway':
        return "Highway"
    if 'town' in address or 'residential' in address or 'city' in address:
        return "Urban"
    if 'village' in address:
        return "Rural"

    return "Unknown"

def categorize_time(dt, latitude, longitude):
    utc_zone = ZoneInfo('UTC')
    dt_utc = dt.astimezone(utc_zone)

    city = LocationInfo("", "", "UTC", latitude, longitude)
    s = sun(city.observer, date=dt_utc.date())
    
    sunrise_cet = s['sunrise'].astimezone(dt.tzinfo)
    sunset_cet = s['sunset'].astimezone(dt.tzinfo)
    dawn_cet = s['dawn'].astimezone(dt.tzinfo)
    dusk_cet = s['dusk'].astimezone(dt.tzinfo)
    
    if sunrise_cet <= dt < sunset_cet:
        return 'Day'
    elif dt >= dusk_cet or dt < dawn_cet:
        return 'Night'
    elif dawn_cet <= dt < sunrise_cet:
        return 'Dawn'
    elif sunset_cet <= dt < dusk_cet:
        return 'Dusk'

def fetch_metadata(md5):
    try:
        meta = dss_client.get_meta([md5])
        if not meta or not meta[0]['fdi']:
            return None
        latitude = meta[0]['fdi'].get('gps', {}).get('latitude', None)
        longitude = meta[0]['fdi'].get('gps', {}).get('longitude', None)
        collected_time_raw = meta[0]['collected_time']
        cet_zone = ZoneInfo('CET')
        collected_time = datetime.fromtimestamp(collected_time_raw, tz=cet_zone)
        
        return md5, latitude, longitude, collected_time, meta[0]
    except Exception as e:
        logging.error(f"Failed to fetch metadata for MD5 {md5}: {e}")
        return None

def process_md5(md5_data):
    if not md5_data:
        return
    md5, latitude, longitude, collected_time, meta = md5_data
    
    location_info = get_location_details(latitude, longitude)
    location_category = categorize_location(location_info) if location_info else "Out of Range"
    times_of_day = categorize_time(collected_time, latitude, longitude) if latitude and longitude else None

    Mviz = f'https://mviz.cla.eu.momenta.works/player/v4/?bag_md5={md5}'

    return dict(
        MD5=md5,
        location=location_category,
        times_of_day=times_of_day,
        weather=meta['fdi'].get('weather', {}).get('weather', None),
        latitude=latitude,
        longitude=longitude,
        Mviz=Mviz
    )

def save_logs(new_data, filename):
    file_exists = os.path.exists(filename)
    with open(filename, 'a', newline='') as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(['MD5', 'Location', 'Times of Day', 'Weather', 'Latitude', 'Longitude', 'Mviz'])

        for data in new_data:
            writer.writerow([data['MD5'], data['location'], data['times_of_day'], data['weather'], data['latitude'], data['longitude'], data['Mviz']])

def is_coordinate_on_land(lat, lon, land_gdf):
    """
    Check if a given coordinate is within any land boundary polygons.

    Parameters:
    - lat: Latitude of the coordinate.
    - lon: Longitude of the coordinate.
    - land_gdf: GeoDataFrame containing land boundaries.

    Returns:
    - True if the coordinate is within land boundaries, otherwise False.
    """
    point = Point(lon, lat)  # Create a Point object from the coordinates

    # Check if the point is within any of the land polygons
    return any(land_gdf.contains(point))

def handle_exit(signal, frame):
    logging.info("Script interrupted. Saving logs...")
    save_logs(processed_data, 'valid_coordinates_log.csv')
    sys.exit(0)

def load_existing_md5s():
    existing_md5s = set()
    
    for log_file in ['valid_coordinates_log.csv', 'invalid_coordinates_log.csv']:
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    if row[0]:
                        existing_md5s.add(row[0])
    
    return existing_md5s

def main():
    # Load the shapefile containing land boundaries
    land_gdf = gpd.read_file('./WB_countries_Admin0_10m/WB_countries_Admin0_10m.shp')

    # Read the content from the file
    with open('data100.txt', 'r') as file:
        file_content = file.read()

    # Use regular expressions to find all occurrences of md5
    md5_pattern = re.compile(r'"md5":"([a-f0-9]{32})"')
    md5s = set(md5_pattern.findall(file_content))

    logging.info(f"Total unique MD5s found: {len(md5s)}")

    # Load existing MD5s from both logs
    existing_md5s = load_existing_md5s()

    # Filter out MD5s that are already processed
    new_md5s = md5s - existing_md5s
    logging.info(f"New MD5s to process: {len(new_md5s)}")

    # Convert the set to a list before slicing
    new_md5s_list = list(new_md5s)

    # Split the MD5s into batches of 100
    batches = [new_md5s_list[i:i + 100] for i in range(0, len(new_md5s_list), 100)]

    with tqdm(total=len(new_md5s_list), unit='md5', desc='Processing MD5s') as pbar:
        for batch in batches:
            # Fetch metadata for the batch
            batch_data = [fetch_metadata(md5) for md5 in batch]
            # Process metadata and filter on land
            for md5_data in batch_data:
                if md5_data:
                    md5, latitude, longitude, collected_time, meta = md5_data
                    if latitude is not None and longitude is not None:
                        if is_coordinate_on_land(latitude, longitude, land_gdf):
                            processed_entry = process_md5(md5_data)
                            if processed_entry:
                                processed_data.append(processed_entry)
                                save_logs([processed_entry], 'valid_coordinates_log.csv')
                                processed_data.clear()
                        else:
                            # Log MD5 with invalid (non-land) coordinates
                            invalid_entry = process_md5(md5_data)
                            save_logs([invalid_entry], 'invalid_coordinates_log.csv')
                    else:
                        # Log MD5 with missing or invalid coordinates
                        invalid_entry = process_md5(md5_data)
                        save_logs([invalid_entry], 'invalid_coordinates_log.csv')
                    
                    pbar.update(1)

    logging.info("All data processed and saved to CSV.")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    main()
