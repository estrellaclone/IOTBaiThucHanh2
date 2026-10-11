import math
from datetime import datetime, timezone


# Các trường telemetry cần xử lý
TELEMETRY_KEYS = [
    "temperature",
    "humidity",
    "distance"
]

# Giới hạn tham khảo, cần điều chỉnh theo cảm biến thực tế
VALID_RANGES = {
    "temperature": (-40, 80),
    "humidity": (0, 100),
    "distance": (2, 400)
}


def preprocess_telemetry(data):
    """
    Tiền xử lý dữ liệu telemetry từ ThingsBoard.

    Đầu vào:
        data: JSON telemetry từ ThingsBoard API.

    Đầu ra:
        valid_records: danh sách bản ghi hợp lệ.
        stats: thống kê dữ liệu.
    """

    records_by_ts = {}
    seen_timestamps = set()

    stats = {
        "received": 0,
        "invalid": 0,
        "out_of_range": 0,
        "duplicate": 0,
        "incomplete": 0,
        "valid": 0
    }

    # Bước 1: Chuyển JSON thành các bản ghi theo timestamp
    for key in TELEMETRY_KEYS:

        items = data.get(key, [])

        if not isinstance(items, list):
            stats["invalid"] += 1
            continue

        for item in items:

            stats["received"] += 1

            if not isinstance(item, dict):
                stats["invalid"] += 1
                continue

            try:
                ts = int(item["ts"])
                value = float(item["value"])

                # Kiểm tra timestamp và giá trị số
                if ts <= 0 or not math.isfinite(value):
                    stats["invalid"] += 1
                    continue

                # Kiểm tra timestamp theo đơn vị mili giây
                datetime.fromtimestamp(
                    ts / 1000,
                    tz=timezone.utc
                )

            except (
                KeyError,
                ValueError,
                TypeError,
                OverflowError,
                OSError
            ):
                stats["invalid"] += 1
                continue

            # Bước 2: Kiểm tra phạm vi giá trị
            low, high = VALID_RANGES[key]

            if not low <= value <= high:
                stats["out_of_range"] += 1
                continue

            # Bước 3: Loại bỏ dữ liệu trùng theo trường và timestamp
            duplicate_key = (key, ts)

            if duplicate_key in seen_timestamps:
                stats["duplicate"] += 1
                continue

            seen_timestamps.add(duplicate_key)

            # Bước 4: Ghép các trường có cùng timestamp
            if ts not in records_by_ts:
                records_by_ts[ts] = {"ts": ts}

            records_by_ts[ts][key] = value

    # Bước 5: Kiểm tra dữ liệu thiếu và sắp xếp thời gian
    valid_records = []

    for ts in sorted(records_by_ts):

        record = records_by_ts[ts]

        # Chỉ giữ bản ghi có đủ 3 trường
        if not all(
            key in record
            for key in TELEMETRY_KEYS
        ):
            stats["incomplete"] += 1
            continue

        valid_records.append(record)

    stats["valid"] = len(valid_records)

    return valid_records, stats