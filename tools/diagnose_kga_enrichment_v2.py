from services.golf_kga_enrichment_v2 import diagnose_kga_matches

def main():
    result = diagnose_kga_matches()
    s = result["stats"]
    print("=" * 62)
    print("KGA 코스레이팅 DB 안전 매칭 진단 v2 · catalog 변경 없음")
    print("=" * 62)
    print(f"현재 catalog           : {s['catalog']}건")
    print(f"KGA 코스 조합          : {s['kga_course_rows']}건")
    print(f"KGA 골프장             : {s['kga_golf_courses']}곳")
    print(f"자동 매칭 안전 후보      : {s['safe']}건")
    print(f"추가 검토 후보           : {s['review']}건")
    print(f"미매칭                  : {s['none']}건")
    print()
    print("보고서: data/golf/kga_match_diagnostic_v2.json")
    print("catalog 변경: 없음")

if __name__ == "__main__":
    main()
