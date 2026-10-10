from pathlib import Path
import sqlite3
from datetime import datetime
from contextlib import closing

root=Path(__file__).resolve().parent
source=root/'data/shop.sqlite3'
if not source.exists():
    raise SystemExit('尚未生成数据库，请先启动商城。')
folder=root/'backups'
folder.mkdir(exist_ok=True)
target=folder/('shop-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
    src.backup(dst)
print('数据库已备份到：'+str(target))
