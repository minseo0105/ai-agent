import requests
import zipfile
import io
import xml.etree.ElementTree as ET
import json
import tomllib

with open(".streamlit/secrets.toml", "rb") as f:
    secrets = tomllib.load(f)

DART_API_KEY = secrets["DART_API_KEY"]

url = "https://opendart.fss.or.kr/api/corpCode.xml"
params = {"crtfc_key": DART_API_KEY}
response = requests.get(url, params=params, timeout=60)

zip_file = zipfile.ZipFile(io.BytesIO(response.content))
xml_data = zip_file.read("CORPCODE.xml")
root = ET.fromstring(xml_data)

corp_map = {}
for corp in root.findall("list"):
    name = corp.find("corp_name").text
    code = corp.find("corp_code").text
    if name not in corp_map:
        corp_map[name] = []
    corp_map[name].append(code)

with open("corp_codes.json", "w", encoding="utf-8") as f:
    json.dump(corp_map, f, ensure_ascii=False)

print(f"저장 완료! 총 {len(corp_map)}개 회사")