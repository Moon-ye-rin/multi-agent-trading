"""
pykrx KRX 로그인 패치 스크립트
PR #282 (https://github.com/sharebook-kr/pykrx/pull/282) 내용을
설치된 pykrx에 직접 적용합니다.

실행: python patch_pykrx.py
(한 번만 실행하면 됩니다. pykrx 재설치 시 다시 실행 필요)
"""
import importlib
import os
import sys


def find_pykrx_comm_dir():
    """설치된 pykrx의 website/comm 디렉터리 경로를 찾습니다."""
    try:
        import pykrx
        base = os.path.dirname(pykrx.__file__)
        comm_dir = os.path.join(base, "website", "comm")
        if os.path.isdir(comm_dir):
            return comm_dir
        print(f"❌ comm 디렉터리를 찾을 수 없습니다: {comm_dir}")
        sys.exit(1)
    except ImportError:
        print("❌ pykrx가 설치되어 있지 않습니다. pip install pykrx 를 먼저 실행하세요.")
        sys.exit(1)


def write_auth_py(comm_dir):
    """PR #282의 auth.py를 생성합니다."""
    path = os.path.join(comm_dir, "auth.py")
    content = '''\
import os
import requests

LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
LOGIN_JSP  = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
LOGIN_URL  = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def warmup_krx_session(session: requests.Session) -> None:
    """KRX 로그인 페이지를 미리 방문해 세션 쿠키를 초기화합니다."""
    try:
        session.get(LOGIN_PAGE, headers={"User-Agent": USER_AGENT}, timeout=15)
        session.get(
            LOGIN_JSP,
            headers={"User-Agent": USER_AGENT, "Referer": LOGIN_PAGE},
            timeout=15,
        )
    except Exception:
        pass


def login_krx(session: requests.Session, login_id: str, login_pw: str) -> bool:
    """KRX 데이터 포털에 로그인합니다. 성공 시 True 반환."""
    payload = {
        "mbrNm":    "",
        "telNo":    "",
        "di":       "",
        "certType": "",
        "mbrId":    login_id,
        "pw":       login_pw,
    }
    headers = {"User-Agent": USER_AGENT, "Referer": LOGIN_PAGE}
    try:
        resp = session.post(LOGIN_URL, data=payload, headers=headers, timeout=15)
        if not resp.ok:
            return False

        # Content-Type 무관하게 JSON 파싱 시도 (KRX는 text/html로 JSON을 반환함)
        try:
            data = resp.json()
        except Exception:
            return False

        error_code = data.get("_error_code", "")

        # CD011 = 중복 로그인 → skipDup=Y로 재시도
        if error_code == "CD011":
            payload["skipDup"] = "Y"
            resp = session.post(LOGIN_URL, data=payload, headers=headers, timeout=15)
            if not resp.ok:
                return False
            try:
                data = resp.json()
            except Exception:
                return False
            error_code = data.get("_error_code", "")

        return error_code == "CD001"  # CD001 = 로그인 성공
    except Exception as e:
        print(f"[pykrx-patch] KRX 로그인 오류: {e}")
        return False


def build_krx_session(
    login_id: str | None = None,
    login_pw: str | None = None,
) -> requests.Session | None:
    """
    KRX 로그인 세션을 생성합니다.
    KRX_ID / KRX_PW 환경변수가 없으면 None을 반환합니다.
    """
    if login_id is None:
        login_id = os.getenv("KRX_ID")
    if login_pw is None:
        login_pw = os.getenv("KRX_PW")

    if not (login_id and login_pw):
        return None  # 환경변수 미설정 시 None (기존 방식으로 fallback)

    session = requests.Session()
    warmup_krx_session(session)
    success = login_krx(session, login_id, login_pw)
    if not success:
        print("[pykrx-patch] ⚠️  KRX 로그인 실패. ID/PW를 확인하세요.")
        return None
    print("[pykrx-patch] ✅ KRX 로그인 성공")
    return session
'''
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ auth.py 작성 완료: {path}")


def patch_webio_py(comm_dir):
    """webio.py에 세션 주입 로직을 패치합니다."""
    path = os.path.join(comm_dir, "webio.py")

    with open(path, "r", encoding="utf-8") as f:
        original = f.read()

    # 이미 패치되어 있으면 스킵
    if "build_krx_session" in original:
        print(f"⏭️  webio.py 이미 패치되어 있음: {path}")
        return

    # 파일 상단에 세션 초기화 코드 삽입
    patch_header = '''\
import os
import requests
from pykrx.website.comm.auth import build_krx_session

_session = None  # 지연 초기화 (import 시점에 네트워크 호출 안 함)


def _get_or_init_session():
    global _session
    if _session is None:
        _session = build_krx_session()
    return _session


def set_session(session):
    global _session
    _session = session


def get_session():
    return _get_or_init_session()


'''

    # 기존 import requests 아래에 삽입
    if "import requests" in original:
        patched = original.replace(
            "import requests\n",
            patch_header,
            1,
        )
        # 기존 requests.get/post → session 분기로 교체
        patched = patched.replace(
            "resp = requests.get(self.url, headers=self.headers, params=params)",
            (
                "session = get_session()\n"
                "        if session is None:\n"
                "            resp = requests.get(self.url, headers=self.headers, params=params)\n"
                "        else:\n"
                "            resp = session.get(self.url, headers=self.headers, params=params)"
            ),
        )
        patched = patched.replace(
            "resp = requests.post(self.url, headers=self.headers, data=params)",
            (
                "session = get_session()\n"
                "        if session is None:\n"
                "            resp = requests.post(self.url, headers=self.headers, data=params)\n"
                "        else:\n"
                "            resp = session.post(self.url, headers=self.headers, data=params)"
            ),
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(patched)
        print(f"✅ webio.py 패치 완료: {path}")
    else:
        print(f"⚠️  webio.py 구조가 예상과 다릅니다. 수동 패치가 필요할 수 있습니다: {path}")


def patch_init_py(comm_dir):
    """__init__.py에 auth 심볼을 추가합니다."""
    path = os.path.join(comm_dir, "__init__.py")

    with open(path, "r", encoding="utf-8") as f:
        original = f.read()

    if "build_krx_session" in original:
        print(f"⏭️  __init__.py 이미 패치되어 있음: {path}")
        return

    addition = "\nfrom pykrx.website.comm.auth import build_krx_session, login_krx, warmup_krx_session\n"
    patched = original + addition

    with open(path, "w", encoding="utf-8") as f:
        f.write(patched)
    print(f"✅ __init__.py 패치 완료: {path}")


def verify_patch():
    """패치가 정상 적용됐는지 확인합니다."""
    print("\n--- 패치 검증 중 ---")
    # 모듈 캐시 초기화
    for mod in list(sys.modules.keys()):
        if "pykrx" in mod:
            del sys.modules[mod]

    try:
        from pykrx.website.comm.auth import build_krx_session, login_krx
        print("✅ auth.py import 성공")
    except ImportError as e:
        print(f"❌ auth.py import 실패: {e}")
        return

    try:
        from pykrx.website.comm.webio import get_session, set_session
        print("✅ webio.py import 성공")
    except ImportError as e:
        print(f"❌ webio.py import 실패: {e}")
        return

    krx_id = os.getenv("KRX_ID")
    krx_pw = os.getenv("KRX_PW")
    if krx_id and krx_pw:
        print(f"✅ 환경변수 확인: KRX_ID={krx_id[:3]}*** KRX_PW=***")
    else:
        print("⚠️  KRX_ID / KRX_PW 환경변수가 설정되지 않았습니다.")
        print("   .env 파일에 추가하거나 환경변수로 설정하세요.")


if __name__ == "__main__":
    # .env 로드
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ .env 로드 완료")
    except ImportError:
        print("⚠️  python-dotenv 없음, 환경변수는 시스템 설정값을 사용합니다.")

    print("\n=== pykrx KRX 로그인 패치 시작 ===")
    comm_dir = find_pykrx_comm_dir()
    print(f"pykrx 위치: {comm_dir}")

    write_auth_py(comm_dir)
    patch_webio_py(comm_dir)
    patch_init_py(comm_dir)
    verify_patch()

    print("\n=== 패치 완료 ===")
    print("이제 main.py를 실행하세요.")