import os
import time
import logging
import math
from datetime import datetime, timezone
from preprocessing import preprocess_telemetry

import requests
from dotenv import load_dotenv

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS


# =====================================================
# 1. ĐỌC CẤU HÌNH
# =====================================================

load_dotenv()

THINGSBOARD_URL = os.getenv(
    "THINGSBOARD_URL", ""
).rstrip("/")

THINGSBOARD_DEVICE_ID = os.getenv(
    "THINGSBOARD_DEVICE_ID", ""
)

THINGSBOARD_USERNAME = os.getenv(
    "THINGSBOARD_USERNAME", ""
)

THINGSBOARD_PASSWORD = os.getenv(
    "THINGSBOARD_PASSWORD", ""
)

INFLUXDB_URL = os.getenv(
    "INFLUXDB_URL", "http://localhost:8086"
)

INFLUXDB_TOKEN = os.getenv(
    "INFLUXDB_TOKEN", ""
)

INFLUXDB_ORG = os.getenv(
    "INFLUXDB_ORG", ""
)

INFLUXDB_BUCKET = os.getenv(
    "INFLUXDB_BUCKET", ""
)

MEASUREMENT = "sensor_raw"

TELEMETRY_KEYS = [
    "temperature",
    "humidity",
    "distance"
]

POLL_INTERVAL = 2

# True: chỉ ghi bản ghi có đủ 3 trường.
# False: chấp nhận bản ghi có ít nhất 1 trường hợp lệ.
REQUIRE_ALL_FIELDS = True


# =====================================================
# 2. LOGGING
# =====================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# =====================================================
# 3. KIỂM TRA CẤU HÌNH
# =====================================================

def validate_config():
    required = {
        "THINGSBOARD_URL": THINGSBOARD_URL,
        "THINGSBOARD_DEVICE_ID": THINGSBOARD_DEVICE_ID,
        "THINGSBOARD_USERNAME": THINGSBOARD_USERNAME,
        "THINGSBOARD_PASSWORD": THINGSBOARD_PASSWORD,
        "INFLUXDB_URL": INFLUXDB_URL,
        "INFLUXDB_TOKEN": INFLUXDB_TOKEN,
        "INFLUXDB_ORG": INFLUXDB_ORG,
        "INFLUXDB_BUCKET": INFLUXDB_BUCKET
    }

    missing = [
        name
        for name, value in required.items()
        if not value or value.startswith("YOUR_")
    ]

    if missing:
        raise ValueError(
            "Chưa cấu hình đầy đủ: " + ", ".join(missing)
        )


# =====================================================
# 4. BƯỚC 1: ĐĂNG NHẬP THINGSBOARD
# =====================================================

session = requests.Session()


def login_thingsboard():
    url = f"{THINGSBOARD_URL}/api/auth/login"

    payload = {
        "username": THINGSBOARD_USERNAME,
        "password": THINGSBOARD_PASSWORD
    }

    response = session.post(
        url,
        json=payload,
        timeout=15
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Đăng nhập ThingsBoard thất bại: "
            f"HTTP {response.status_code}"
        )

    data = response.json()

    token = data.get("token")

    if not token:
        raise RuntimeError(
            "ThingsBoard không trả về JWT token."
        )

    session.headers.update({
        "X-Authorization": f"Bearer {token}"
    })

    logger.info("Đăng nhập ThingsBoard thành công.")

    return token


# =====================================================
# 5. BƯỚC 2: ĐỌC TELEMETRY
# =====================================================

def fetch_telemetry():
    url = (
        f"{THINGSBOARD_URL}"
        f"/api/plugins/telemetry/DEVICE/"
        f"{THINGSBOARD_DEVICE_ID}/values/timeseries"
    )

    params = {
        "keys": ",".join(TELEMETRY_KEYS)
    }

    response = session.get(
        url,
        params=params,
        timeout=15
    )

    # JWT có thể hết hạn. Đăng nhập lại một lần.
    if response.status_code == 401:
        logger.warning(
            "JWT hết hạn hoặc không hợp lệ. Đăng nhập lại."
        )

        login_thingsboard()

        response = session.get(
            url,
            params=params,
            timeout=15
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"Đọc telemetry thất bại: "
            f"HTTP {response.status_code}; "
            f"nội dung: {response.text[:300]}"
        )

    data = response.json()

    if not isinstance(data, dict):
        raise ValueError(
            "JSON telemetry không có cấu trúc đối tượng."
        )

    return data


# =====================================================
# 6. BƯỚC 3: CHUYỂN JSON THÀNH BẢN GHI THEO TIMESTAMP
# =====================================================

def json_to_records(data):
    """
    Ví dụ JSON ThingsBoard:

    {
        "temperature": [
            {"ts": 1791700000000, "value": "28.5"}
        ],
        "humidity": [
            {"ts": 1791700000000, "value": "65.2"}
        ],
        "distance": [
            {"ts": 1791700000000, "value": "120"}
        ]
    }

    Kết quả:

    [
        {
            "ts": 1791700000000,
            "temperature": 28.5,
            "humidity": 65.2,
            "distance": 120.0
        }
    ]
    """

    records_by_ts = {}

    for key in TELEMETRY_KEYS:
        items = data.get(key, [])

        if not isinstance(items, list):
            logger.warning(
                "Telemetry %s không phải danh sách.", key
            )
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            ts = item.get("ts")
            value = item.get("value")

            if ts is None or value is None:
                continue

            try:
                ts = int(ts)

                # Timestamp ThingsBoard thông thường tính bằng ms.
                # Từ mili giây chuyển thành giây để kiểm tra.
                if ts <= 0:
                    continue

                datetime.fromtimestamp(
                    ts / 1000,
                    tz=timezone.utc
                )

                number = float(value)

                if not math.isfinite(number):
                    continue

            except (
                ValueError,
                TypeError,
                OverflowError,
                OSError
            ):
                continue

            if ts not in records_by_ts:
                records_by_ts[ts] = {"ts": ts}

            records_by_ts[ts][key] = number

    # Sắp xếp bản ghi theo thời gian tăng dần.
    return sorted(
        records_by_ts.values(),
        key=lambda record: record["ts"]
    )


# =====================================================
# 7. BƯỚC 4: KIỂM TRA TÍNH HỢP LỆ
# =====================================================

def validate_records(records):
    valid_records = []

    for record in records:
        ts = record.get("ts")

        if not isinstance(ts, int) or ts <= 0:
            continue

        valid_fields = {}

        for key in TELEMETRY_KEYS:
            if key not in record:
                continue

            try:
                value = float(record[key])

                if not math.isfinite(value):
                    continue

                valid_fields[key] = value

            except (ValueError, TypeError):
                continue

        # Kiểm tra đủ các trường theo cấu hình.
        if REQUIRE_ALL_FIELDS:
            if len(valid_fields) != len(TELEMETRY_KEYS):
                logger.warning(
                    "Bỏ timestamp %s vì thiếu trường telemetry.",
                    ts
                )
                continue

        elif not valid_fields:
            continue

        valid_records.append({
            "ts": ts,
            **valid_fields
        })

    return valid_records


# =====================================================
# 8. KẾT NỐI INFLUXDB
# =====================================================

def create_influx_client():
    client = InfluxDBClient(
        url=INFLUXDB_URL,
        token=INFLUXDB_TOKEN,
        org=INFLUXDB_ORG,
        timeout=15000
    )

    write_api = client.write_api(
        write_options=SYNCHRONOUS
    )

    logger.info("Đã khởi tạo kết nối InfluxDB.")

    return client, write_api


# =====================================================
# 9. BƯỚC 5: GHI DỮ LIỆU VÀO INFLUXDB
# =====================================================

def write_records(write_api, records):
    if not records:
        return 0

    points = []

    for record in records:
        # ThingsBoard trả timestamp theo mili giây.
        # InfluxDB nhận timestamp với độ chính xác ms.
        point = Point(MEASUREMENT).time(
            record["ts"],
            WritePrecision.MS
        )

        for key in TELEMETRY_KEYS:
            if key in record:
                point = point.field(
                    key,
                    float(record[key])
                )

        points.append(point)

    write_api.write(
        bucket=INFLUXDB_BUCKET,
        org=INFLUXDB_ORG,
        record=points
    )

    return len(points)


# =====================================================
# 10. BƯỚC 6: LẶP LẠI SAU 2 GIÂY
# =====================================================

def main():
    validate_config()

    influx_client = None
    write_api = None

    try:
        # Khởi tạo kết nối InfluxDB.
        influx_client, write_api = create_influx_client()

        # Đăng nhập ThingsBoard.
        login_thingsboard()

        while True:
            cycle_start = time.monotonic()

            try:
                # Bước 2: đọc telemetry.
                telemetry = fetch_telemetry()

                # Bước 3: chuyển JSON thành bản ghi.
                records = json_to_records(telemetry)

                # Bước 4: kiểm tra tính hợp lệ.
                valid_records = validate_records(records)

                # Bước 5: ghi InfluxDB.
                written = write_records(
                    write_api,
                    valid_records
                )

                logger.info(
                    "Hoàn tất chu kỳ: nhận %d timestamp, "
                    "hợp lệ %d bản ghi, ghi %d bản ghi.",
                    len(records),
                    len(valid_records),
                    written
                )

            except requests.RequestException as exc:
                logger.error(
                    "Lỗi kết nối ThingsBoard: %s", exc
                )

            except Exception as exc:
                logger.exception(
                    "Lỗi trong chu kỳ thu thập: %s", exc
                )

            # Bước 6: bắt đầu chu kỳ tiếp theo sau 2 giây.
            elapsed = time.monotonic() - cycle_start
            time.sleep(max(0, POLL_INTERVAL - elapsed))

    except KeyboardInterrupt:
        logger.info("Đã dừng chương trình.")

    finally:
        if influx_client is not None:
            influx_client.close()


if __name__ == "__main__":
    main()