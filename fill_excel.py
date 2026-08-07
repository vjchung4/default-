"""
기존 엑셀 파일(종목코드/기업명/연도/매출액/유형자산/연구개발비/직원수/산업 형식)에서
비어 있는 매출액/유형자산/직원수 칸만 DART Open API로 채워 넣는다.

이미 값이 채워진 칸은 절대 건드리지 않는다. 연구개발비/산업/종목코드는
이 스크립트가 다루지 않는다.

사용법:
    set DART_API_KEY=발급받은키
    python fill_excel.py 입력파일.xlsx [출력파일.xlsx]

출력파일을 생략하면 "입력파일_filled.xlsx" 로 저장한다 (원본은 건드리지 않음).
"""

import sys

from openpyxl import load_workbook

from dart_financial_data import (
    fetch_employee_count,
    fetch_financials,
    find_corp_code,
    load_corp_code_xml,
)

# 시트에 등장하는 기업명이 DART 공식 회사명과 다르면 여기에 매핑을 추가한다.
NAME_ALIASES = {
    "두산퓨어셀": "두산퓨얼셀",  # 정식 사명은 "두산퓨얼셀"
}

COL_CORP_CODE = 1
COL_NAME = 2
COL_YEAR = 3
COL_REVENUE = 4
COL_TANGIBLE = 5
COL_RND = 6
COL_EMPLOYEES = 7
COL_INDUSTRY = 8


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: python fill_excel.py 입력파일.xlsx [출력파일.xlsx]")
    in_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else in_path.rsplit(".", 1)[0] + "_filled.xlsx"

    wb = load_workbook(in_path)
    ws = wb.active

    # 기업명은 각 회사 블록의 첫 행에만 적혀 있고 그 아래는 비어 있으므로 채워 내려간다.
    current_name = None
    rows = []
    for r in range(2, ws.max_row + 1):
        name_cell = ws.cell(r, COL_NAME).value
        if name_cell:
            current_name = name_cell.strip()
        year = ws.cell(r, COL_YEAR).value
        if current_name and year:
            rows.append((r, current_name, int(year)))

    xml_text = load_corp_code_xml()
    corp_code_cache = {}

    def get_corp_code(name):
        if name not in corp_code_cache:
            lookup_name = NAME_ALIASES.get(name, name)
            corp_code_cache[name] = find_corp_code(xml_text, lookup_name)
        return corp_code_cache[name]

    financials_cache = {}

    # "N/A"는 그 해에 회사가 존재하지 않았다는 의도적인 표시이므로 빈 칸으로 취급하지 않는다.
    EMPTY_MARKERS = (None, "")

    filled = 0
    for r, name, year in rows:
        need_revenue = ws.cell(r, COL_REVENUE).value in EMPTY_MARKERS
        need_tangible = ws.cell(r, COL_TANGIBLE).value in EMPTY_MARKERS
        need_employees = ws.cell(r, COL_EMPLOYEES).value in EMPTY_MARKERS

        if not (need_revenue or need_tangible or need_employees):
            continue

        try:
            corp_code = get_corp_code(name)
        except ValueError as e:
            print(f"[건너뜀] {name} {year}: {e}")
            continue

        row_filled = 0

        if need_revenue or need_tangible:
            key = (corp_code, year)
            if key not in financials_cache:
                financials_cache[key] = fetch_financials(corp_code, year, name=name)
            revenue, tangible, fs_div = financials_cache[key]
            if need_revenue and revenue is not None:
                ws.cell(r, COL_REVENUE).value = revenue
                row_filled += 1
            if need_tangible and tangible is not None:
                ws.cell(r, COL_TANGIBLE).value = tangible
                row_filled += 1

        if need_employees:
            employees = fetch_employee_count(corp_code, year, name=name)
            if employees is not None:
                ws.cell(r, COL_EMPLOYEES).value = employees
                row_filled += 1

        if row_filled:
            print(f"{name} {year} 처리 완료 ({row_filled}칸)")
        else:
            print(f"[값 없음] {name} {year}: DART에 해당 연도 데이터가 없어 그대로 둠")
        filled += row_filled

    wb.save(out_path)
    print(f"\n{filled}개 칸을 채웠습니다. 저장 위치: {out_path}")


if __name__ == "__main__":
    main()
