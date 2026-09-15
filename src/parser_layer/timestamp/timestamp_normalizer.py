from datetime import datetime


FORMATS = [

    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S %z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f"

]


class TimestampNormalizer:

    def normalize(self, ts):

        if not ts:
            return None

        ts = ts.strip()

        for fmt in FORMATS:

            try:

                dt = datetime.strptime(ts, fmt)

                return int(dt.timestamp())

            except Exception:
                continue

        return None