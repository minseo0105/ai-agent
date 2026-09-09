import requests
import tomllib

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

DART_API_KEY = secrets["DART_API_KEY"]

url = "https://opendart.fss.or.kr/api/list.json"
params = {
    "crtfc_key": DART_API_KEY,
    "corp_code": "00254045",
    "bgn_de": "20250101",
    "end_de": "20261231",
    "page_count": 5
}

response = requests.get(url, params=params, timeout=15)
print(response.text)