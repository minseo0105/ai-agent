from pathlib import Path
import shutil
from datetime import datetime

BASE=Path(__file__).resolve().parents[1]
PAGE=BASE/"pages"/"6_골프장_추천.py"
BACKUP=BASE/"data"/"golf"/"backups"/f"6_골프장_추천_before_kga_{datetime.now():%Y%m%d_%H%M%S}.py"

IMPORT="from services.golf_kga_ui import render_kga_course_intelligence\n"
ANCHOR="    # =====================================================\n    # CONTACT / NAVIGATION\n"
CALL="    # KGA 공인 코스정보\n    render_kga_course_intelligence(club)\n\n"

def main():
    text=PAGE.read_text(encoding="utf-8")
    if "render_kga_course_intelligence" in text:
        print("이미 KGA UI가 적용되어 있습니다.")
        return
    BACKUP.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(PAGE,BACKUP)
    marker="from services.golf_public_data import dual_verification_summary\n"
    if marker not in text:
        raise RuntimeError("페이지 import 위치를 찾지 못했습니다. 원본은 변경하지 않았습니다.")
    text=text.replace(marker,marker+IMPORT,1)
    if ANCHOR not in text:
        raise RuntimeError("CONTACT / NAVIGATION 위치를 찾지 못했습니다. 원본은 변경하지 않았습니다.")
    text=text.replace(ANCHOR,CALL+ANCHOR,1)
    PAGE.write_text(text,encoding="utf-8")
    print("KGA UI 적용 완료")
    print("백업:",BACKUP)
    print("수정:",PAGE)

if __name__=="__main__":
    main()
