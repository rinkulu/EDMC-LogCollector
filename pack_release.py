import zipfile
from datetime import datetime, timezone

files = ['load.py', 'L10n/en.strings', 'L10n/ru.strings', "LICENSE"]
now = datetime.now(timezone.utc)
fixed_datetime = (now.year, now.month, now.day, now.hour, now.minute, now.second)

with zipfile.ZipFile('EDMC-LogCollector.zip', 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    for file_path in files:
        zinfo = zipfile.ZipInfo(filename=file_path, date_time=fixed_datetime)
        zinfo.compress_type = zipfile.ZIP_DEFLATED
        with open(file_path, 'rb') as f:
            zf.writestr(zinfo, f.read())
