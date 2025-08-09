# 대한수사회 공고 인턴, 1년차 구인 정보 수집
# https://www.kvma.or.kr/
# Playwright를 사용하여 웹 스크래핑
# Python 3.8 이상 필요
# 설치: pip install playwright python-dotenv pandas
# playwright install
# 사용법: 환경변수 KVMA_ID, KVMA_PW에 로그인 정보 입력 후 실행


from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import os
import time
from datetime import datetime, timedelta
import csv
import pandas as pd


LOOKBACK_DAYS = 30

def parse_date(text: str):
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None

def within_lookback(dt: datetime | None, days: int = LOOKBACK_DAYS):
    if dt is None:
        return False
    return dt >= (datetime.now() - timedelta(days=days))

def resolve_link(page, href: str | None) -> str:
    if not href:
        return ""
    href = href.strip()
    if href.startswith("http"):
        return href
    base = page.url.split('/kvma/')[0]
    if href.startswith('/'):
        return f"{base}{href}"
    return f"{base}/kvma/{href}"

# === Helper functions for safe extraction and robust list selection ===
def safe_text(page, selector, timeout=1500):
    loc = page.locator(selector)
    try:
        if loc.count():
            return (loc.first.inner_text(timeout=timeout) or "").strip()
    except Exception:
        pass
    return ""

KEYWORDS = ("1년차", "인턴")

def click_first_matching_post(page):
    """On the list page, click the first row whose title contains any KEYWORDS. Return True if clicked."""
    rows = page.locator("#listform table tbody tr")
    if not rows.count():
        rows = page.locator("table.tb tbody tr, table tbody tr")
    n = rows.count()
    for i in range(n):
        tr = rows.nth(i)
        if tr.locator("th").count() > 0:
            continue
        tds = tr.locator("td")
        if tds.count() < 2:
            continue
        title_el = tds.nth(1).locator("a") if tds.nth(1).locator("a").count() else tds.nth(1)
        try:
            title = title_el.inner_text(timeout=1500).strip()
        except Exception:
            title = ""
        if any(k in title for k in KEYWORDS):
            title_el.click()
            page.wait_for_load_state("networkidle")
            return True
    return False

def collect_list_rows(page):
    rows = []
    table = page.locator("#listform table tbody tr")
    if not table.count():
        table = page.locator("table.tb tbody tr, table tbody tr")
    n = table.count()
    for i in range(n):
        tr = table.nth(i)
        if tr.locator("th").count() > 0:
            continue
        tds = tr.locator("td")
        if tds.count() < 4:
            continue
        title_el = tds.nth(1)
        a = title_el.locator("a")
        title = (a.first.inner_text(timeout=1000).strip() if a.count() else title_el.inner_text(timeout=1000).strip())
        href = (a.first.get_attribute("href") if a.count() else None)
        link = resolve_link(page, href)
        date_text = tds.nth(3).inner_text(timeout=1000).strip()
        dt = parse_date(date_text)
        rows.append({
            "날짜": dt.strftime("%Y-%m-%d") if dt else date_text,
            "제목": title,
            "링크": link,
            "_dt": dt
        })
    return rows

# 환경변수 로드
load_dotenv()
ID = os.getenv("KVMA_ID")
PW = os.getenv("KVMA_PW")

with sync_playwright() as p:
    # Chromium 브라우저 실행 (headless=False → 창 보이게)
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()

    # 페이지 열기
    page = context.new_page()
    page.goto("https://www.kvma.or.kr/")

    # 네이버 로그인 입력창에 값 입력 (사람처럼 delay)
    page.locator("#username").click()
    page.locator("#username").fill(ID, timeout=3000)
    time.sleep(0.5)
    page.locator("#password").click()
    page.locator("#password").fill(PW, timeout=3000)
    time.sleep(0.5)

    # 로그인 버튼 클릭
    page.click("#ct > div > div > ul > form > button")

    # 로그인 후 페이지 대기 (예: 메인 페이지로 이동 대기)
    page.wait_for_timeout(5000)

    # ✅ 현재 URL 출력 (로그인 성공 여부 확인용)
    print("현재 URL:", page.url)
    # '채용매매' 메뉴 클릭
    page.click("text=채용매매")
    page.wait_for_load_state("networkidle")
    print("채용매매 페이지 URL:", page.url)

    # '채용매매' 페이지에서 '수의사 구인' 클릭
    page.click("text=수의사 구인")
    page.wait_for_load_state("networkidle")
    print("수의사 구인 페이지 URL:", page.url)
    # '수의사 구인' 페이지에서 '구인정보 검색' 클릭
    page.locator("#findtext").click()
    # '구인정보 검색' 페이지에서 검색어 입력
    page.locator("#findtext").fill("1년차", timeout=3000)
    # 검색 버튼 클릭
    page.click("#ct > div > div.content > div.srch-bx.text-right.form-inline > input.btn.bg-blue")
    # 검색 결과 페이지 대기
    page.wait_for_load_state("networkidle")

    # ==============================
    # 최근 30일 & ('1년차'|'인턴')만 수집 (목록 기반)
    # ==============================
    kept = []
    for _ in range(50):  # 안전장치: 최대 50페이지
        page.wait_for_load_state("networkidle")
        time.sleep(0.5)
        rows = collect_list_rows(page)
        print(f"[DEBUG] rows on page = {len(rows)}")
        if not rows:
            break
        # 필터 적용
        for r in rows:
            title = r.get("제목", "")
            dt = r.get("_dt")
            if any(k in title for k in KEYWORDS) and within_lookback(dt):
                kept.append({k: r[k] for k in ("날짜","제목","링크")})
        # 다음 페이지 필요 여부: 페이지 내 최저 날짜가 lookback 안이면 다음으로
        dates = [r.get("_dt") for r in rows if r.get("_dt")]
        need_next = False
        if dates:
            oldest = min(dates)
            need_next = within_lookback(oldest)
        if not need_next:
            break
        # 페이지네이션: '다음' 또는 '>'
        moved = False
        for sel in ["text=다음", "a:has-text('>')", "a:has-text('Next')"]:
            try:
                page.click(sel, timeout=1500)
                page.wait_for_load_state("networkidle")
                moved = True
                break
            except Exception:
                continue
        if not moved:
            break

    # 프리뷰 출력
    print("[RESULT] 최근 30일 & (1년차|인턴) 매칭 항목:")
    for it in kept:
        print(f" - {it['날짜']} | {it['제목']} | {it['링크']}")
    # CSV 저장
    os.makedirs("data", exist_ok=True)
    out = os.path.join("data", f"kvma_jobs_list_{datetime.now().strftime('%Y%m%d')}.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["날짜","제목","링크"])
        w.writeheader(); w.writerows(kept)
    print(f"[SAVE] {out} ({len(kept)} rows)")

    # '수의사 구인' 페이지에서 '구인정보 검색' 클릭
    page.locator("#findtext").click()
    # '구인정보 검색' 페이지에서 검색어 입력
    page.locator("#findtext").fill("인턴", timeout=3000)
    # 검색 버튼 클릭
    page.click("#ct > div > div.content > div.srch-bx.text-right.form-inline > input.btn.bg-blue")
    # 검색 결과 페이지 대기
    page.wait_for_load_state("networkidle")

    # ==============================
    # 최근 30일 & ('1년차'|'인턴')만 수집 (목록 기반)
    # ==============================
    kept = []
    for _ in range(50):  # 안전장치: 최대 50페이지
        page.wait_for_load_state("networkidle")
        time.sleep(0.5)
        rows = collect_list_rows(page)
        print(f"[DEBUG] rows on page = {len(rows)}")
        if not rows:
            break
        # 필터 적용
        for r in rows:
            title = r.get("제목", "")
            dt = r.get("_dt")
            if any(k in title for k in KEYWORDS) and within_lookback(dt):
                kept.append({k: r[k] for k in ("날짜","제목","링크")})
        # 다음 페이지 필요 여부: 페이지 내 최저 날짜가 lookback 안이면 다음으로
        dates = [r.get("_dt") for r in rows if r.get("_dt")]
        need_next = False
        if dates:
            oldest = min(dates)
            need_next = within_lookback(oldest)
        if not need_next:
            break
        # 페이지네이션: '다음' 또는 '>'
        moved = False
        for sel in ["text=다음", "a:has-text('>')", "a:has-text('Next')"]:
            try:
                page.click(sel, timeout=1500)
                page.wait_for_load_state("networkidle")
                moved = True
                break
            except Exception:
                continue
        if not moved:
            break

    # 프리뷰 출력
    print("[RESULT] 최근 30일 & (1년차|인턴) 매칭 항목:")
    for it in kept:
        print(f" - {it['날짜']} | {it['제목']} | {it['링크']}")
    # CSV 저장
    os.makedirs("data", exist_ok=True)
    out = os.path.join("data", f"kvma_jobs_list_{datetime.now().strftime('%Y%m%d')}.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["날짜","제목","링크"])
        w.writeheader(); w.writerows(kept)
    print(f"[SAVE] {out} ({len(kept)} rows)")

df = pd.read_csv(out)
excel_out = out.replace(".csv", ".xlsx")
df.to_excel(excel_out, index=False)
print(f"[SAVE] {excel_out} ({len(df)} rows)")