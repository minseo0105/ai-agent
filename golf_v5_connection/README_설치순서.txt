골프장 추천 V5 연결 패키지

1. 이 폴더 전체를 ai-agent 프로젝트 폴더 안에 둡니다.
2. VS Code 터미널에서 ai-agent 루트로 이동합니다.
   cd C:\Users\user\Desktop\ai-agent
3. 아래 명령을 실행합니다.
   powershell -ExecutionPolicy Bypass -File .\golf_v5_connection\설치하기.ps1
4. 앱을 실행합니다.
   python -m streamlit run app.py

설치 스크립트가 기존 페이지와 catalog.json을 자동 백업한 뒤 교체합니다.

검증된 파일 기준:
- 원장: 553개
- 수도권/충청권/강원권: 377개
- service: 13개
- 공공데이터 영업확인 candidate: 175개
- 현재 추천 Pool(페이지 로직 기준, 코스 적격 필터 전): 188개

주의:
224개를 억지로 맞추기 위해 미검증 candidate를 추천 가능으로 승격하지 않았습니다.
현재 업로드된 원장에 실제로 기록된 상태값을 그대로 사용합니다.
