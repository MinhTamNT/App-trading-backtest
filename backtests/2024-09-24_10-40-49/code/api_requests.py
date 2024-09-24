
import requests
import time


def MakeRequestWithRetries(algorithm, url, retries=3, delay=5):
    for attempt in range(retries):
        try:
            headers = {"X-Fiin-Key": algorithm.ApiKey, "Accept": "application/json"}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response
            else:
                algorithm.Debug(f"Request failed with status {response.status_code}: {response.text}")
        except Exception as ex:
            algorithm.Debug(f"Attempt {attempt + 1} failed: {str(ex)}")
        time.sleep(delay)
    return None

