import os
import re
import requests
import time
from pymdi.pymdi import Client
import hashlib
import signal
import sys

# DSS client settings
token = os.getenv("MINING_TOKEN") or "75e40531-4760-4fa8-9e90-5b22e45ada20"
data_endpoint = os.getenv("DATA_ENDPOINT") or "https://mdi.cla.eu.momenta.works"

dss_client = Client(token=token, endpoint=data_endpoint, log_level='INFO')

def get_location_details(latitude, longitude):
    base_url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": latitude,
        "lon": longitude,
        "format": "json"
    }
    cache_key = hashlib.md5(f"{latitude}_{longitude}".encode()).hexdigest()
    
    headers = {
        "User-Agent": "YourAppName/1.0 (yourname@domain.com)"
    }

    start_time = time.time()  # Record start time
    response = requests.get(base_url, params=params, headers=headers)
    end_time = time.time()  # Record end time

    elapsed_time = end_time - start_time  # Calculate elapsed time
    print(f"API call took {elapsed_time:.2f} seconds")

    if response.status_code == 200:
        return response.json()
    else:
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

def fetch_metadata(md5):
    meta = dss_client.get_meta([md5])
    if not meta or not meta[0]['fdi']:
        return None
    latitude = meta[0]['fdi'].get('gps', {}).get('latitude', None)
    longitude = meta[0]['fdi'].get('gps', {}).get('longitude', None)
    
    return md5, latitude, longitude, meta[0]

def process_md5(md5_data):
    md5, latitude, longitude, meta = md5_data
    
    location_info = get_location_details(latitude, longitude)
    location_category = categorize_location(location_info) if location_info else "Out of Range"

    print(f"MD5: {md5}")
    print(f"Latitude: {latitude}")
    print(f"Longitude: {longitude}")
    print(f"Location Category: {location_category}")
    print("----------------------------")

def handle_exit(signal, frame):
    print("Script interrupted. Exiting...")
    sys.exit(0)

if __name__ == "__main__":
    # Handle script interruption
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    try:
        # Read the content from the file
        with open('data100.txt', 'r') as file:
            file_content = file.read()

        # Use regular expressions to find all occurrences of md5
        md5_pattern = re.compile(r'"md5":"([a-f0-9]{32})"')
        md5s = md5_pattern.findall(file_content)

        # Filter new MD5s
        new_md5s = set(md5s)

        print("MD5 check complete. Starting processing of MD5s...")
        for md5 in new_md5s:
            md5_data = fetch_metadata(md5)
            if md5_data:
                process_md5(md5_data)
                time.sleep(1)  # Sleep for 1 second to respect rate limit

        print("\nAll data processed.")

    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)
