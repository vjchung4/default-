"""
DART(전자공시) Open API로 회사별 연도별 매출액/유형자산/직원수를 수집해 엑셀로 저장한다.

사용법:
    export DART_API_KEY="발급받은_API_KEY"
    python3 dart_financial_data.py

대상 회사/연도는 아래 COMPANIES / YEARS 상수에서 바꿀 수 있다.

디버깅용으로 DART_DEBUG=1 을 함께 설정하면, 각 회사/연도별 원본 API 응답을
debug_raw/ 폴더에 JSON으로 저장한다. 수치가 이상하게 나올 때 이 파일을 보면
정확한 원인을 확인할 수 있다.

로직이 아직 확정되지 않은 동안에는 결과를 콘솔에만 출력하고, corpCode.xml
캐시 파일이나 엑셀 파일을 디스크에 자동으로 저장하지 않는다.
검증이 끝나서 파일로 저장하고 싶으면 DART_SAVE_FILES=1 을 설정한다.
"""

import io
import os
import re
import sys
import time
import zipfile

import requests

API_KEY = os.environ.get("DART_API_KEY")
if not API_KEY:
    sys.exit("환경변수 DART_API_KEY가 설정되어 있지 않습니다. export DART_API_KEY=... 후 다시 실행하세요.")

BASE_URL = "https://opendart.fss.or.kr/api"
CORP_CODE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpCode.xml")

COMPANIES = [
    "삼성SDI",
    "SK이노베이션",
    "DB하이텍",
    "포스코퓨처엠",
    "한화솔루션",
    "이엔에프테크놀로지",
    "한미반도체",
    "원익IPS",
    "주성엔지니어링",
    "이오테크닉스",
    "에코프로비엠",
    "엘앤에프",
    "덕산네오룩스",
    "원익QnC",
    "리노공업",
    "두산에너빌리티",
    "현대자동차",
    "한화에어로스페이스",
    "두산퓨얼셀",
    "안랩",
]
YEARS = list(range(2018, 2026))
REPORT_CODE = "11011"  # 사업보고서(연간)
REVENUE_ACCOUNT_NAMES = {"매출액", "수익(매출액)"}
TANGIBLE_ASSET_ACCOUNT_NAMES = {"유형자산"}
DEBUG_DUMP = os.environ.get("DART_DEBUG") == "1"
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_raw")
SAVE_FILES = os.environ.get("DART_SAVE_FILES") == "1"


def load_corp_code_xml():
    """DART 전체 회사 고유번호 매핑 파일을 받아온다.

    DART_SAVE_FILES=1 일 때만 corpCode.xml로 캐시해서 다음 실행 때 재사용한다.
    그 전에는 매번 새로 받아서 메모리에서만 쓰고 디스크에 남기지 않는다.
    """
    if SAVE_FILES and os.path.exists(CORP_CODE_CACHE):
        with open(CORP_CODE_CACHE, encoding="utf-8") as f:
            return f.read()

    resp = requests.get(f"{BASE_URL}/corpCode.xml", params={"crtfc_key": API_KEY}, timeout=30)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_bytes = zf.read(zf.namelist()[0])
    xml_text = xml_bytes.decode("utf-8")
    if SAVE_FILES:
        with open(CORP_CODE_CACHE, "w", encoding="utf-8") as f:
            f.write(xml_text)
    return xml_text


def find_corp_code(xml_text, corp_name):
    """상장사(stock_code가 공백이 아닌 것) 중 이름이 정확히 일치하는 회사의 고유번호를 찾는다."""
    import html

    for block in re.findall(r"<list>(.*?)</list>", xml_text, re.S):
        # XML에서는 "&"가 "&amp;"로 이스케이프되어 있으므로 비교 전에 풀어준다
        # (예: "동원F&B", "F&F"처럼 이름에 &가 들어간 회사).
        name = html.unescape(re.search(r"<corp_name>(.*?)</corp_name>", block).group(1)).strip()
        stock_code = re.search(r"<stock_code>(.*?)</stock_code>", block).group(1).strip()
        if name == corp_name and stock_code:
            corp_code = re.search(r"<corp_code>(.*?)</corp_code>", block).group(1).strip()
            return corp_code
    raise ValueError(f"상장사 목록에서 '{corp_name}'을(를) 찾지 못했습니다.")


def to_int(amount_str):
    if not amount_str:
        return None
    try:
        return int(amount_str.replace(",", ""))
    except ValueError:
        return None


def dump_debug(name, year, endpoint, payload):
    if not DEBUG_DUMP:
        return
    os.makedirs(DEBUG_DIR, exist_ok=True)
    path = os.path.join(DEBUG_DIR, f"{name}_{year}_{endpoint}.json")
    with open(path, "w", encoding="utf-8") as f:
        import json

        json.dump(payload, f, ensure_ascii=False, indent=2)


def fetch_financials(corp_code, year, name=None):
    """해당 연도 매출액(손익/포괄손익계산서)과 유형자산(재무상태표)을 개별(별도) 재무제표에서 가져온다.

    사업보고서 본문의 "4. 재무제표"(개별/별도)만 사용한다. 연결재무제표(CFS)는
    보지 않는다 — 개별 재무제표가 그 해에 없으면 연결로 대체하지 않고 빈 값을 낸다.
    """
    fs_div = "OFS"
    params = {
        "crtfc_key": API_KEY,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": REPORT_CODE,
        "fs_div": fs_div,
    }
    res = requests.get(f"{BASE_URL}/fnlttSinglAcntAll.json", params=params, timeout=30).json()
    dump_debug(name, year, f"fs_{fs_div}", res)
    if res.get("status") != "000":
        return None, None, None

    revenue = tangible_assets = None
    for item in res["list"]:
        account_nm = item.get("account_nm", "").strip()
        sj_div = item.get("sj_div", "").strip()  # BS=재무상태표, IS/CIS=손익/포괄손익계산서
        if sj_div in ("IS", "CIS") and account_nm in REVENUE_ACCOUNT_NAMES and revenue is None:
            revenue = to_int(item.get("thstrm_amount"))
        elif sj_div == "BS" and account_nm in TANGIBLE_ASSET_ACCOUNT_NAMES and tangible_assets is None:
            tangible_assets = to_int(item.get("thstrm_amount"))
    return revenue, tangible_assets, fs_div


def find_business_report_rcept_no(corp_code, year, name=None):
    """해당 사업연도의 사업보고서 접수번호(rcept_no)를 list.json으로 찾는다.

    사업보고서는 보통 다음 해 3월에 제출되지만 정정 등으로 늦게 올라올 수도
    있어 다음 해 전체를 조회 범위로 잡는다. 여러 건이 잡히면 report_nm에
    해당 연도(12월 결산)가 명시된 것을 우선하고, 없으면 가장 최근 것을 쓴다.
    """
    params = {
        "crtfc_key": API_KEY,
        "corp_code": corp_code,
        "bgn_de": f"{year + 1}0101",
        "end_de": f"{year + 1}1231",
        "pblntf_detail_ty": "A001",  # 사업보고서
        "page_count": 100,
    }
    res = requests.get(f"{BASE_URL}/list.json", params=params, timeout=30).json()
    dump_debug(name, year, "report_list", res)
    if res.get("status") != "000":
        return None

    candidates = [item for item in res.get("list", []) if item.get("report_nm", "").startswith("사업보고서")]
    if not candidates:
        return None

    exact = [c for c in candidates if f"{year}.12" in c.get("report_nm", "")]
    pool = exact or candidates
    pool.sort(key=lambda c: c.get("rcept_no", ""), reverse=True)
    return pool[0]["rcept_no"]


def fetch_report_document_text(rcept_no, name=None, year=None):
    """사업보고서 원본 문서(document.xml, zip)를 받아 태그를 제거한 순수 텍스트로 반환한다."""
    params = {"crtfc_key": API_KEY, "rcept_no": rcept_no}
    resp = requests.get(f"{BASE_URL}/document.xml", params=params, timeout=60)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        raw = zf.read(zf.namelist()[0])
    for encoding in ("utf-8", "cp949"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="ignore")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    if DEBUG_DUMP and name and year:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        idx = text.find("연구개발비용")
        snippet = text[max(0, idx - 200):idx + 1000] if idx != -1 else "(연구개발비용 문구를 찾지 못함)"
        with open(os.path.join(DEBUG_DIR, f"{name}_{year}_rnd_snippet.txt"), "w", encoding="utf-8") as f:
            f.write(snippet)
    return text


def fetch_rnd_expense(corp_code, year, name=None):
    """사업보고서 "주요계약 및 연구개발활동"(또는 "연구개발활동") 표에서
    "연구개발비용 계" 행의 당기 금액을 읽어온다.

    "사업의 내용" 하위 항목으로 들어있는 경우와, 독립된 장으로 분리되어 있는
    경우를 모두 찾는다. 표를 찾지 못하거나 금액을 확실히 특정할 수 없으면
    None을 반환해 해당 칸을 비워 둔다 (억지로 채우지 않는다).
    """
    try:
        rcept_no = find_business_report_rcept_no(corp_code, year, name=name)
        if not rcept_no:
            return None
        text = fetch_report_document_text(rcept_no, name=name, year=year)
    except Exception as e:
        print(f"  [연구개발비 문서 조회 실패] {name} {year}: {e}")
        return None

    # "사업의 내용"의 하위 항목("6. 주요계약 및 연구개발활동")이든, 독립된
    # 장("주요계약 및 연구개발활동")이든 상관없이 "연구개발비용 계" 행 자체를
    # 직접 찾는다 — 이 라벨은 목차 등에는 나오지 않는 실제 표의 행 이름이라
    # 어느 위치에 있든 이 방식이면 잡힌다.
    row_match = re.search(r"연구개발비용?\s*계([^가-힣]{0,200})", text)
    if not row_match:
        return None

    numbers = re.findall(r"-?[0-9][0-9,]*(?:\.[0-9]+)?", row_match.group(1))
    if not numbers:
        return None

    amount_str = numbers[0].replace(",", "")
    try:
        amount = float(amount_str) if "." in amount_str else int(amount_str)
    except ValueError:
        return None

    unit_search_start = max(0, row_match.start() - 3000)
    unit_window = text[unit_search_start:row_match.start()]
    unit_match = None
    for m in re.finditer(r"단위\s*[:：]\s*(백만원|천원|원)", unit_window):
        unit_match = m
    if unit_match is None:
        # 단위 표시를 못 찾으면 잘못 스케일링할 위험이 있으므로 채우지 않는다.
        return None

    scale = {"원": 1, "천원": 1_000, "백만원": 1_000_000}[unit_match.group(1)]
    return int(amount * scale)


def fetch_employee_count(corp_code, year, name=None):
    """사업보고서 '임원 및 직원 현황 > 직원 현황'의 총 인원수를 구한다.

    DART API는 사업부문/성별별 세부 행만 내려주고, 화면에 보이는 "합 계" 행은
    DART 웹뷰어가 화면 표시용으로 계산해서 보여주는 것일 뿐 API 응답에는
    별도로 포함되지 않는다. 따라서 모든 세부 행의 '합계' 열(sm)을 그대로
    더하면 된다.
    """
    params = {
        "crtfc_key": API_KEY,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": REPORT_CODE,
    }
    res = requests.get(f"{BASE_URL}/empSttus.json", params=params, timeout=30).json()
    dump_debug(name, year, "emp", res)
    if res.get("status") != "000":
        print(f"  [직원현황 조회 실패] {name} {year}: status={res.get('status')} message={res.get('message')}")
        return None

    total = 0
    found = False
    for item in res["list"]:
        count = to_int(item.get("sm"))
        if count is not None:
            total += count
            found = True

    if not found:
        print(f"  [직원수 못 찾음] {name} {year}: 응답={res['list']}")
        return None
    return total


def main():
    xml_text = load_corp_code_xml()
    corp_codes = {name: find_corp_code(xml_text, name) for name in COMPANIES}
    print("고유번호:", corp_codes)

    rows = []
    for name in COMPANIES:
        corp_code = corp_codes[name]
        for year in YEARS:
            revenue, tangible_assets, fs_div = fetch_financials(corp_code, year, name=name)
            time.sleep(0.2)
            employees = fetch_employee_count(corp_code, year, name=name)
            time.sleep(0.2)
            rows.append(
                {
                    "회사": name,
                    "연도": year,
                    "매출액": revenue,
                    "유형자산": tangible_assets,
                    "직원수": employees,
                    "재무제표기준": fs_div,
                }
            )
            print(rows[-1])

    if not SAVE_FILES:
        print("\n(엑셀 파일은 저장하지 않았습니다. 저장하려면 DART_SAVE_FILES=1로 다시 실행하세요.)")
        return

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "DART재무데이터"
    headers = ["회사", "연도", "매출액", "유형자산", "직원수", "재무제표기준(연결/개별)"]
    ws.append(headers)
    for row in rows:
        ws.append(
            [
                row["회사"],
                row["연도"],
                row["매출액"],
                row["유형자산"],
                row["직원수"],
                row["재무제표기준"],
            ]
        )
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dart_financial_data.xlsx")
    wb.save(out_path)
    print(f"저장 완료: {out_path}")


if __name__ == "__main__":
    main()
