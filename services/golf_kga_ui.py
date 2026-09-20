import streamlit as st

def _clean_combo(value):
    return " ".join(str(value or "").split())

def render_kga_course_intelligence(club):
    kga=club.get("kga") or {}
    if not kga.get("matched"):
        st.info("KGA 공인 코스정보는 아직 연결되지 않았습니다.")
        return

    st.markdown("### ⛳ KGA 공인 코스정보")
    st.caption(f"{kga.get('status','KGA 코스정보 확인')} · 확인일 {kga.get('checked_at','-')} · 대한골프협회")

    combos=[_clean_combo(x) for x in (kga.get("course_combinations") or []) if _clean_combo(x)]
    if combos:
        cols=st.columns(2)
        for i,combo in enumerate(combos[:6]):
            cols[i%2].markdown(f"**{combo}**")
        if len(combos)>6:
            with st.expander(f"다른 코스 조합 {len(combos)-6}개"):
                for combo in combos[6:]:
                    st.write("• "+combo)
    else:
        st.caption("KGA 매칭은 확인됐지만 코스 조합 상세는 확인되지 않았습니다.")

    ratings=kga.get("ratings") or []
    if ratings:
        st.markdown("#### 공인 난이도")
        for r in ratings[:8]:
            tee=r.get("tee") or "티"
            gender=r.get("gender") or ""
            length=r.get("length_yds")
            cr=r.get("course_rating")
            slope=r.get("slope_rating")
            parts=[x for x in [
                f"{tee} {gender}".strip(),
                f"{length:,}yd" if isinstance(length,(int,float)) else None,
                f"Course Rating {cr}" if cr not in (None,"") else None,
                f"Slope {slope}" if slope not in (None,"") else None,
            ] if x]
            st.write(" · ".join(parts))
    else:
        st.caption("Course Rating · Slope Rating 상세값은 KGA 상세 데이터가 연결된 코스부터 표시됩니다.")

    source=kga.get("source_url")
    if source:
        st.link_button("KGA 코스레이팅 DB ↗", source, width="stretch")
