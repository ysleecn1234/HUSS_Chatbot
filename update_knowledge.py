"""
HUSS 글로벌 공생 챗봇 — 동적 지식 베이스 자동 업데이트 스크립트

사용법:
  python update_knowledge.py

이 스크립트는 아래 사이트들을 스크래핑하여 knowledge_dynamic.js를 갱신합니다:
  1) husslms.ac.kr   — 교과목 정보 (5개 대학)
  2) huss.kw.ac.kr   — 광운대 HUSS 공지사항/프로그램/일정
  3) climate.ac.kr    — 국민대 기후변화대응사업단 뉴스/행사

GitHub Actions에서 4일마다 자동 실행됩니다.

필요 패키지:
  pip install requests beautifulsoup4
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os
import re
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "knowledge_dynamic.js")
BACKUP_DIR = os.path.join(SCRIPT_DIR, "kb_backups")

URLS = {
    # 교과목 정보
    "글로벌공생_소개": "https://husslms.ac.kr/intro/intro_symbiosis",
    # 광운대 HUSS 공지사항 (날짜 포함)
    "광운대_공지": "https://huss.kw.ac.kr/bulletin/notice.php",
    # 광운대 HUSS 메인 (일정 + 우수성과)
    "광운대_메인": "https://huss.kw.ac.kr/",
    # 국민대 기후변화대응사업단 메인 (뉴스 + 행사)
    "국민대_메인": "https://www.climate.ac.kr/",
    # 국민대 공지사항
    "국민대_공지": "https://www.climate.ac.kr/ko/news/notice",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_page(url, timeout=15):
    """URL에서 HTML 페이지를 가져옵니다."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    except Exception as e:
        print(f"  [경고] {url} 가져오기 실패: {e}")
        return None


# ============================================================
# 1) 교과목 추출 (husslms.ac.kr — 기존 유지)
# ============================================================
def extract_courses_from_intro(html):
    """글로벌 공생 소개 페이지에서 학교별 교과목 테이블을 추출합니다."""
    soup = BeautifulSoup(html, "html.parser")
    result = {}

    university_names = ["광운대학교", "국민대학교", "선문대학교", "영남대학교", "호남대학교"]
    tables = soup.find_all("table")

    for i, table in enumerate(tables):
        if i >= len(university_names):
            break

        uni_name = university_names[i]
        rows = table.find_all("tr")
        existing_courses = []
        new_courses = []
        current_section = "기존"

        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            first_cell = cells[0].get_text(strip=True)
            if "신규" in first_cell:
                current_section = "신규"
            elif "기존" in first_cell or "개편" in first_cell:
                current_section = "기존"

            course_name = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            professor = cells[-1].get_text(strip=True) if len(cells) > 4 else ""

            if course_name and course_name not in ["교과목명", "구분"]:
                entry = f"{course_name}({professor})" if professor else course_name
                if current_section == "신규":
                    new_courses.append(entry)
                else:
                    existing_courses.append(entry)

        result[uni_name] = {
            "existing": existing_courses,
            "new": new_courses
        }

    return result


# ============================================================
# 2) 광운대 HUSS 공지사항 추출 (huss.kw.ac.kr)
# ============================================================
def extract_kw_notices(html, max_count=20):
    """광운대 HUSS 공지사항을 날짜와 함께 추출합니다."""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    notices = []

    # 테이블 구조: 번호 | 제목 | 등록일 | 작성자 | 조회수
    rows = soup.select("table tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        # 제목 추출 (두 번째 컬럼의 링크)
        title_cell = cells[1] if len(cells) > 1 else None
        if not title_cell:
            continue

        link = title_cell.find("a")
        if not link:
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 3 or title in ["제목"]:
            continue

        # 날짜 추출 (세 번째 컬럼)
        date_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""

        # URL 추출
        href = link.get("href", "")
        if href and not href.startswith("http"):
            href = f"https://huss.kw.ac.kr{href}" if href.startswith("/") else f"https://huss.kw.ac.kr/bulletin/{href}"

        # 번호 (공지/숫자)
        num = cells[0].get_text(strip=True)

        notices.append({
            "title": title,
            "date": date_text,
            "url": href,
            "pinned": num == "공지"
        })

        if len(notices) >= max_count:
            break

    return notices


def extract_kw_notice_detail(html):
    """개별 공지 페이지에서 상세 내용을 추출합니다."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # 본문 영역 찾기: 보통 에디터 콘텐츠 영역
    # huss.kw.ac.kr은 게시판 본문이 특정 div 안에 있음
    content_area = None

    # 방법 1: 에디터 이미지/텍스트가 포함된 영역
    for div in soup.find_all(["div", "td"]):
        text = div.get_text(strip=True)
        # 본문 특징: 참가대상, 신청기간, 모집인원 등 키워드 포함
        keywords = ["참가대상", "신청기간", "모집 대상", "모집 인원", "선발인원",
                     "신청방법", "행사 일시", "행사 장소", "접수기간", "지원자격"]
        if any(kw in text for kw in keywords) and len(text) > 50:
            content_area = div
            break

    if not content_area:
        return ""

    # 핵심 정보만 추출
    text = content_area.get_text(separator="\n", strip=True)
    lines = text.split("\n")

    detail_lines = []
    target_keys = ["참가대상", "모집 대상", "모집대상", "대상", "선발인원", "모집 인원",
                    "모집인원", "신청기간", "접수기간", "신청 기간", "신청방법", "신청 방법",
                    "행사 일시", "행사일시", "행사 장소", "행사장소", "기간", "일시", "장소",
                    "지원자격", "프로그램 기간", "문의"]

    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue
        # 키워드가 포함된 줄만 추출
        for key in target_keys:
            if key in line:
                # 줄이 너무 길면 자르기
                if len(line) > 150:
                    line = line[:150] + "..."
                detail_lines.append(line)
                break

    return "\n".join(detail_lines[:8])  # 최대 8줄


def crawl_notice_details(notices, max_detail=10):
    """공지 목록에서 상위 N개의 상세 페이지를 크롤링합니다."""
    import time

    for i, notice in enumerate(notices):
        if i >= max_detail:
            break

        # 이미 마감된 것은 건너뛰기 (선택)
        url = notice.get("url", "")
        if not url:
            continue

        print(f"  상세 크롤링 [{i+1}/{min(len(notices), max_detail)}]: {notice['title'][:30]}...")
        detail_html = fetch_page(url)
        if detail_html:
            detail = extract_kw_notice_detail(detail_html)
            notice["detail"] = detail
        else:
            notice["detail"] = ""

        # 서버 부하 방지
        time.sleep(0.5)

    return notices


def extract_kw_schedule(html):
    """광운대 메인 페이지에서 사업단 일정을 추출합니다."""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    schedules = []

    # 일정 텍스트 찾기 (날짜 패턴: MM.DD ~ MM.DD)
    text = soup.get_text()
    # 패턴: 05.06 ~ 05.06 <줄바꿈> 이벤트명
    schedule_pattern = re.findall(
        r'(\d{2}\.\d{2})\s*~\s*(\d{2}\.\d{2})\s*\n\s*(.+?)(?:\n|$)',
        text
    )
    for start, end, event in schedule_pattern:
        event = event.strip()
        if event and len(event) > 3:
            schedules.append({
                "period": f"{start} ~ {end}",
                "event": event
            })

    return schedules


# ============================================================
# 3) 국민대 기후변화대응사업단 뉴스 추출 (climate.ac.kr)
# ============================================================
def extract_kookmin_news(html, max_count=10):
    """국민대 기후변화대응사업단 메인 페이지에서 뉴스를 추출합니다."""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    news_items = []

    # 사업단 뉴스 섹션의 링크들
    news_links = soup.select("a[href*='/ko/news/']")
    seen = set()
    for link in news_links:
        title = link.get_text(strip=True)
        href = link.get("href", "")

        if not title or len(title) < 10 or title in seen:
            continue
        # 메뉴 링크 제외
        if title in ["공지사항", "사업단 뉴스", "활동사진", "행사/이벤트", "사업단 일정", "뉴스레터", "더보기 ->"]:
            continue

        seen.add(title)

        # 날짜 추출: 제목 다음 텍스트 또는 부모 요소에서
        date_text = ""
        parent = link.find_parent()
        if parent:
            full_text = parent.get_text()
            date_match = re.search(r'(\d{4}[-./]\d{2}[-./]\d{2})', full_text)
            if date_match:
                date_text = date_match.group(1).replace("/", "-").replace(".", "-")

        if href and not href.startswith("http"):
            href = f"https://www.climate.ac.kr{href}"

        news_items.append({
            "title": title,
            "date": date_text,
            "url": href
        })

        if len(news_items) >= max_count:
            break

    return news_items


def extract_kookmin_activities(html, max_count=5):
    """국민대 기후변화대응사업단 메인 페이지에서 활동사진/행사를 추출합니다."""
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    activities = []

    # 활동사진 섹션의 링크들
    photo_links = soup.select("a[href*='/ko/news/photo/view/']")
    seen = set()
    for link in photo_links:
        title = link.get_text(strip=True)
        if not title or len(title) < 10 or title in seen:
            continue
        seen.add(title)

        date_text = ""
        parent = link.find_parent()
        if parent:
            full_text = parent.get_text()
            date_match = re.search(r'(\d{4}[-./]\d{2}[-./]\d{2})', full_text)
            if date_match:
                date_text = date_match.group(1).replace("/", "-").replace(".", "-")

        activities.append({
            "title": title,
            "date": date_text,
        })

        if len(activities) >= max_count:
            break

    return activities


# ============================================================
# 백업 & 빌드
# ============================================================
def backup_existing():
    """기존 파일을 백업합니다."""
    if os.path.exists(OUTPUT_FILE):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"knowledge_dynamic_{timestamp}.js")
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  백업 완료: {backup_path}")
        except Exception as e:
            print(f"  [경고] 백업 실패: {e}")


def build_dynamic_knowledge(courses, kw_notices, kw_schedules, km_news, km_activities):
    """동적 지식 베이스 문자열을 생성합니다."""
    sections = []
    today = datetime.now().strftime("%Y-%m-%d")

    # ── 교과목 정보 ──
    uni_display = {
        "광운대학교": "광운대학교",
        "국민대학교": "국민대학교",
        "선문대학교": "선문대학교",
        "영남대학교": "영남대학교",
        "호남대학교": "호남대학교"
    }

    for uni_name, display_name in uni_display.items():
        if uni_name in courses:
            data = courses[uni_name]
            section = f"【{display_name} 교과목 — 최신】"

            if data["existing"]:
                section += f"\n■ 기존/개편 과목 ({len(data['existing'])}개):\n"
                section += ", ".join(data["existing"])

            if data["new"]:
                section += f"\n\n■ 신규 과목 ({len(data['new'])}개):\n"
                section += ", ".join(data["new"])

            sections.append(section)

    # ── 광운대 HUSS 공지사항/프로그램 (날짜 + 상세 포함) ──
    if kw_notices:
        notice_section = "【광운대 HUSS 최근 공지사항/프로그램 모집】\n"
        notice_section += f"(업데이트: {today})\n"
        for n in kw_notices:
            pin = "[공지] " if n.get("pinned") else ""
            notice_section += f"\n■ {pin}{n['title']} ({n['date']})"
            detail = n.get("detail", "")
            if detail:
                notice_section += f"\n{detail}"
            url = n.get("url", "")
            if url:
                notice_section += f"\n→ 상세: {url}"
            notice_section += "\n"
        notice_section += "\n※ 전체 공지: https://huss.kw.ac.kr/bulletin/notice.php"
        sections.append(notice_section)

    # ── 광운대 HUSS 사업단 일정 ──
    if kw_schedules:
        sched_section = "【광운대 HUSS 사업단 일정】\n"
        for s in kw_schedules:
            sched_section += f"- {s['period']}: {s['event']}\n"
        sched_section += "\n※ 전체 일정: https://huss.kw.ac.kr/bulletin/schedule.php"
        sections.append(sched_section)

    # ── 국민대 기후변화대응사업단 뉴스 ──
    if km_news:
        km_section = "【국민대 기후변화대응사업단 최근 소식】\n"
        km_section += f"(업데이트: {today})\n"
        for n in km_news:
            date_str = f" ({n['date']})" if n.get('date') else ""
            km_section += f"- {n['title']}{date_str}\n"
        km_section += "\n※ 전체 소식: https://www.climate.ac.kr/ko/news/press"
        sections.append(km_section)

    # ── 국민대 최근 활동 ──
    if km_activities:
        act_section = "【국민대 기후변화대응사업단 최근 활동】\n"
        for a in km_activities:
            date_str = f" ({a['date']})" if a.get('date') else ""
            act_section += f"- {a['title']}{date_str}\n"
        sections.append(act_section)

    # ── 참여대학별 참여학과 (정적이지만 크롤링 확인용) ──
    dept_section = """【참여대학별 참여학과 — 최신】
선문대(충청): 외국어학부, 경영학과, 국제관계학과, 글로벌 관광학부, 건축학부(건축학전공)
영남대(경상): 사회학과, 경영학과, 글로벌교육학부, 무역학과, 화학공학부
호남대(전라): 교양대학 교양학부, 경영학부, 관광경영학과, 글로벌 한국어교육학과, 토목환경공학과"""
    sections.append(dept_section)

    # ── 폴백: 공지가 전혀 없을 때 ──
    if not kw_notices and not km_news:
        sections.append("【최근 공지사항】\n※ 광운대: https://huss.kw.ac.kr/bulletin/notice.php\n※ 국민대: https://www.climate.ac.kr/ko/news/notice")

    return "\n\n".join(sections)


def write_js_file(knowledge_text):
    """knowledge_dynamic.js 파일을 생성합니다."""
    today = datetime.now().strftime("%Y-%m-%d")

    escaped = knowledge_text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

    js_content = f"""// 동적 지식 베이스 — update_knowledge.py가 자동 생성하는 파일
// 마지막 업데이트: {today}
// 출처: husslms.ac.kr, huss.kw.ac.kr, climate.ac.kr

const KNOWLEDGE_DYNAMIC = `{escaped}`;
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"  저장 완료: {OUTPUT_FILE}")


def update_html_inline(knowledge_text):
    """index.html 내부의 인라인 KNOWLEDGE_DYNAMIC도 업데이트합니다."""
    html_file = os.path.join(SCRIPT_DIR, "index.html")
    if not os.path.exists(html_file):
        print("  [경고] index.html을 찾을 수 없습니다.")
        return

    with open(html_file, "r", encoding="utf-8") as f:
        html = f.read()

    # index.html에서는 템플릿 리터럴(백틱)을 사용하므로 백틱과 \n을 이스케이프 처리
    escaped_backtick = knowledge_text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    old_pattern = re.compile(r"var KNOWLEDGE_DYNAMIC = `.*?`;", re.DOTALL)
    new_value = f"var KNOWLEDGE_DYNAMIC = `{escaped_backtick}`;"

    if old_pattern.search(html):
        html = old_pattern.sub(new_value, html)
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  index.html 인라인 데이터 업데이트 완료")
    else:
        print("  [경고] index.html에서 인라인 KNOWLEDGE_DYNAMIC을 찾을 수 없습니다.")


def main():
    print("=" * 60)
    print("HUSS 동적 지식 베이스 업데이트 시작")
    print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 기존 파일 백업
    print("\n[1/6] 기존 파일 백업...")
    backup_existing()

    # 2. 교과목 정보 크롤링 (husslms.ac.kr)
    print("\n[2/6] 교과목 정보 크롤링 (husslms.ac.kr)...")
    intro_html = fetch_page(URLS["글로벌공생_소개"])
    courses = {}
    if intro_html:
        courses = extract_courses_from_intro(intro_html)
        for uni, data in courses.items():
            print(f"  {uni}: 기존 {len(data['existing'])}개 + 신규 {len(data['new'])}개")
    else:
        print("  [경고] 소개 페이지를 가져오지 못했습니다.")

    # 3. 광운대 HUSS 공지사항 크롤링 (huss.kw.ac.kr)
    print("\n[3/6] 광운대 HUSS 공지사항 크롤링...")
    kw_notice_html = fetch_page(URLS["광운대_공지"])
    kw_notices = extract_kw_notices(kw_notice_html) if kw_notice_html else []
    print(f"  광운대 공지 {len(kw_notices)}개 추출")
    for n in kw_notices[:5]:
        print(f"    - [{n['date']}] {n['title'][:40]}...")

    # 3-2. 광운대 공지 상세 페이지 크롤링
    if kw_notices:
        print(f"\n[3-2/6] 광운대 공지 상세 크롤링 (상위 10개)...")
        kw_notices = crawl_notice_details(kw_notices, max_detail=10)
        detailed = sum(1 for n in kw_notices if n.get("detail"))
        print(f"  상세 정보 추출: {detailed}개")

    # 4. 광운대 HUSS 메인에서 일정 추출
    print("\n[4/6] 광운대 HUSS 사업단 일정 크롤링...")
    kw_main_html = fetch_page(URLS["광운대_메인"])
    kw_schedules = extract_kw_schedule(kw_main_html) if kw_main_html else []
    print(f"  사업단 일정 {len(kw_schedules)}개 추출")
    for s in kw_schedules:
        print(f"    - {s['period']}: {s['event']}")

    # 5. 국민대 기후변화대응사업단 뉴스/활동 크롤링
    print("\n[5/6] 국민대 기후변화대응사업단 크롤링...")
    km_main_html = fetch_page(URLS["국민대_메인"])
    km_news = extract_kookmin_news(km_main_html) if km_main_html else []
    km_activities = extract_kookmin_activities(km_main_html) if km_main_html else []
    print(f"  국민대 뉴스 {len(km_news)}개, 활동 {len(km_activities)}개 추출")
    for n in km_news[:3]:
        print(f"    - [{n.get('date', '?')}] {n['title'][:40]}...")

    # 6. JS 파일 + HTML 인라인 업데이트
    print("\n[6/6] knowledge_dynamic.js 생성 + index.html 업데이트...")
    if courses or kw_notices or km_news:
        knowledge_text = build_dynamic_knowledge(
            courses, kw_notices, kw_schedules, km_news, km_activities
        )
        write_js_file(knowledge_text)
        update_html_inline(knowledge_text)
        print("\n✅ 업데이트 완료!")
    else:
        print("\n⚠️ 크롤링 데이터가 없어 기존 파일을 유지합니다.")

    print("=" * 60)


if __name__ == "__main__":
    main()
