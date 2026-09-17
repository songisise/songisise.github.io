# 산림조합중앙회 송이 공판현황 수집기
# 자료 출처: 산림조합중앙회 (https://m.nfcf.or.kr)

import json, os, re, time
from datetime import date, timedelta
import requests
from bs4 import BeautifulSoup

BASE = "https://m.nfcf.or.kr/forest/user.tdf"
HEADERS = {"User-Agent": "Mozilla/5.0 (songi-price-viewer; github.com/songisise/songi)"}
OUT_DIR = "docs/data"
EMPTY_FILE = os.path.join(OUT_DIR, "_empty.json")

GRADES = ["1등품", "2등품", "생장정지품", "개산품", "등외품", "혼합품"]


def to_num(text):
    if not text:
        return 0.0
    cleaned = re.sub(r"[^0-9.]", "", text)
    if cleaned in ("", "."):
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def has_data(payload):
    """등급 어딘가에 0보다 큰 값이 있으면 공판이 열린 날로 본다."""
    for region in payload.get("regions", []):
        for v in region.get("grades", {}).values():
            if v.get("kg", 0) > 0 or v.get("price", 0) > 0:
                return True
    return False


def file_has_data(path):
    """저장된 파일에 쓸 만한 자료가 들어 있는지 본다."""
    try:
        with open(path, encoding="utf-8") as fp:
            return has_data(json.load(fp))
    except Exception:
        return False


def fetch_day(day):
    params = {
        "a": "user.songi.SongiApp",
        "c": "1003",
        "sply_date": day.strftime("%Y%m%d"),
        "pmsh_item_c": "01",
        "mc": "MOB_CST01",
    }
    res = requests.get(BASE, params=params, headers=HEADERS, timeout=20)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, "html.parser")

    regions = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        name = ""
        node = table.find_previous(string=re.compile(r"\S"))
        hops = 0
        while node is not None and hops < 12:
            text = str(node).strip()
            if text and "단가는" not in text and len(text) < 20:
                name = text
                break
            node = node.find_previous(string=re.compile(r"\S"))
            hops += 1

        grades = {}
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) >= 3 and cells[0] in GRADES:
                grades[cells[0]] = {"kg": to_num(cells[1]), "price": to_num(cells[2])}

        if grades:
            total_kg = sum(v["kg"] for v in grades.values())
            total_amt = sum(v["kg"] * v["price"] for v in grades.values())
            regions.append({
                "name": name or "전체",
                "grades": grades,
                "total_kg": round(total_kg, 2),
                "total_amt": round(total_amt),
            })

    if not regions:
        return None
    return {"date": day.isoformat(), "regions": regions}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # 공판이 없던 날 목록 (다시 훑지 않기 위해 기억해둔다)
    try:
        with open(EMPTY_FILE, encoding="utf-8") as fp:
            empty = set(json.load(fp))
    except Exception:
        empty = set()

    today = date.today()
    targets = []
    for year in range(today.year - 5, today.year + 1):
        day = date(year, 9, 1)
        end = min(date(year, 11, 30), today)
        while day <= end:
            targets.append(day)
            day += timedelta(days=1)

    index = []
    for day in targets:
        key = day.isoformat()
        path = os.path.join(OUT_DIR, f"{key}.json")
        recent = (today - day).days <= 10

        # 이미 받아둔 날은 검사만 하고 넘어간다
        if os.path.exists(path) and not recent:
            if file_has_data(path):
                index.append(key)
                continue
            os.remove(path)      # 내용이 비었으면 지운다
            empty.add(key)
            continue

        # 공판이 없던 날로 확인된 과거 날짜는 건너뛴다
        if key in empty and not recent:
            continue

        try:
            data = fetch_day(day)
        except Exception as err:
            print(f"{key} 실패: {err}")
            # 받아온 게 없어도 저장해둔 자료가 있으면 목록에 남긴다
            if file_has_data(path):
                index.append(key)
            continue

        if data and has_data(data):
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=1)
            index.append(key)
            empty.discard(key)
            print(f"{key} 저장 ({len(data['regions'])}곳)")
        elif file_has_data(path):
            # 산림조합에서 잠깐 자료를 안 줄 때 기존 파일을 지우지 않는다
            index.append(key)
            print(f"{key} 자료 없음 - 기존 파일 유지")
        else:
            if os.path.exists(path):
                os.remove(path)
            empty.add(key)
            print(f"{key} 공판 없음")

        time.sleep(0.6)

    index = sorted(set(index), reverse=True)
    with open(os.path.join(OUT_DIR, "index.json"), "w", encoding="utf-8") as fp:
        json.dump({"dates": index, "updated": today.isoformat()}, fp, ensure_ascii=False, indent=1)
    with open(EMPTY_FILE, "w", encoding="utf-8") as fp:
        json.dump(sorted(empty), fp, ensure_ascii=False)

    print(f"\n공판일 {len(index)}일치 보관 중")


if __name__ == "__main__":
    main()
