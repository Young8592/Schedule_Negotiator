"""Schedule parsing, privacy boundaries and candidate selection (Asia/Seoul)."""
from __future__ import annotations

import calendar
import hashlib
import hmac
import re
import secrets
import sqlite3
import time as clock_time
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")
PRIORITIES = {1: "변경 불가", 2: "협의 필요", 3: "조정 가능"}
JOIN_CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
JOIN_CODE_DIGITS = "23456789"
JOIN_CODE_ALPHABET = JOIN_CODE_LETTERS + JOIN_CODE_DIGITS


class _PostgresConnection:
    """Small compatibility layer so the storage logic can use SQLite-style placeholders."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        if sql.strip().upper() == "BEGIN IMMEDIATE":
            return self.connection.cursor()
        return self.connection.execute(sql.replace("?", "%s"), params)


def generate_join_code():
    """Return a readable five-character code containing letters and digits."""
    while True:
        code = "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(5))
        if any(c in JOIN_CODE_LETTERS for c in code) and any(c in JOIN_CODE_DIGITS for c in code):
            return code


def generate_host_code():
    """Return a readable five-character management code containing letters and digits."""
    while True:
        code = "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(5))
        if any(c in JOIN_CODE_LETTERS for c in code) and any(c in JOIN_CODE_DIGITS for c in code):
            return code


def today():
    return datetime.now(SEOUL).date()


def period_bounds(start: date, mode: str):
    if mode == "일간":
        return start, start
    if mode == "주간":
        return start, start + timedelta(days=6)
    if mode == "월간":
        return start.replace(day=1), start.replace(day=calendar.monthrange(start.year, start.month)[1])
    raise ValueError("기간 종류를 확인해 주세요.")


def validate_event(event, meeting):
    title = str(event.get("title", "")).strip()
    if not title or len(title) > 200:
        raise ValueError("일정 내용은 1~200자로 입력해 주세요.")
    try:
        start = datetime.fromisoformat(str(event["start"]))
        end = datetime.fromisoformat(str(event["end"]))
    except (ValueError, KeyError, TypeError):
        raise ValueError("시작과 종료 날짜·시간을 확인해 주세요.") from None
    if start.tzinfo or end.tzinfo:
        raise ValueError("날짜와 시간은 한국 시간으로 입력해 주세요.")
    if start >= end:
        raise ValueError("종료는 시작보다 늦어야 합니다.")
    low = datetime.combine(date.fromisoformat(meeting["start_date"]), time.min)
    high = datetime.combine(date.fromisoformat(meeting["end_date"]) + timedelta(days=1), time.min)
    if end <= low or start >= high:
        raise ValueError("후보 기간과 겹치는 일정을 입력해 주세요.")
    priority = event.get("priority", 1)
    if isinstance(priority, bool) or priority not in PRIORITIES:
        raise ValueError("우선도는 1, 2, 3 중 하나여야 합니다.")
    if not isinstance(event.get("public", False), bool):
        raise ValueError("공개 여부를 확인해 주세요.")
    return {"title": title, "start": start.isoformat(timespec="minutes"),
            "end": end.isoformat(timespec="minutes"), "priority": int(priority),
            "public": event.get("public", False)}


def parse_local(raw: str, meeting, default_priority=1):
    """Conservative offline parser. Ambiguity is surfaced, never silently saved."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines or len(lines) > 30 or len(raw) > 6000:
        raise ValueError("한 줄에 한 일정씩, 최대 30개·6,000자로 입력해 주세요.")
    result, warnings = [], []
    base = date.fromisoformat(meeting["start_date"])
    end_date = date.fromisoformat(meeting["end_date"])
    clock = re.compile(r"(?P<ampm>오전|오후|아침|저녁|밤)?\s*(?P<h>\d{1,2})(?:(?::(?P<min>\d{2}))|시(?:\s*(?P<km>\d{1,2})분|(?P<half>\s*반))?)")
    for line_no, line in enumerate(lines, 1):
        if re.search(r"매주|매일|반복|격주|부터.*일까지", line):
            raise ValueError(f"{line_no}번째 줄: 반복 일정은 날짜별로 나눠 입력해 주세요.")
        m = re.match(r"(?:(\d{4})[-/.년]\s*)?(\d{1,2})[-/.월]\s*(\d{1,2})(?:일)?", line)
        if m:
            yr, mo, dy = m.groups()
            years = [int(yr)] if yr else list(range(base.year, end_date.year + 1))
            try:
                choices = [date(y, int(mo), int(dy)) for y in years]
            except ValueError:
                raise ValueError(f"{line_no}번째 줄: 존재하지 않는 날짜입니다.") from None
            day = next((d for d in choices if base <= d <= end_date), choices[0])
            rest = line[m.end():].strip()
        else:
            relative = re.match(r"(오늘|내일|모레)", line)
            if not relative:
                raise ValueError(f"{line_no}번째 줄: '10/8 오후 8시 공연'처럼 날짜부터 입력해 주세요.")
            day = today() + timedelta(days={"오늘": 0, "내일": 1, "모레": 2}[relative[1]])
            rest = line[relative.end():].strip()
        weekday = re.match(r"\(([월화수목금토일])(?:요일)?\)", rest)
        if weekday:
            if "월화수목금토일"[day.weekday()] != weekday[1]:
                warnings.append(f"{line_no}번째 줄: 날짜와 요일이 다릅니다. {day.isoformat()} 기준으로 확인해 주세요.")
            rest = rest[weekday.end():].strip()
        priority_match = re.search(r"우선도\s*[:=]?\s*([123])", rest)
        priority = int(priority_match[1]) if priority_match else default_priority
        if priority_match:
            rest = (rest[:priority_match.start()] + rest[priority_match.end():]).strip()
        if re.search(r"하루\s*종일|종일|하루\s*전체", rest):
            title = re.sub(r"하루\s*종일|종일|하루\s*전체", "", rest).strip()
            start = datetime.combine(day, time.min)
            end = start + timedelta(days=1)
        else:
            first = clock.match(rest)
            if not first:
                raise ValueError(f"{line_no}번째 줄: 시작 시간 또는 '하루종일'을 입력해 주세요.")

            def read_time(match, inherit=None):
                h = int(match["h"])
                minute = int(match["min"] or match["km"] or (30 if match["half"] else 0))
                ampm = match["ampm"] or inherit
                if minute > 59 or h > 23 or (ampm and not 1 <= h <= 12):
                    raise ValueError(f"{line_no}번째 줄: 시간 범위를 확인해 주세요.")
                if ampm:
                    h = h % 12 + (12 if ampm in ("오후", "저녁", "밤") else 0)
                elif h <= 12 and not match["min"]:
                    warnings.append(f"{line_no}번째 줄: 오전/오후가 없어 {h:02d}:{minute:02d}로 임시 해석했습니다. 수정 후 저장해 주세요.")
                return time(h, minute)

            start = datetime.combine(day, read_time(first))
            remaining = rest[first.end():].strip()
            sep = re.match(r"(?:부터|~|〜|–|—|-)\s*", remaining)
            if sep:
                second = clock.match(remaining[sep.end():])
                if not second:
                    raise ValueError(f"{line_no}번째 줄: 종료 시간을 '21:00' 또는 '오후 9시'로 입력해 주세요.")
                end = datetime.combine(day, read_time(second, first["ampm"]))
                if end <= start:
                    end += timedelta(days=1)
                    warnings.append(f"{line_no}번째 줄: 종료를 다음 날로 해석했습니다. 자정을 넘기는 일정인지 확인해 주세요.")
                title = remaining[sep.end() + second.end():].removeprefix("까지").strip()
            else:
                if re.match(r"\d.*(?:시간|분)", remaining):
                    raise ValueError(f"{line_no}번째 줄: 지속 시간 대신 종료 시간을 입력해 주세요.")
                end = start + timedelta(hours=1)
                title = remaining
                warnings.append(f"{line_no}번째 줄: 종료 시간이 없어 1시간으로 임시 설정했습니다. 실제 종료 시간을 확인해 주세요.")
        event = {"title": title or "개인 일정", "start": start.isoformat(), "end": end.isoformat(),
                 "priority": priority, "public": False}
        result.append(validate_event(event, meeting))
    return result, warnings


class Store:
    def __init__(self, path):
        self.database_url = str(path) if str(path).startswith(("postgres://", "postgresql://")) else ""
        self.path = None if self.database_url else Path(path)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.integrity_errors = (sqlite3.IntegrityError,)
        else:
            import psycopg
            self.psycopg = psycopg
            self.integrity_errors = (psycopg.IntegrityError,)
        if self.database_url:
            with self.db() as con:
                statements = [
                    '''CREATE TABLE IF NOT EXISTS meetings (
                      id TEXT PRIMARY KEY, join_code TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
                      start_date TEXT NOT NULL, end_date TEXT NOT NULL, duration INTEGER NOT NULL,
                      location TEXT NOT NULL DEFAULT '', expected_people INTEGER NOT NULL DEFAULT 2,
                      host_code_hash TEXT NOT NULL DEFAULT '')''',
                    '''CREATE TABLE IF NOT EXISTS people (
                      id TEXT PRIMARY KEY, meeting_id TEXT REFERENCES meetings(id), name TEXT NOT NULL,
                      token_hash TEXT UNIQUE NOT NULL, host INTEGER NOT NULL DEFAULT 0,
                      required INTEGER NOT NULL DEFAULT 0, submitted INTEGER NOT NULL DEFAULT 0,
                      access_code_hash TEXT NOT NULL DEFAULT '', UNIQUE(meeting_id, name))''',
                    '''CREATE TABLE IF NOT EXISTS events (
                      id TEXT PRIMARY KEY, person_id TEXT REFERENCES people(id), title TEXT NOT NULL,
                      start TEXT NOT NULL, "end" TEXT NOT NULL,
                      priority INTEGER NOT NULL CHECK(priority IN (1,2,3)), public INTEGER NOT NULL DEFAULT 0)''',
                    "CREATE INDEX IF NOT EXISTS events_person ON events(person_id)",
                    "CREATE INDEX IF NOT EXISTS people_meeting ON people(meeting_id)",
                    '''CREATE TABLE IF NOT EXISTS auth_attempts (
                      bucket TEXT PRIMARY KEY, started DOUBLE PRECISION NOT NULL, count INTEGER NOT NULL)''',
                ]
                for statement in statements:
                    con.execute(statement)
            return
        with self.db() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS meetings (
                  id TEXT PRIMARY KEY, join_code TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
                  start_date TEXT NOT NULL, end_date TEXT NOT NULL, duration INTEGER NOT NULL,
                  location TEXT NOT NULL DEFAULT '', expected_people INTEGER NOT NULL DEFAULT 2,
                  host_code_hash TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS people (
                  id TEXT PRIMARY KEY, meeting_id TEXT REFERENCES meetings(id), name TEXT NOT NULL,
                  token_hash TEXT UNIQUE NOT NULL, host INTEGER NOT NULL DEFAULT 0,
                  required INTEGER NOT NULL DEFAULT 0, submitted INTEGER NOT NULL DEFAULT 0,
                  access_code_hash TEXT NOT NULL DEFAULT '',
                  UNIQUE(meeting_id, name));
                CREATE TABLE IF NOT EXISTS events (
                  id TEXT PRIMARY KEY, person_id TEXT REFERENCES people(id), title TEXT NOT NULL,
                  start TEXT NOT NULL, "end" TEXT NOT NULL, priority INTEGER NOT NULL CHECK(priority IN (1,2,3)),
                  public INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS events_person ON events(person_id);
                CREATE INDEX IF NOT EXISTS people_meeting ON people(meeting_id);
                CREATE TABLE IF NOT EXISTS auth_attempts (
                  bucket TEXT PRIMARY KEY, started REAL NOT NULL, count INTEGER NOT NULL);
            ''')
            columns = {r["name"] for r in con.execute("PRAGMA table_info(meetings)")}
            if "location" not in columns:
                con.execute("ALTER TABLE meetings ADD COLUMN location TEXT NOT NULL DEFAULT ''")
            if "expected_people" not in columns:
                con.execute("ALTER TABLE meetings ADD COLUMN expected_people INTEGER NOT NULL DEFAULT 2")
                con.execute("""UPDATE meetings SET expected_people = MAX(2,
                    (SELECT COUNT(*) FROM people WHERE people.meeting_id=meetings.id))""")
            if "host_code_hash" not in columns:
                con.execute("ALTER TABLE meetings ADD COLUMN host_code_hash TEXT NOT NULL DEFAULT ''")
            people_columns = {r["name"] for r in con.execute("PRAGMA table_info(people)")}
            if "access_code_hash" not in people_columns:
                con.execute("ALTER TABLE people ADD COLUMN access_code_hash TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def db(self):
        if self.database_url:
            from psycopg.rows import dict_row
            con = self.psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=10)
            try:
                with con:
                    yield _PostgresConnection(con)
            finally:
                con.close()
            return
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def throttle(self, bucket, limit=10, window=600):
        """Persist attempt counters across sessions; never rely on a browser/IP claim."""
        now = clock_time.time()
        with self.db() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM auth_attempts WHERE started < ?", (now - 86400,))
            row = con.execute("SELECT * FROM auth_attempts WHERE bucket=?", (bucket,)).fetchone()
            if row and now - row["started"] < window:
                if row["count"] >= limit:
                    seconds = max(1, int(window - (now - row["started"])))
                    raise ValueError(f"입력 시도가 너무 많습니다. {seconds}초 후 다시 시도해 주세요.")
                con.execute("UPDATE auth_attempts SET count=count+1 WHERE bucket=?", (bucket,))
            else:
                con.execute('''INSERT INTO auth_attempts (bucket,started,count) VALUES (?,?,1)
                    ON CONFLICT(bucket) DO UPDATE SET started=excluded.started,count=1''', (bucket, now))

    def clear_attempts(self, bucket):
        with self.db() as con:
            con.execute("DELETE FROM auth_attempts WHERE bucket=?", (bucket,))

    def actor(self, con, token):
        row = con.execute("SELECT * FROM people WHERE token_hash=?", (self.digest(token),)).fetchone()
        if row is None:
            raise ValueError("접속 코드를 확인해 주세요.")
        return dict(row)

    def unique_access_code(self, con):
        """Generate a code that cannot be confused with an invite or another access code."""
        for _ in range(100):
            code = generate_host_code()
            digest = self.digest(code)
            if con.execute("SELECT 1 FROM meetings WHERE join_code=? OR host_code_hash=?", (code, digest)).fetchone():
                continue
            if con.execute("SELECT 1 FROM people WHERE access_code_hash=?", (digest,)).fetchone():
                continue
            return code
        raise RuntimeError("사용 가능한 개인 접속 코드를 만들지 못했습니다.")

    def create(self, title, name, start, end, duration, location="", expected_people=2, return_access=False):
        if not 1 <= len(title.strip()) <= 80 or not 1 <= len(name.strip()) <= 30 or len(location.strip()) > 120:
            raise ValueError("모임 이름(80자), 이름(30자), 장소(120자 이내)를 확인해 주세요.")
        if not start <= end or (end - start).days > 31 or not 10 <= duration <= 480 or duration % 10:
            raise ValueError("기간은 최대 32일, 모임 길이는 10분 단위로 10~480분을 입력해 주세요.")
        if isinstance(expected_people, bool) or not 2 <= int(expected_people) <= 30:
            raise ValueError("모임 인원은 모임장을 포함해 2~30명으로 설정해 주세요.")
        mid, pid, token = secrets.token_hex(12), secrets.token_hex(12), secrets.token_urlsafe(24)
        with self.db() as con:
            for _ in range(50):
                code = generate_join_code()
                digest = self.digest(code)
                meeting_conflict = con.execute(
                    "SELECT 1 FROM meetings WHERE join_code=? OR host_code_hash=?", (code, digest)
                ).fetchone()
                person_conflict = con.execute(
                    "SELECT 1 FROM people WHERE access_code_hash=?", (digest,)
                ).fetchone()
                if meeting_conflict is None and person_conflict is None:
                    break
            else:
                raise RuntimeError("사용 가능한 모임 초대 코드를 만들지 못했습니다.")
            host_code = self.unique_access_code(con)
            con.execute("INSERT INTO meetings (id,join_code,title,start_date,end_date,duration,location,expected_people,host_code_hash) VALUES (?,?,?,?,?,?,?,?,?)", (mid, code, title.strip(), start.isoformat(), end.isoformat(), duration, location.strip(), int(expected_people), self.digest(host_code)))
            con.execute("INSERT INTO people (id,meeting_id,name,token_hash,host,required,submitted) VALUES (?,?,?,?,?,?,?)", (pid, mid, name.strip(), self.digest(token), 1, 1, 0))
        return (token, host_code) if return_access else token

    def host_login(self, join_code, host_code):
        """Issue a fresh host session token after verifying the room management code."""
        join_code = join_code.strip().upper()
        host_code = host_code.strip().upper()
        with self.db() as con:
            meeting = con.execute(
                "SELECT id,host_code_hash FROM meetings WHERE join_code=?", (join_code,)
            ).fetchone()
        if not meeting:
            raise ValueError("입장 코드 또는 모임장 관리 코드를 확인해 주세요.")
        bucket = "host:" + meeting["id"]
        self.throttle(bucket, limit=10, window=600)
        if not meeting["host_code_hash"] or not hmac.compare_digest(
            meeting["host_code_hash"], self.digest(host_code)
        ):
            raise ValueError("입장 코드 또는 모임장 관리 코드를 확인해 주세요.")
        token = secrets.token_urlsafe(24)
        with self.db() as con:
            con.execute("BEGIN IMMEDIATE")
            host = con.execute(
                "SELECT id FROM people WHERE meeting_id=? AND host=1", (meeting["id"],)
            ).fetchone()
            if not host:
                raise ValueError("모임장 정보를 찾을 수 없습니다.")
            con.execute("UPDATE people SET token_hash=? WHERE id=?", (self.digest(token), host["id"]))
        self.clear_attempts(bucket)
        return token

    def ensure_access_code(self, token):
        """Issue an access code once for a legacy participant who is still signed in."""
        with self.db() as con:
            con.execute("BEGIN IMMEDIATE")
            actor = self.actor(con, token)
            if actor["host"]:
                meeting = con.execute(
                    "SELECT host_code_hash FROM meetings WHERE id=?", (actor["meeting_id"],)
                ).fetchone()
                if meeting["host_code_hash"]:
                    return None
                access_code = self.unique_access_code(con)
                con.execute(
                    "UPDATE meetings SET host_code_hash=? WHERE id=?",
                    (self.digest(access_code), actor["meeting_id"]),
                )
            else:
                if actor["access_code_hash"]:
                    return None
                access_code = self.unique_access_code(con)
                con.execute(
                    "UPDATE people SET access_code_hash=? WHERE id=?",
                    (self.digest(access_code), actor["id"]),
                )
            return access_code

    def resume(self, access_code):
        """Recognize a five-character code and restore its host or member session."""
        access_code = access_code.strip().upper()
        if len(access_code) != 5:
            raise ValueError("5자리 개인 접속 코드를 확인해 주세요.")
        digest = self.digest(access_code)
        self.throttle("resume", limit=100, window=600)
        with self.db() as con:
            host_matches = con.execute(
                "SELECT id FROM meetings WHERE host_code_hash=?", (digest,)
            ).fetchall()
            member_matches = con.execute(
                "SELECT id FROM people WHERE access_code_hash=? AND host=0", (digest,)
            ).fetchall()
            if len(host_matches) + len(member_matches) != 1:
                raise ValueError("개인 접속 코드를 확인해 주세요.")
            if host_matches:
                person = con.execute(
                    "SELECT id FROM people WHERE meeting_id=? AND host=1", (host_matches[0]["id"],)
                ).fetchone()
                role = "host"
            else:
                person = member_matches[0]
                role = "member"
            if not person:
                raise ValueError("참여자 정보를 찾을 수 없습니다.")
            token = secrets.token_urlsafe(24)
            con.execute("UPDATE people SET token_hash=? WHERE id=?", (self.digest(token), person["id"]))
        return token, role

    def join(self, code, name, return_access=False):
        name = name.strip()
        if not 1 <= len(name) <= 30:
            raise ValueError("이름은 1~30자로 입력해 주세요.")
        with self.db() as con:
            m = con.execute("SELECT * FROM meetings WHERE join_code=?", (code.strip().upper(),)).fetchone()
        if not m:
            raise ValueError("모임 초대 코드를 확인해 주세요.")
        with self.db() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT COUNT(*) AS count FROM people WHERE meeting_id=?", (m["id"],)).fetchone()["count"] >= m["expected_people"]:
                raise ValueError("설정한 모임 인원이 모두 참여했습니다.")
            token = secrets.token_urlsafe(24)
            access_code = self.unique_access_code(con)
            try:
                con.execute("INSERT INTO people (id,meeting_id,name,token_hash,host,required,submitted,access_code_hash) VALUES (?,?,?,?,?,?,?,?)", (secrets.token_hex(12), m["id"], name, self.digest(token), 0, 0, 0, self.digest(access_code)))
            except self.integrity_errors:
                raise ValueError("같은 이름이 이미 있습니다. 다른 이름을 쓰거나 개인 접속 코드로 돌아와 주세요.") from None
        return (token, access_code) if return_access else token

    def snapshot(self, token):
        with self.db() as con:
            actor = self.actor(con, token)
            m = dict(con.execute("SELECT id,join_code,title,start_date,end_date,duration,location,expected_people FROM meetings WHERE id=?", (actor["meeting_id"],)).fetchone())
            people = [dict(r) for r in con.execute("SELECT id,name,host,required,submitted FROM people WHERE meeting_id=? ORDER BY host DESC,name", (m["id"],))]
            # Mask in SQL: private titles belonging to others never enter the UI payload.
            events = [dict(r) for r in con.execute('''SELECT e.id,e.person_id,p.name,e.start,e."end" AS end,e.priority,e.public,
                CASE WHEN e.person_id=? OR e.public=1 THEN e.title ELSE '바쁨' END AS title
                FROM events e JOIN people p ON p.id=e.person_id WHERE p.meeting_id=? ORDER BY e.start''',
                (actor["id"], m["id"]))]
            return {"me": {k: actor[k] for k in ("id", "name", "host", "required", "submitted")},
                    "meeting": m, "people": people, "events": events}

    def save_events(self, token, events):
        if not events or len(events) > 30:
            raise ValueError("일정은 한 번에 1~30개를 저장해 주세요.")
        with self.db() as con:
            con.execute("BEGIN IMMEDIATE")
            actor = self.actor(con, token)
            count = con.execute("SELECT COUNT(*) AS count FROM events WHERE person_id=?", (actor["id"],)).fetchone()["count"]
            if count + len(events) > 300:
                raise ValueError("한 사람당 최대 300개의 일정을 저장할 수 있습니다.")
            m = dict(con.execute("SELECT * FROM meetings WHERE id=?", (actor["meeting_id"],)).fetchone())
            valid = [validate_event(e, m) for e in events]
            for e in valid:
                duplicate = con.execute("SELECT id FROM events WHERE person_id=? AND start=? AND \"end\"=? AND title=?", (actor["id"], e["start"], e["end"], e["title"])).fetchone()
                if duplicate:
                    raise ValueError("이미 저장한 일정이 포함되어 있습니다. 중복 행을 제거해 주세요.")
                con.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)", (secrets.token_hex(12), actor["id"], e["title"], e["start"], e["end"], e["priority"], int(e["public"])))
            con.execute("UPDATE people SET submitted=0 WHERE id=?", (actor["id"],))

    def update_event(self, token, event_id, priority, public):
        if priority not in PRIORITIES or not isinstance(public, bool):
            raise ValueError("우선도와 공개 여부를 확인해 주세요.")
        with self.db() as con:
            actor = self.actor(con, token)
            row = con.execute("SELECT * FROM events WHERE id=? AND person_id=?", (event_id, actor["id"])).fetchone()
            if not row:
                raise ValueError("자신의 일정만 수정할 수 있습니다.")
            con.execute("UPDATE events SET priority=?,public=? WHERE id=?", (priority, int(public), event_id))
            if priority != row["priority"]:
                con.execute("UPDATE people SET submitted=0 WHERE id=?", (actor["id"],))

    def delete_event(self, token, event_id):
        with self.db() as con:
            actor = self.actor(con, token)
            if con.execute("DELETE FROM events WHERE id=? AND person_id=?", (event_id, actor["id"])).rowcount != 1:
                raise ValueError("자신의 일정만 삭제할 수 있습니다.")
            con.execute("UPDATE people SET submitted=0 WHERE id=?", (actor["id"],))

    def submit(self, token):
        with self.db() as con:
            actor = self.actor(con, token)
            con.execute("UPDATE people SET submitted=1 WHERE id=?", (actor["id"],))

    def set_required(self, token, ids):
        with self.db() as con:
            actor = self.actor(con, token)
            if not actor["host"]:
                raise ValueError("모임장만 필수 참여자를 지정할 수 있습니다.")
            people = con.execute("SELECT id FROM people WHERE meeting_id=?", (actor["meeting_id"],)).fetchall()
            if not set(ids).issubset({p["id"] for p in people}):
                raise ValueError("이 모임의 참여자만 지정할 수 있습니다.")
            for p in people:
                con.execute("UPDATE people SET required=? WHERE id=?", (int(p["id"] in ids), p["id"]))

    def delete_meeting(self, token):
        with self.db() as con:
            actor = self.actor(con, token)
            if not actor["host"]:
                raise ValueError("모임장만 모임을 삭제할 수 있습니다.")
            con.execute("DELETE FROM events WHERE person_id IN (SELECT id FROM people WHERE meeting_id=?)", (actor["meeting_id"],))
            con.execute("DELETE FROM people WHERE meeting_id=?", (actor["meeting_id"],))
            con.execute("DELETE FROM meetings WHERE id=?", (actor["meeting_id"],))
            con.execute("DELETE FROM auth_attempts WHERE bucket=?", ("room:" + actor["meeting_id"],))

    def delete_expired_meetings(self, as_of=None):
        """Delete rooms after the final candidate date has passed."""
        cutoff = (as_of or today()).isoformat()
        with self.db() as con:
            con.execute("BEGIN IMMEDIATE")
            ids = [r["id"] for r in con.execute("SELECT id FROM meetings WHERE end_date < ?", (cutoff,))]
            for meeting_id in ids:
                con.execute("DELETE FROM events WHERE person_id IN (SELECT id FROM people WHERE meeting_id=?)", (meeting_id,))
                con.execute("DELETE FROM people WHERE meeting_id=?", (meeting_id,))
                con.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))
                con.execute("DELETE FROM auth_attempts WHERE bucket=?", ("room:" + meeting_id,))
        return len(ids)


def find_candidates(snapshot, limit=12):
    """Half-open intervals; unknown schedules are not considered free."""
    m, people, events = snapshot["meeting"], snapshot["people"], snapshot["events"]
    if len(people) != m["expected_people"] or any(not p["submitted"] for p in people):
        return []
    by_person = {p["id"]: [] for p in people}
    for e in events:
        by_person[e["person_id"]].append((datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"]), e["priority"]))
    candidates = []
    day, last = date.fromisoformat(m["start_date"]), date.fromisoformat(m["end_date"])
    while day <= last:
        start = datetime.combine(day, time.min)
        boundary = start + timedelta(days=1)
        while start + timedelta(minutes=m["duration"]) <= boundary:
            end = start + timedelta(minutes=m["duration"])
            free, conditional, excluded = [], [], []
            p2, p3, blocked = 0, 0, False
            for person in people:
                overlaps = [priority for a, b, priority in by_person[person["id"]] if a < end and b > start]
                priority = min(overlaps, default=0)
                label = {"name": person["name"], "required": bool(person["required"])}
                if priority == 1:
                    excluded.append(label)
                    blocked |= bool(person["required"])
                elif priority:
                    conditional.append({**label, "priority": priority})
                    p2 += overlaps.count(2)
                    p3 += overlaps.count(3)
                else:
                    free.append(label)
            if not blocked and (free or conditional):
                candidates.append({"start": start, "end": end, "free": free, "conditional": conditional,
                    "excluded": excluded, "rank": (len(excluded), p2, p3, start)})
            start += timedelta(minutes=10)
        day += timedelta(days=1)
    return sorted(candidates, key=lambda c: c["rank"])[:limit]


def create_demo(store):
    start = today()
    token = store.create("팀 프로젝트 킥오프", "지윤", start, start + timedelta(days=6), 120, "회의실 A", 4)
    snap = store.snapshot(token)
    others = [store.join(snap["meeting"]["join_code"], name) for name in ("민서", "준호", "서연")]
    for i, t in enumerate([token] + others):
        ev = []
        for offset in range(7):
            d = start + timedelta(days=offset)
            # Explicit private demo events, not a preferred-time feature.
            ev.extend([{"title": "개인 일정", "start": f"{d}T00:00", "end": f"{d}T18:00", "priority": 1, "public": False},
                       {"title": "개인 일정", "start": f"{d}T22:00", "end": f"{d+timedelta(days=1)}T00:00", "priority": 1, "public": False}])
        ev.append({"title": ["리센느 공연", "독서", "운동", "친구와 약속"][i],
                   "start": f"{start}T18:00", "end": f"{start}T20:00", "priority": [1,3,2,1][i], "public": False})
        store.save_events(t, ev)
        store.submit(t)
    store.set_required(token, [store.snapshot(t)["me"]["id"] for t in [token, others[0]]])
    return token
