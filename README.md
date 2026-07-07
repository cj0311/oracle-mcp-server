# Oracle MCP Server

AI agent가 Oracle DB를 읽기 전용으로 조회할 수 있게 해주는 Python 기반 MCP 서버입니다.

## 현재 범위

- 여러 Oracle DB profile 지원
- `stdio` MCP transport 기본 지원
- Oracle Thin mode 기본 사용
- `SELECT` / `WITH` 쿼리만 허용
- table/view/procedure/function/package 메타데이터 조회
- CLOB/NCLOB/BLOB/BFILE 컬럼 JSON 직렬화 지원
- row limit, query timeout 적용
- DB 비밀번호는 `.env` 또는 OS 환경변수에서 주입

## MCP 도구

- `list_profiles`: 등록된 DB profile 목록 조회
- `test_connection`: Oracle 접속 테스트
- `list_tables`: 접근 가능한 table/view 목록 조회
- `list_views`: 접근 가능한 view 목록 조회
- `describe_table`: table/view 컬럼과 primary key 조회
- `describe_view`: view 컬럼 조회
- `get_view_definition`: view SQL 정의 조회
- `sample_rows`: table/view 샘플 row 조회
- `list_procedures`: procedure/function/package 목록 조회
- `describe_procedure`: procedure/function 인자 조회
- `get_object_source`: procedure/function/package source 조회
- `run_select_query`: 읽기 전용 SQL 실행

프로시저와 함수는 실행하지 않습니다. `list_procedures`, `describe_procedure`, `get_object_source`는 Oracle dictionary view를 읽어서 구조와 소스만 조회합니다.

## 폐쇄망 개발 PC 준비 - Nexus 가능 환경

사내 Nexus PyPI simple URL을 pip 기본 저장소로 설정합니다.

```powershell
python -m pip config --user set global.index-url "https://nexus주소/repository/abc-pypi-std/simple/"
```

사내 인증서 문제가 있을 때만 임시로 trusted host를 설정합니다.

```powershell
python -m pip config --user set global.trusted-host "nexus주소"
```

설정 확인:

```powershell
python -m pip config list -v
```

## 폐쇄망 개발 PC 준비 - Nexus 불가 환경

Nexus도 접근할 수 없는 완전 폐쇄망 PC에는 소스만 반입하면 안 됩니다. Python 패키지 wheel 묶음인 `wheelhouse`를 같이 반입해야 합니다.

Nexus 연결이 되는 PC 또는 인터넷 연결이 되는 PC에서 offline bundle을 만듭니다.

```powershell
.\scripts\build-offline-bundle.ps1
```

생성 결과:

```text
dist\oracle-mcp-offline-bundle.zip
```

이 zip을 Nexus 불가 폐쇄망 PC로 반입한 뒤 압축을 풉니다.

```text
oracle-mcp-offline-bundle\
  source\
  wheelhouse\
```

설치:

```powershell
cd oracle-mcp-offline-bundle\source
.\scripts\install-offline.ps1
```

Linux x86_64 서버용 bundle은 Linux 서버에서 아래처럼 설치합니다.

```bash
cd oracle-mcp-offline-bundle-py312-linux-x86_64/source
bash scripts/install-offline.sh
```

RHEL9 서버에 Python 3.12가 없고 repo도 접근할 수 없다면, RHEL9 handoff에 포함된 standalone Python을 먼저 설치합니다.

```bash
unzip oracle-mcp-handoff-py312-rhel9-x86_64.zip -d oracle-mcp-rhel9
cd oracle-mcp-rhel9
bash install-standalone-python-rhel9.sh
export PATH="$HOME/.local/python-3.12.10/bin:$PATH"
unzip oracle-mcp-offline-bundle-py312-linux-x86_64.zip -d oracle-mcp-offline-bundle-py312-linux-x86_64
cd oracle-mcp-offline-bundle-py312-linux-x86_64/source
bash scripts/install-offline.sh
```

서버 공용 위치에 설치하려면 root 권한으로 `PREFIX`를 지정합니다.

```bash
sudo env PREFIX=/opt/python-3.12.10 bash install-standalone-python-rhel9.sh
PYTHON=/opt/python-3.12.10/bin/python3.12 bash scripts/install-offline.sh
```

`ModuleNotFoundError: No module named 'encodings'` 또는 `could not find platform independent libraries <prefix>` 오류가 나면 Python 경로 환경변수나 압축 해제 상태를 먼저 확인합니다.

```bash
unset PYTHONHOME PYTHONPATH
ls -l "$HOME/.local/python-3.12.10/lib/python3.12/encodings/__init__.py"
"$HOME/.local/python-3.12.10/bin/python3.12" -c "import sys, encodings; print(sys.prefix); print(encodings.__file__)"
```

`encodings/__init__.py`가 없다면 standalone Python을 다시 풉니다.

```bash
cd ~/oracle-mcp/rhel9
FORCE=1 bash install-standalone-python-rhel9.sh
```

개발/수정까지 해야 해서 source editable 설치가 필요하면:

```powershell
.\scripts\install-offline.ps1 -Editable
```

주의사항:

- `wheelhouse`는 OS, CPU 아키텍처, Python minor version에 영향을 받습니다.
- 예를 들어 Windows x64 + Python 3.11에서 만든 bundle은 Windows x64 + Python 3.11에서 쓰는 것이 안전합니다.
- Python 3.12 PC에 설치할 예정이면 Python 3.12 환경에서 offline bundle을 다시 만들어야 합니다.
- Linux 서버는 Linux x86_64용 bundle을 따로 사용해야 합니다. Windows용 bundle의 `win_amd64` wheel은 Linux에서 설치되지 않습니다.
- Python 실행 파일 자체는 별도로 설치되어 있어야 합니다. 필요하면 Python installer도 같이 반입합니다.

## 설치

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
```

확인:

```powershell
oracle-mcp --help
oracle-mcp-check --help
python -c "import mcp, oracledb, pydantic, dotenv, yaml; print('ok')"
python -c "import oracledb; print(oracledb.version); print(oracledb.is_thin_mode())"
```

## DB profile 설정

```powershell
Copy-Item profiles.example.yaml profiles.yaml
Copy-Item .env.example .env
```

`profiles.yaml` 예시:

```yaml
defaults:
  max_rows: 500
  query_timeout_seconds: 30
  sample_rows: 20

profiles:
  dev:
    description: "Development Oracle database"
    user: "${DEV_ORACLE_USER}"
    password: "${DEV_ORACLE_PASSWORD}"
    dsn: "dev-db.company.local:1521/DEV"
    default_owner: "APP_SCHEMA"
```

`.env` 예시:

```ini
ORACLE_MCP_CONFIG=profiles.yaml
DEV_ORACLE_USER=readonly_user
DEV_ORACLE_PASSWORD=change-me
```

`dsn`은 보통 아래 형식 중 하나를 씁니다.

```text
host:port/service_name
host:port/sid
tns_alias
```

TNS alias나 wallet이 필요하면 profile에 `config_dir`, `wallet_location`, `wallet_password`를 추가합니다.

## 로컬 실행

```powershell
oracle-mcp --config profiles.yaml --transport stdio
```

`stdio`는 MCP host가 서버 프로세스를 직접 실행해서 stdin/stdout으로 통신하는 방식입니다. 일반 터미널에서 실행하면 대기 상태처럼 보이는 것이 정상입니다.

## OpenCode 등록 예시

OpenCode는 MCP 서버를 최상위 `mcp` 키 아래에 등록합니다. `mcpServers`가 아닙니다.
Python 실행 파일과 config 경로는 절대경로를 권장합니다.

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "oracle-db": {
      "type": "local",
      "command": [
        "C:\\path\\to\\oracle-mcp\\.venv\\Scripts\\python.exe",
        "-m",
        "oracle_mcp",
        "--config",
        "C:\\path\\to\\oracle-mcp\\profiles.yaml"
      ],
      "cwd": "C:\\path\\to\\oracle-mcp",
      "enabled": true,
      "timeout": 30000
    }
  },
  "permission": {
    "*": "ask",
    "oracle-db_*": "allow"
  }
}
```

`permission`에서 `oracle-db_*`는 `oracle-db` MCP 서버가 노출하는 모든 도구를 의미합니다. 위 설정은 다른 OpenCode 도구는 계속 승인받고, 이 Oracle MCP 도구만 자동 실행합니다.

프로젝트별 설정은 작업 디렉터리의 `opencode.json` 또는 `opencode.jsonc`에 넣습니다. 전역 설정은 `~/.config/opencode/opencode.json`에 넣을 수 있습니다.

등록 후 OpenCode에서 다음처럼 확인합니다.

```powershell
opencode mcp list
```

프롬프트 테스트:

```text
use the oracle-db tool to list profiles
```

## 테스트

Oracle 접속 없이 가능한 단위 테스트:

```powershell
python -m unittest discover -s tests
```

Oracle 접속 테스트는 MCP tool의 `test_connection`으로 수행합니다.

MCP client를 붙이기 전에 로컬에서 먼저 확인하려면:

```powershell
oracle-mcp-check --config profiles.yaml
oracle-mcp-check --config profiles.yaml --profile dev
oracle-mcp-check --config profiles.yaml --profile dev --metadata
```

`--metadata`는 table, view, procedure dictionary view 접근까지 같이 확인합니다.

조회 결과에 CLOB/NCLOB/BLOB/BFILE 컬럼이 있으면 연결이 살아있는 동안 읽어서 반환합니다. 큰 CLOB/NCLOB은 앞부분만 반환하고 `truncated`, `original_length`를 함께 표시합니다. BLOB/BFILE은 base64 prefix와 전체 길이를 반환합니다.

## 안전 제한

`run_select_query`는 다음을 차단합니다.

- `INSERT`, `UPDATE`, `DELETE`, `MERGE`
- `CREATE`, `ALTER`, `DROP`, `TRUNCATE`
- `BEGIN`, `DECLARE`, `CALL`, `EXECUTE`
- multiple statements
- `SELECT FOR UPDATE`
- `DBMS_*`, `UTL_*` 패키지 호출

이 제한은 실수 방지용입니다. 실제 DB 권한은 반드시 read-only 계정으로 분리하는 것이 좋습니다.
