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

COMPANIES = ["삼성SDI", "SK이노베이션", "DB하이텍"]
YEARS = list(range(2018, 2026))
REPORT_CODE = "11011"  # 사업보고서(연간)
REVENUE_ACCOUNT_NAMES = {"매출액", "수익(매출액)"}
TANGIBLE_ASSET_ACCOUNT_NAMES = {"유형자산"}
TOTAL_ROW_MARKERS = {"합계", "계", "합 계", "총계"}
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
    for block in re.findall(r"<list>(.*?)</list>", xml_text, re.S):
        name = re.search(r"<corp_name>(.*?)</corp_name>", block).group(1).strip()
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
    """해당 연도 매출액(손익/포괄손익계산서)과 유형자산(재무상태표)을 (연결 우선, 없으면 개별) 가져온다."""
    # 사업보고서 본문의 "4. 재무제표"(개별/별도)를 기준으로 삼는다.
    # 앞쪽 "연결재무제표"와 다른 표이므로 OFS를 먼저 시도한다.
    for fs_div in ("OFS", "CFS"):
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
            continue

        revenue = tangible_assets = None
        for item in res["list"]:
            account_nm = item.get("account_nm", "").strip()
            sj_div = item.get("sj_div", "").strip()  # BS=재무상태표, IS/CIS=손익/포괄손익계산서
            if sj_div in ("IS", "CIS") and account_nm in REVENUE_ACCOUNT_NAMES and revenue is None:
                revenue = to_int(item.get("thstrm_amount"))
            elif sj_div == "BS" and account_nm in TANGIBLE_ASSET_ACCOUNT_NAMES and tangible_assets is None:
                tangible_assets = to_int(item.get("thstrm_amount"))
        if revenue is not None or tangible_assets is not None:
            return revenue, tangible_assets, fs_div
    return None, None, None


def fetch_employee_count(corp_code, year, name=None):
    """사업보고서 '임원 및 직원 현황 > 직원 현황'의 총 인원수를 구한다.

    사업부문별 세부 행과 별도로, 사업부문(fo_bbm)이 '합계'류인 행에 이미
    전체 인원수가 적혀 있으므로 세부 행은 무시하고 합계 행만 사용한다.
    성별(남/여)로 나뉜 합계 행이 각각 있으면 둘을 더해서 전체 인원수를 낸다.
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
        return None

    total_rows = []
    for item in res["list"]:
        fo_bbm = (item.get("fo_bbm") or "").strip()
        if fo_bbm not in TOTAL_ROW_MARKERS:
            continue
        count = to_int(item.get("sm"))
        if count is not None:
            total_rows.append((item.get("sexdstn", "").strip(), count))

    if not total_rows:
        return None

    sex_values = {sex for sex, _ in total_rows}
    if sex_values <= {"남", "여"}:
        return sum(c for _, c in total_rows)
    return total_rows[-1][1]


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
