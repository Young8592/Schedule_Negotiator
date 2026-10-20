# 인터넷 주소로 사용하는 방법

## 처음에는 무료 주소로 체험하기

서버가 앱을 실행하므로 배포 후에는 내 PC를 꺼도 사람들이 접속할 수 있습니다.
별도 도메인 구매 없이 `원하는이름.streamlit.app` 주소를 신청할 수 있습니다.
주소의 이름은 다른 사람이 쓰고 있지 않아야 합니다. 아래 주소는 예시이며 아직 개설되지 않았습니다.

1. [GitHub](https://github.com)에 로그인하고 새 저장소(repository)를 만듭니다. 공개 저장소로 시작하면 간단합니다.
2. 압축을 풀고 `schedule_negotiator` 폴더 안의 파일을 저장소에 업로드합니다. ZIP 자체가 아니라 안의 파일을 올립니다. `app.py`와 `requirements.txt`가 맨 위에 오도록 합니다. `.streamlit/config.toml`도 포함합니다. **개인 일정 DB, data 폴더, .venv는 올리지 않습니다.** 제공 ZIP에는 이 파일들이 없습니다.
3. [Streamlit Community Cloud](https://share.streamlit.io)에 GitHub 계정으로 연결합니다.
4. **Create app**에서 방금 만든 저장소와 브랜치를 선택하고, 실행 파일을 `app.py`로 지정합니다. Advanced settings에서 Python **3.12**를 선택합니다.
5. App URL에 원하는 이름을 입력하고 **Deploy**를 누릅니다. 완료 후 실제 발급된 HTTPS 주소를 공유합니다.

공개 앱으로 배포하면 누구나 첫 화면에 접속할 수 있고, 각 모임에는 영문 대문자와 숫자가 섞인 5자리 초대 코드가 발급됩니다.
내 모임을 만든 뒤 사이드바의 초대 링크 또는 코드를 참여자에게 공유하세요. 별도 입장 비밀번호는 없습니다.

**무료 체험의 저장 한계:** `DATABASE_URL`을 설정하지 않으면 앱은 SQLite 파일에 일정을 저장합니다. Community Cloud의 로컬 파일은 서버 재생성 시 사라질 수 있습니다. 아래의 무료 Supabase 연결을 설정하면 모임과 개인 접속 코드를 외부 PostgreSQL에 보관할 수 있습니다.

공식 안내: [배포와 주소 설정](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [GitHub 연결](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account)

## 무료 배포에서 데이터를 유지하기: Supabase

1. Supabase에서 무료 프로젝트를 만들고 데이터베이스 비밀번호를 안전하게 보관합니다.
2. 프로젝트 상단 **Connect**에서 **Session pooler** 연결 문자열을 복사합니다. Streamlit Cloud에서 IPv4로 접속할 수 있도록 포트 5432의 Session pooler를 사용합니다.
3. 문자열의 `[YOUR-PASSWORD]`를 실제 DB 비밀번호로 바꿉니다. 특수문자가 있으면 URL 인코딩합니다.
4. Streamlit Community Cloud의 앱에서 **Settings → Secrets**를 엽니다.
5. 아래 형식으로 저장합니다. 실제 문자열은 GitHub나 채팅에 올리지 않습니다.

```toml
DATABASE_URL = "postgresql://postgres.프로젝트참조:DB비밀번호@풀러주소:5432/postgres?sslmode=require"
```

6. 앱을 재부팅합니다. 첫 연결 때 필요한 테이블이 자동 생성됩니다.
7. 새 테스트 모임을 만들고 나간 뒤 개인 접속 코드로 다시 들어가 정상 동작을 확인합니다.

SQLite에 이미 만들었던 모임은 Supabase로 자동 이전되지 않으므로 외부 DB 연결 후 새로 생성해야 합니다. Supabase 무료 프로젝트는 장기간 사용하지 않으면 일시 정지될 수 있으며, 대시보드에서 다시 시작할 수 있습니다.

## 일정을 보관하며 운영하기: Render + 영구 디스크

이 방식은 유료입니다. 제공된 `render.yaml`은 설정 예시이며 자동으로 결제하거나 서버를 만들지 않습니다. 배포 화면에서 현재 서버·디스크 비용을 확인한 후 진행하세요.

1. 위의 파일을 GitHub 저장소 루트에 올립니다.
2. [Render](https://dashboard.render.com)에서 GitHub를 연결하고 **New → Blueprint**로 저장소를 선택합니다.
3. `render.yaml`에 있는 웹 서비스 1개와 영구 디스크 1GB 설정을 확인하고 배포합니다.
4. 배포가 끝나면 Render에서 표시하는 `https://…onrender.com` 주소로 접속합니다. 모임 생성 → 다른 브라우저로 참여 → 일정 저장 → 서비스 재시작 후 일정 유지까지 확인합니다.
5. 필요하면 환경변수 `PUBLIC_BASE_URL`에 최종 HTTPS 주소를 넣습니다. 설정하지 않으면 현재 접속 주소로 초대 링크를 만듭니다.

앱은 `/var/data/schedule.db`에 저장합니다. **디스크 경로와 SCHEDULE_DB를 함께 유지해야 합니다.** SQLite를 쓰므로 서비스 인스턴스는 1개로 운영합니다. 서버 관리자에게는 DB 파일 접근 권한이 있으므로 앱의 비공개 표시는 참여자 사이의 보호를 의미합니다. DB 자체의 일정 내용은 암호화하지 않습니다.

백업할 때는 SQLite backup 기능을 사용해 일관된 복사본을 만드세요. 서버 터미널에서 다음 명령으로 영구 디스크에 백업할 수 있습니다. 별도 보관할 복사본은 공개 저장소에 올리지 마세요.

```sh
python -c "import sqlite3; src=sqlite3.connect('/var/data/schedule.db'); dst=sqlite3.connect('/var/data/schedule.backup.db'); src.backup(dst); dst.close(); src.close()"
```

공식 안내: [영구 디스크](https://render.com/docs/disks), [배포 설정](https://render.com/docs/blueprint-spec)

## 나만의 .com / .kr 주소

먼저 위의 기본 주소로 시작할 수 있습니다. 나중에 원하는 도메인을 구매하고, 사용 중인 호스팅의 Custom Domain 메뉴에서 안내하는 DNS 값을 도메인 업체에 등록합니다. Render는 [자체 도메인 연결](https://render.com/docs/custom-domains)을 지원합니다. 도메인 등록 비용은 서버 요금과 별도이며, 등록 가능한 이름인지 확인해야 합니다.

## 모임 접근과 삭제

- 새 참여: 5자리 모임 초대 코드 + 이름.
- 초대 코드를 아는 사람은 참여할 수 있으므로 참여자에게만 공유합니다.
- 모임장만 모임을 수동 삭제할 수 있으며, 삭제하면 해당 모임의 참여자와 일정도 삭제됩니다.
- 후보 기간의 마지막 날이 지나면 앱 실행 또는 새로고침 시 모임과 관련 정보가 자동 삭제됩니다.
- 전체 앱에서 모임 생성은 시간당 최대 30회, 모임당 최대 30명, 한 사람당 최대 300개 일정입니다. 공개 서비스의 대규모 운영을 위한 부하 시험은 하지 않았습니다.
- 샘플 모임 버튼은 기본적으로 꺼져 있습니다. 로컬 체험 시에만 환경변수 `SCHEDULE_ENABLE_DEMO=1`을 설정할 수 있습니다.

이 앱의 일정 해석과 추천 계산은 모두 코드로 처리하며 LLM 또는 외부 일정 API를 호출하지 않습니다.
