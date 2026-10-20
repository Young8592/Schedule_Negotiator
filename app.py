from __future__ import annotations

import calendar
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

import pandas as pd
import streamlit as st

from core import PRIORITIES, Store, find_candidates, today

st.set_page_config(page_title="시간표 네고시에이터", page_icon="◷", layout="wide", initial_sidebar_state="expanded")
ROOT = Path(__file__).resolve().parent
@st.cache_resource
def get_store(path):
    return Store(path)

database_url = os.environ.get("DATABASE_URL", "")
if not database_url:
    try:
        database_url = st.secrets.get("DATABASE_URL", "")
    except FileNotFoundError:
        database_url = ""
store = get_store(database_url or os.environ.get("SCHEDULE_DB", str(ROOT / "data" / "schedule.db")))
store.delete_expired_meetings()

st.markdown("""<style>
html, body, [class*="css"], .stApp {font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;}
.stApp {background:#f5f7fb;color:#172033;}
.block-container {max-width:1200px;padding-top:3rem;padding-bottom:4rem;}
h1 {font-weight:700!important;letter-spacing:-.06em;font-size:3rem!important;color:#111827!important;}
h2,h3 {font-weight:700!important;letter-spacing:-.04em;color:#172033!important;}
.title-row {display:flex;align-items:baseline;gap:18px;flex-wrap:wrap;margin:.1rem 0 1rem;}
.page-title {font-size:3rem;font-weight:700;line-height:1.15;letter-spacing:-.06em;}
.creator {font-size:16pt;font-weight:500;letter-spacing:-.04em;white-space:nowrap;}
p, label, [data-testid="stCaptionContainer"] {color:#4b5565;}
.eyebrow {font-family:monospace;font-size:.76rem;font-weight:700;letter-spacing:.22em;color:#2563eb;margin-bottom:1rem;}
.lede {font-size:1.08rem;line-height:1.85;color:#475569;max-width:760px;margin-bottom:2rem;}
.rule {height:1px;background:#d9e1ee;margin:1.6rem 0;}
.step {font:.76rem monospace;font-weight:700;color:#2563eb;letter-spacing:.12em;}
.flow {display:flex;align-items:stretch;justify-content:center;gap:10px;margin:1.4rem 0 2rem;}
.flow-step {flex:1;text-align:center;background:#fff;border:1px solid #dbe3ef;border-radius:14px;padding:20px 12px;box-shadow:0 2px 8px rgba(15,23,42,.05);}
.flow-icon {font-size:2rem;line-height:1;margin-bottom:12px;}
.flow-title {font-weight:700;color:#172033;margin-bottom:5px;}
.flow-copy {font-size:.82rem;color:#64748b;line-height:1.5;}
.flow-arrow {display:flex;align-items:center;color:#2563eb;font-size:1.5rem;font-weight:700;}
.feature-title {font-size:1rem;font-weight:700;letter-spacing:-.045em;line-height:1.35;white-space:nowrap;margin:0 0 .45rem;}
.calendar {display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:5px;margin:1rem 0 1.6rem;}
.day {border:1px solid #dbe3ef;min-height:92px;padding:12px 9px;border-radius:10px;background:#ffffff;box-shadow:0 1px 2px rgba(15,23,42,.04);}
.day.off {opacity:.42;background:#eef2f7;}
.day.today {border:2px solid #2563eb;background:#eff6ff;}
.day strong {font-size:1rem;font-weight:500;}
.day small {display:block;font-size:.72rem;color:#64748b;margin-top:10px;}
.weekday {text-align:center;color:#475569;font-size:.72rem;font-weight:700;padding:8px 0;}
.tag {display:inline-block;padding:4px 10px;border:1px solid #cbd5e1;border-radius:30px;font-size:.73rem;color:#334155;margin:0 6px 6px 0;background:#fff;}
div[data-testid="stMetric"] {background:#ffffff;border:1px solid #dbe3ef;border-radius:12px;padding:16px 18px;box-shadow:0 2px 8px rgba(15,23,42,.05);}
div[data-testid="stMetricValue"] {font-weight:700;color:#172033;}
div[data-testid="stForm"], div[data-testid="stVerticalBlockBorderWrapper"] {background:#ffffff;border-color:#dbe3ef!important;box-shadow:0 2px 10px rgba(15,23,42,.04);}
section[data-testid="stSidebar"] {background:#eef3f9;border-right:1px solid #d8e1ed;}
section[data-testid="stSidebar"] code {background:#ffffff;color:#172033;border:1px solid #cbd5e1;}
.stButton>button {border-radius:8px;border-color:#b8c5d8;background:#ffffff;color:#172033;}
.stButton>button:hover {border-color:#2563eb;color:#1d4ed8;}
button[kind="primary"] {background:#2563eb!important;border-color:#2563eb!important;}
button[kind="primary"], button[kind="primary"] p {color:#000000!important;}
div[data-baseweb="tab-list"] {gap:.35rem;}
button[data-baseweb="tab"] {background:#e9eef6;border-radius:8px 8px 0 0;padding-left:1rem;padding-right:1rem;}
button[data-baseweb="tab"][aria-selected="true"] {background:#ffffff;color:#1d4ed8;}
input, textarea {color:#172033!important;}
.stApp, .stApp * {color:#000000!important;}
@media(max-width:700px){h1{font-size:2.1rem!important}.page-title{font-size:2.1rem}.title-row{gap:10px}.block-container{padding-top:1.5rem}.day{padding:8px 4px;min-height:76px}.day small{font-size:.6rem}.flow{flex-direction:column}.flow-arrow{justify-content:center;transform:rotate(90deg)}}
</style>""", unsafe_allow_html=True)


def enter(token, access_code=None):
    st.session_state.clear()
    st.session_state.auth = token
    if access_code:
        st.session_state.access_code = access_code
    st.rerun()


def flash(message):
    st.session_state.flash = message
    st.rerun()


def safely(action):
    try:
        action()
    except ValueError as exc:
        st.error(str(exc))


def format_duration(minutes):
    hours, remainder = divmod(minutes, 60)
    readable = " ".join(part for part in (f"{hours}시간" if hours else "", f"{remainder}분" if remainder else "") if part)
    return f"{readable} ({minutes}분)"


def app_link(**params):
    base = os.environ.get("PUBLIC_BASE_URL", "") or st.context.url
    parts = urlsplit(base)
    if parts.scheme in ("http", "https") and parts.netloc:
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))
    return ""


def home():
    st.markdown('<div class="eyebrow">SCHEDULE NEGOTIATOR / PROTOTYPE</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="title-row"><div class="page-title">시간표 네고시에이터</div>'
        '<div class="creator">제작자 · 계명대학교 경영정보학과 석사과정 윤준영</div></div>',
        unsafe_allow_html=True,
    )
    if st.session_state.get("flash"):
        st.info(st.session_state.pop("flash"))
    mode = st.session_state.get("entry_mode")
    if mode is None:
        st.markdown('<div class="lede">역할을 선택해 시작하세요.</div>', unsafe_allow_html=True)
        host_col, member_col, existing_col = st.columns(3, gap="large")
        if host_col.button("모임장으로 참여하기", type="primary", use_container_width=True):
            st.session_state.entry_mode = "host"
            st.rerun()
        host_col.caption("후보 기간·모임 길이·장소·인원을 설정하고, 참여자들의 스케줄을 모아 최적 시간을 결정합니다.")
        if member_col.button("모임원으로 참여하기", use_container_width=True):
            st.session_state.entry_mode = "member"
            st.rerun()
        member_col.caption("모임장에게 받은 5자리 초대 코드로 입장해, 후보 기간 중 참석이 어려운 시간을 제출합니다.")
        if existing_col.button("기존 모임 참여하기", use_container_width=True):
            st.session_state.entry_mode = "existing"
            st.rerun()
        existing_col.caption("개인 접속 코드 하나로 모임장 또는 모임원 권한을 자동 인식해 다시 접속합니다.")
        st.divider()
        st.markdown("### 시간표 네고시에이터란?")
        st.write("여러 사람의 참석 가능 시간과 일정 우선도를 모아, 필수 참여자가 참석할 수 있는 최적의 모임 시간을 찾아주는 일정 조율 도구입니다.")
        st.markdown("""
        <div class="flow">
          <div class="flow-step"><div class="flow-icon">🗓️</div><div class="flow-title">후보 기간 설정</div><div class="flow-copy">모임장·시간·장소·인원 설정</div></div>
          <div class="flow-arrow">→</div>
          <div class="flow-step"><div class="flow-icon">👥</div><div class="flow-title">스케줄 제출</div><div class="flow-copy">참여자별 참석 불가 시간 취합</div></div>
          <div class="flow-arrow">→</div>
          <div class="flow-step"><div class="flow-icon">⚖️</div><div class="flow-title">조건 반영</div><div class="flow-copy">우선도와 필수인원 적용</div></div>
          <div class="flow-arrow">→</div>
          <div class="flow-step"><div class="flow-icon">✨</div><div class="flow-title">최적 시간 추천</div><div class="flow-copy">참석·조정·불참을 계산해 순위화</div></div>
        </div>
        """, unsafe_allow_html=True)
        feature_one, feature_two, feature_three = st.columns(3, gap="medium")
        with feature_one:
            st.markdown('<div class="feature-title">01 · 스케쥴 취합</div>', unsafe_allow_html=True)
            st.caption("후보 기간 동안 각 참여자의 참석이 어려운 시간과 일정 우선도를 모읍니다.")
        with feature_two:
            st.markdown('<div class="feature-title">02 · 우선도</div>', unsafe_allow_html=True)
            st.caption("변경 불가·협의 필요·조정 가능의 세 단계로 일정의 중요도를 반영합니다.")
        with feature_three:
            st.markdown('<div class="feature-title">03 · 규칙기반 모임시간 최적화</div>', unsafe_allow_html=True)
            st.caption("필수인원과 우선도 규칙을 계산해 가장 적합한 모임 시간을 순서대로 제안합니다.")
        return

    if st.button("← 역할 선택으로 돌아가기"):
        st.session_state.pop("entry_mode", None)
        st.rerun()

    if mode == "host":
        st.subheader("모임 생성하기")
        st.caption("후보 기간, 필요한 모임 시간, 장소와 전체 인원을 먼저 설정하세요.")
        with st.form("create"):
            title = st.text_input("모임 이름", placeholder="예: 팀 프로젝트 킥오프", max_chars=80)
            name = st.text_input("내 이름 (모임장)", placeholder="이름 또는 닉네임", max_chars=30)
            period = st.date_input(
                "후보 기간", value=(today(), today() + timedelta(days=7)), min_value=today(),
                help="달력에서 시작일과 종료일을 차례로 선택하세요.",
            )
            st.markdown("**모임 길이**")
            duration_left, duration_right = st.columns(2)
            with duration_left:
                duration_hours = st.selectbox("시간", list(range(9)), index=2)
            with duration_right:
                duration_minutes = st.selectbox("분", list(range(0, 60, 10)), index=0)
            location = st.text_input("모임 위치", placeholder="예: 강남역 회의실 / Google Meet", max_chars=120)
            expected_people = st.number_input("모임 인원 (모임장 포함)", min_value=2, max_value=30, value=4, step=1)
            if st.form_submit_button("모임 생성하기", type="primary", use_container_width=True):
                def create_room():
                    if not isinstance(period, (tuple, list)) or len(period) != 2:
                        raise ValueError("달력에서 후보 기간의 시작일과 종료일을 모두 선택해 주세요.")
                    duration = duration_hours * 60 + duration_minutes
                    store.throttle("create", limit=30, window=3600)
                    token, access_code = store.create(
                        title, name, period[0], period[1], duration, location,
                        expected_people, return_access=True,
                    )
                    enter(token, access_code)
                safely(create_room)
    elif mode == "member":
        st.subheader("모임원으로 참여하기")
        with st.form("join"):
            code = st.text_input("모임 초대 코드", value=str(st.query_params.get("room", ""))[:5].upper(), placeholder="예: A7K2Q", max_chars=5)
            name = st.text_input("참여자 이름", max_chars=30)
            st.caption("모임장에게 받은 5자리 코드를 입력하세요.")
            if st.form_submit_button("참여하고 스케줄 입력하기", type="primary", use_container_width=True):
                def join_room():
                    token, access_code = store.join(code, name, return_access=True)
                    enter(token, access_code)
                safely(join_room)
    else:
        st.subheader("기존 모임 참여하기")
        st.caption("처음 참여했을 때 발급받은 5자리 개인 접속 코드를 입력하세요.")
        with st.form("resume"):
            access_code = st.text_input(
                "개인 접속 코드", value=str(st.query_params.get("access", ""))[:5].upper(),
                placeholder="예: B3M8Q", max_chars=5,
            )
            if st.form_submit_button("기존 모임으로 접속", type="primary", use_container_width=True):
                def resume_room():
                    token, _role = store.resume(access_code)
                    enter(token, access_code.strip().upper())
                safely(resume_room)


def calendar_view(snapshot, month):
    m = snapshot["meeting"]
    begin, end = date.fromisoformat(m["start_date"]), date.fromisoformat(m["end_date"])
    counts = {}
    for e in snapshot["events"]:
        a, b = datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])
        for week in calendar.Calendar(0).monthdatescalendar(month.year, month.month):
            for d in week:
                if a.date() <= d <= b.date() and a < datetime.combine(d, datetime.max.time()) and b > datetime.combine(d, datetime.min.time()):
                    counts.setdefault(d, set()).add(e["person_id"])
    cells = ['<div class="calendar">'] + [f'<div class="weekday">{w}</div>' for w in "월화수목금토일"]
    for week in calendar.Calendar(0).monthdatescalendar(month.year, month.month):
        for day in week:
            active = begin <= day <= end
            classes = "day" + (" off" if not active else "") + (" today" if day == today() else "")
            caption = f"{len(counts.get(day, []))}명 일정" if active and counts.get(day) else ("후보 날짜" if active else "")
            cells.append(f'<div class="{classes}"><strong>{day.day:02d}</strong><small>{caption}</small></div>')
    st.markdown("".join(cells) + "</div>", unsafe_allow_html=True)


def my_schedule(snapshot, token):
    st.subheader("나의 스케줄 입력하기")
    st.caption("달력에서 날짜를 고른 뒤 참석이 어려운 시간, 내용 공개 여부와 우선도를 입력하세요.")
    with st.expander("우선도 안내", expanded=False):
        st.write("1 · 절대 변경할 수 없음")
        st.write("2 · 변경 가능성이 있거나 다른 사람과 협의가 필요함")
        st.write("3 · 급하지 않아 미루거나 조정할 수 있음")
        st.caption("우선도 2·3도 자동으로 변경하지 않습니다.")
    m = snapshot["meeting"]
    first_day, last_day = date.fromisoformat(m["start_date"]), date.fromisoformat(m["end_date"])
    with st.form("manual_schedule", clear_on_submit=True):
        event_day = st.date_input("날짜", value=first_day, min_value=first_day, max_value=last_day)
        start_col, end_col = st.columns(2)
        with start_col:
            start_clock = st.time_input("시작 시간", value=time(9, 0), step=timedelta(minutes=10))
        with end_col:
            end_clock = st.time_input("종료 시간", value=time(10, 0), step=timedelta(minutes=10))
        title = st.text_input("일정 내용", placeholder="예: 개인 일정", max_chars=200)
        priority = st.selectbox("우선도", [1, 2, 3], format_func=lambda n: f"{n} · {PRIORITIES[n]}")
        masked = st.checkbox("일정 내용 마스킹", value=True, help="체크하면 다른 사람에게 일정 내용 대신 ‘바쁨’으로 표시됩니다.")
        if st.form_submit_button("스케줄에 추가", type="primary", use_container_width=True):
            def save_event():
                start_at = datetime.combine(event_day, start_clock)
                end_at = datetime.combine(event_day, end_clock)
                if end_at <= start_at:
                    raise ValueError("종료 시간은 시작 시간보다 늦어야 합니다.")
                store.save_events(token, [{
                    "title": title.strip() or "개인 일정",
                    "start": start_at.isoformat(timespec="minutes"),
                    "end": end_at.isoformat(timespec="minutes"),
                    "priority": priority,
                    "public": not masked,
                }])
                flash("스케줄에 추가했습니다. 모두 입력한 뒤 아래 제출 버튼을 눌러주세요.")
            safely(save_event)
    st.divider()
    owned = [e for e in snapshot["events"] if e["person_id"] == snapshot["me"]["id"]]
    st.markdown(f"#### 저장한 일정 · {len(owned)}개")
    if not owned:
        st.info("참석이 어려운 시간이 없다면 바로 아래 ‘나의 스케줄 제출’을 눌러주세요.")
    for event in owned:
        a = datetime.fromisoformat(event["start"])
        b = datetime.fromisoformat(event["end"])
        with st.expander(f"{a:%m/%d %H:%M} – {b:%m/%d %H:%M}  ·  {event['title']}"):
            with st.form(f"event_{event['id']}"):
                priority = st.selectbox("우선도", [1,2,3], index=event["priority"] - 1,
                                       format_func=lambda n: f"{n} · {PRIORITIES[n]}")
                public = st.checkbox("일정 내용 공개", value=bool(event["public"]))
                if st.form_submit_button("변경 저장"):
                    def update(e=event, p=priority, v=public):
                        store.update_event(token, e["id"], p, v)
                        flash("변경을 저장했습니다.")
                    safely(update)
            if st.button("일정 삭제", key=f"delete_{event['id']}"):
                store.delete_event(token, event["id"])
                flash("일정을 삭제했습니다.")
    if snapshot["me"]["submitted"]:
        st.success("나의 스케줄을 제출했습니다. 일정을 변경하면 다시 제출해야 합니다.")
    if st.button("나의 스케줄 제출", type="primary", use_container_width=True):
        store.submit(token)
        message = "모임 생성 완료. 초대 코드를 모임원에게 공유하세요." if snapshot["me"]["host"] else "스케줄 제출 완료. 다른 참여자의 제출을 기다려주세요."
        flash(message)
    st.caption("제출 후에도 일정을 추가하거나 삭제할 수 있습니다. 시간이 바뀌면 다시 제출해 주세요.")


def shared_calendar(snapshot):
    st.subheader("공유 캘린더")
    st.caption("다른 참여자의 비공개 일정은 내용 대신 ‘바쁨’과 우선도만 표시합니다.")
    m = snapshot["meeting"]
    start, end = date.fromisoformat(m["start_date"]), date.fromisoformat(m["end_date"])
    months = sorted({(start.year, start.month), (end.year, end.month)})
    choice = st.selectbox("표시할 달", months, format_func=lambda x: f"{x[0]}년 {x[1]}월")
    calendar_view(snapshot, date(*choice, 1))
    selected = st.date_input("확인할 날짜", value=start, min_value=start, max_value=end)
    low = datetime.combine(selected, datetime.min.time())
    high = low + pd.Timedelta(days=1)
    events = [e for e in snapshot["events"] if datetime.fromisoformat(e["start"]) < high and datetime.fromisoformat(e["end"]) > low]
    st.markdown(f"#### {selected:%m월 %d일}의 일정")
    if not events:
        st.info("이 날짜에 저장된 일정이 없습니다. 미제출자의 가능 여부는 아직 알 수 없습니다.")
    for event in events:
        a, b = datetime.fromisoformat(event["start"]), datetime.fromisoformat(event["end"])
        with st.container(border=True):
            left, right = st.columns([1, 3])
            left.write(event["name"])
            left.caption(f"우선도 {event['priority']} · {PRIORITIES[event['priority']]}")
            right.text(event["title"])
            right.caption(f"{a:%m/%d %H:%M} – {b:%m/%d %H:%M}")


def recommendations(snapshot):
    st.subheader("추천 시간")
    st.caption("필수 참여자의 변경 불가 일정은 피하고, 더 많은 사람이 참석할 수 있는 순서로 제안합니다.")
    expected = snapshot["meeting"]["expected_people"]
    if len(snapshot["people"]) < expected:
        st.info(f"모임원 참여를 기다리고 있습니다: {len(snapshot['people'])} / {expected}명")
        return
    missing = [p["name"] for p in snapshot["people"] if not p["submitted"]]
    if missing:
        st.info("모든 참여자의 일정 제출을 기다리고 있습니다: " + ", ".join(missing))
        st.caption("모임장도 제출해야 합니다. 바쁜 일정이 없어도 ‘내 일정 제출’을 눌러주세요.")
        return
    st.caption("10분 간격으로 하루 00:00~24:00 전체를 탐색합니다. 모임 자체는 자정을 넘기지 않습니다.")
    candidates = find_candidates(snapshot)
    if not candidates:
        st.warning("필수 참여자가 모두 참석할 수 있는 시간이 없습니다. 일정을 확인하거나 필수 참여자 지정을 검토해 주세요.")
        return
    best = candidates[0]
    if not best["excluded"] and not best["conditional"]:
        st.success("일정 변경 없이 전원 참석할 수 있는 시간을 찾았습니다.")
    else:
        st.info("일부 참여자의 불참 또는 일정 조정이 필요합니다. 조건을 확인한 뒤 협의해 주세요.")
    for i, c in enumerate(candidates):
        with st.container(border=True):
            left, right = st.columns([1.05, 1.3], gap="large")
            with left:
                st.caption(f"후보 {i+1:02d}" + (" · 가장 먼저 추천" if i == 0 else ""))
                st.markdown(f"### {c['start']:%m월 %d일} ({'월화수목금토일'[c['start'].weekday()]})")
                st.markdown(f"## {c['start']:%H:%M} — {c['end']:%H:%M}")
            with right:
                st.write(f"바로 참석 가능 {len(c['free'])}명  /  조정 필요 {len(c['conditional'])}명  /  불참 {len(c['excluded'])}명")
                if c["free"]:
                    st.caption("가능: " + ", ".join(p["name"] + (" (필수)" if p["required"] else "") for p in c["free"]))
                for p in c["conditional"]:
                    st.write(f"↳ {p['name']}{' (필수)' if p['required'] else ''}: 우선도 {p['priority']} 일정 조정 동의 필요")
                if c["excluded"]:
                    st.caption("불참: " + ", ".join(p["name"] for p in c["excluded"]))
                if c["conditional"]:
                    st.caption("조건부 후보입니다. 일정은 자동으로 이동·확정하지 않습니다.")
    with st.expander("추천 순서"):
        st.write("필수 참여자의 우선도 1과 겹치면 제외합니다. 남은 후보는 불참 인원이 적은 순, 우선도 2 충돌이 적은 순, 우선도 3 충돌이 적은 순, 빠른 시간순으로 정렬합니다.")


def participants(snapshot, token):
    st.subheader("참여자")
    st.caption("필수 참여자의 참석을 먼저 보장합니다. 조건부 후보는 당사자의 일정 조정 동의가 필요합니다.")
    people = snapshot["people"]
    expected = snapshot["meeting"]["expected_people"]
    ready = len(people) == expected and all(p["submitted"] for p in people)
    st.metric("참여 현황", f"{len(people)} / {expected}명")
    if snapshot["me"]["host"] and ready:
        with st.form("required"):
            mapping = {p["id"]: p["name"] + (" (모임장)" if p["host"] else "") for p in people}
            selected = st.multiselect("필수 참여자 지정", list(mapping), default=[p["id"] for p in people if p["required"]], format_func=mapping.get)
            if st.form_submit_button("필수 참여자 저장", type="primary"):
                store.set_required(token, selected)
                flash("필수 참여자 지정을 저장했습니다.")
    elif snapshot["me"]["host"]:
        st.info("설정한 인원이 모두 참여하고 스케줄을 제출하면 필수 참여자를 지정할 수 있습니다.")
    else:
        st.caption("필수·비필수 지정은 모임장만 변경할 수 있습니다.")
    for p in people:
        with st.container(border=True):
            a, b, c = st.columns([2, 1, 1])
            a.write(p["name"] + (" · 모임장" if p["host"] else ""))
            b.write("필수" if p["required"] else "비필수")
            c.write("제출 완료" if p["submitted"] else "제출 대기")
    if snapshot["me"]["host"]:
        st.divider()
        with st.expander("모임 삭제"):
            st.caption("모든 참여자와 일정이 함께 삭제됩니다. 되돌릴 수 없습니다.")
            with st.form("delete_room"):
                confirmation = st.text_input("삭제하려면 모임 이름을 입력하세요")
                if st.form_submit_button("이 모임 삭제"):
                    if confirmation == snapshot["meeting"]["title"]:
                        store.delete_meeting(token)
                        st.session_state.clear()
                        flash("모임을 삭제했습니다.")
                    else:
                        st.error("모임 이름을 정확히 입력해 주세요.")


def workspace(snapshot, token):
    me, m, people = snapshot["me"], snapshot["meeting"], snapshot["people"]
    if not st.session_state.get("access_code"):
        legacy_code = store.ensure_access_code(token)
        if legacy_code:
            st.session_state.access_code = legacy_code
    all_ready = len(people) == m["expected_people"] and all(p["submitted"] for p in people)
    with st.sidebar:
        st.markdown("### ◷ 시간표 네고시에이터")
        st.caption("SCHEDULE NEGOTIATOR")
        st.divider()
        st.write(f"{me['name']} 님" + (" · 모임장" if me["host"] else ""))
        if not me["submitted"]:
            menu = ["내 일정"]
        elif me["host"] and all_ready:
            menu = ["내 일정", "공유 캘린더", "참여자", "추천 시간"]
        elif me["host"]:
            menu = ["내 일정", "참여자"]
        else:
            menu = ["내 일정", "공유 캘린더", "참여자"]
        page = st.radio("메뉴", menu, label_visibility="collapsed")
        st.divider()
        access_code = st.session_state.get("access_code", "")
        if access_code:
            with st.expander("개인 재접속 정보", expanded=not me["submitted"]):
                label = "모임장 관리 코드" if me["host"] else "모임원 개인 접속 코드"
                st.caption(label + " · 다른 사람에게 공유하지 마세요")
                st.code(access_code, language=None)
                access_link = app_link(access=access_code)
                if access_link:
                    st.caption("개인 재접속 링크")
                    st.code(access_link, language=None)
                st.caption("창을 닫기 전에 개인 코드 또는 링크를 안전한 곳에 보관하세요.")
        if me["host"] and not me["submitted"]:
            st.caption("나의 스케줄을 제출하면 모임 생성이 완료되고 참여자 초대 정보가 표시됩니다.")
        else:
            st.caption("참여자 입장 코드 · 함께할 사람에게 공유")
            st.code(m["join_code"], language=None)
            invite = app_link(room=m["join_code"])
            if invite:
                with st.expander("참여 링크 복사"):
                    st.code(invite, language=None)
                    st.caption("모임원에게 참여 링크 또는 5자리 입장 코드를 공유하세요.")
        if st.button("새로고침", use_container_width=True):
            st.rerun()
        if st.button("나가기", use_container_width=True):
            st.session_state.clear()
            st.rerun()
        st.caption("모든 날짜·시간은 한국 시간이며, 후보 기간이 지나면 모임 정보가 자동 삭제됩니다.")
    st.markdown('<div class="eyebrow">YOUR TIME, TOGETHER</div>', unsafe_allow_html=True)
    st.title(m["title"])
    location = f"  ·  {m['location']}" if m["location"] else ""
    st.caption(f"{m['start_date']} ~ {m['end_date']}  ·  모임 {format_duration(m['duration'])}{location}")
    a, b, c = st.columns(3)
    a.metric("참여자", f"{len(people)} / {m['expected_people']}명")
    b.metric("일정 제출", f"{sum(p['submitted'] for p in people)} / {len(people)}")
    c.metric("필수 참여자", f"{sum(p['required'] for p in people)}명")
    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))
    if me["host"] and me["submitted"] and len(people) < m["expected_people"]:
        st.info("모임 생성 완료 · 초대 코드를 공유하고 모임원의 참여를 기다려주세요.")
    elif me["host"] and me["submitted"] and not all_ready:
        st.info("모임원의 스케줄 제출을 기다리고 있습니다.")
    elif me["host"] and all_ready:
        st.success("모든 모임원이 제출했습니다. 참여자 메뉴에서 필수인원을 지정한 뒤 추천 시간을 확인하세요.")
    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
    if page == "내 일정":
        my_schedule(snapshot, token)
    elif page == "공유 캘린더":
        shared_calendar(snapshot)
    elif page == "추천 시간":
        recommendations(snapshot)
    else:
        participants(snapshot, token)


if not st.session_state.get("auth") and st.query_params.get("access"):
    access_code = str(st.query_params.get("access", ""))[:5].upper()
    st.query_params.clear()
    try:
        token, _role = store.resume(access_code)
        enter(token, access_code)
    except ValueError as exc:
        st.session_state.flash = str(exc)

# Backward compatibility for management links created by the previous prototype version.
if not st.session_state.get("auth") and st.query_params.get("room") and st.query_params.get("manage"):
    room = str(st.query_params.get("room", ""))[:5].upper()
    host_code = str(st.query_params.get("manage", ""))[:5].upper()
    st.query_params.clear()
    try:
        enter(store.host_login(room, host_code), host_code)
    except ValueError as exc:
        st.session_state.flash = str(exc)

if not st.session_state.get("auth") and st.query_params.get("room") and not st.session_state.get("entry_mode"):
    st.session_state.entry_mode = "member"

if not st.session_state.get("auth"):
    home()
else:
    try:
        state = store.snapshot(st.session_state.auth)
    except ValueError as exc:
        st.session_state.clear()
        st.session_state.flash = str(exc)
        st.rerun()
    workspace(state, st.session_state.auth)
