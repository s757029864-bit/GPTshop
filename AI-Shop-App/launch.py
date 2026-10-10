"""Double-click launcher: starts the local service and opens the requested page."""
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import json
import webbrowser

root=Path(__file__).resolve().parent
url='http://127.0.0.1:8766'
admin='--admin' in sys.argv

def ready():
    try:
        with urllib.request.urlopen(url+'/api/health',timeout=2) as response:
            value=json.load(response)
            return value.get('version')==2 and value.get('mode')=='demo'
    except Exception:
        return False

def open_page():
    keyfile=root/'data/setup-key.txt'
    if admin and keyfile.exists():
        with urllib.request.urlopen(url+'/api/me',timeout=2) as response:
            if json.load(response).get('setup_needed'):
                print('\n首次设置管理员时，请复制下方初始化码：\n'+keyfile.read_text(encoding='utf-8')+'\n')
    webbrowser.open(url+('/admin' if admin else '/'))

if ready():
    open_page()
    input('网站已在运行，按回车关闭本窗口。')
else:
    process=subprocess.Popen([sys.executable,str(root/'server.py')],cwd=root)
    try:
        for _ in range(50):
            if ready(): break
            if process.poll() is not None: raise RuntimeError('服务未能启动，请检查 8766 端口是否已被其他程序占用。')
            time.sleep(.1)
        else: raise RuntimeError('启动超时，请查看窗口提示。')
        open_page()
        print('本机功能体验版已经启动。保持本窗口打开；按 Ctrl+C 停止。')
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
    except Exception as exc:
        print(str(exc))
        process.terminate()
        process.wait()
        input('按回车关闭。')
