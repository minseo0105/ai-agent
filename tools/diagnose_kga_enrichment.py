from services.golf_kga_enrichment import diagnose_kga_matches

if __name__ == "__main__":
    result = diagnose_kga_matches()
    s = result["stats"]
    print("=" * 64)
    print("KGA 코스정보 안전 매칭 진단 · catalog 변경 없음")
    print("=" * 64)
    print(f"현재 catalog          : {s['catalog']}건")
    print(f"KGA 코스 조합         : {s['kga_course_rows']}건")
    print(f"KGA 회원사 홀수        : {s['kga_member_hole_rows']}건")
    print(f"자동 적용 안전 후보     : {s['safe']}건")
    print(f"추가 검토 후보          : {s['review']}건")
    print(f"미매칭                 : {s['none']}건")
    print()
    print("보고서: data/golf/kga_match_diagnostic.json")
    print("catalog 변경: 없음")
