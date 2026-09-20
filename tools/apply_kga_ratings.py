from services.golf_kga_ratings import apply

if __name__=="__main__":
    r=apply()
    print("="*66)
    print("KGA Course / Slope Rating 보강 완료")
    print("="*66)
    print(f"공식 자료 기준일          : {r['source_date']}")
    print(f"PDF 파싱 rating 행        : {r['parsed_rows']}건")
    print(f"catalog 연결 골프장       : {r['matched_clubs']}곳")
    print(f"저장 rating               : {r['ratings_saved']}건")
    print(f"미연결 파싱 행            : {r['unmatched_parsed_rows']}건")
    print(f"백업                     : {r['backup']}")
    print("※ 2024-07-15 KGA 공식 공개자료임을 catalog에 함께 저장했습니다.")
