def _num(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def rating_summary(club):
    ratings=((club.get("kga") or {}).get("ratings") or [])
    male=[r for r in ratings if str(r.get("gender") or "").strip()=="남자"]
    rows=male or ratings
    slopes=[_num(r.get("slope_rating")) for r in rows]
    lengths=[_num(r.get("length_yds")) for r in rows]
    slopes=[x for x in slopes if x is not None]
    lengths=[x for x in lengths if x is not None]
    if not slopes: return None
    return {"slope":sum(slopes)/len(slopes), "length_yds":sum(lengths)/len(lengths) if lengths else None}

def _target_slope(avg_score, challenge):
    score=int(avg_score or 100)
    base=118 if score>=110 else 123 if score>=100 else 128 if score>=90 else 133
    return base+{"편하게":-7,"적당히":0,"도전":8}.get(challenge,0)

def fit_info(club, avg_score=100, challenge="적당히"):
    s=rating_summary(club)
    if not s:
        return {"known":False,"band":"공인 난이도 확인 필요","reason":"KGA Course/Slope 상세값 없음","distance":999.0}
    slope=s["slope"]; target=_target_slope(avg_score,challenge); d=abs(slope-target)
    band="내 설정과 비슷한 난이도" if d<=5 else ("내 설정보다 편한 편" if slope<target else "내 설정보다 도전적인 편")
    parts=[f"KGA 평균 Slope {slope:.0f}"]
    if s.get("length_yds"): parts.append(f"평균 전장 {s['length_yds']:,.0f}yd")
    parts.append(f"평균 {int(avg_score)}타 · {challenge} 기준 참고")
    return {"known":True,"band":band,"reason":" · ".join(parts),"distance":d}

def personalized_sort_key(club, avg_score=100, challenge="적당히"):
    f=fit_info(club,avg_score,challenge)
    return (0 if f["known"] else 1,f["distance"],str(club.get("name") or ""))

def personalized_reason(club, avg_score=100, challenge="적당히"):
    f=fit_info(club,avg_score,challenge)
    return f"{f['band']} · {f['reason']}"
