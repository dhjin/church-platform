"""정기 청구 배치. k8s CronJob 에서 `python -m billing.run_due` 로 실행한다."""
import json
import sys

from database import get_conn
from billing.service import run_due


def main() -> int:
    conn = get_conn()
    try:
        counts = run_due(conn)
    finally:
        conn.close()
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
