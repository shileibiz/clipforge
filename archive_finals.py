#!/usr/bin/env python3
"""ClipForge 成片归档：projects/*/output/*.mp4 → \\192.168.2.180\transfer\videos\ → 字节校验。
用 btbox venv 跑(smbprotocol)；幂等(状态文件)；本地成片保留不删。
用法: ~/btbox/.venv/bin/python ~/clipforge/archive_finals.py [--once]
"""
import argparse
import glob
import json
import os
import sys
import time

import smbclient

PROJECTS = '/home/dev/clipforge/projects'
REMOTE_DIR = '\\\\192.168.2.180\\transfer\\videos'
STATE = '/home/dev/clipforge/.archived_clips.json'
STABLE_SECS = 120          # 2 分钟无增长视为渲染完成
CHUNK = 4 * 1024 * 1024


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(st):
    json.dump(st, open(STATE, 'w'))


def iter_finals():
    out = []
    for f in sorted(glob.glob(os.path.join(PROJECTS, '*', 'output', '*.mp4'))):
        out.append(f)
    return out


def smb_size(p):
    try:
        return smbclient.stat(p).st_size
    except OSError:
        return None


def upload(src, dst, total):
    have = smb_size(dst) or 0
    if have >= total:
        return True
    with open(src, 'rb') as fo, smbclient.open_file(dst, 'wb' if have == 0 else 'r+b') as fd:
        fo.seek(have)
        fd.seek(have)
        while True:
            buf = fo.read(CHUNK)
            if not buf:
                break
            fd.write(buf)
    return smb_size(dst) == total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--once', action='store_true', help='跑一轮就退出(默认常驻循环)')
    args = ap.parse_args()
    # transfer 共享 guest 会话(2026-10-02 实测匿名裸连已不行, guest+空密码可读写)
    import smbclient
    smbclient.register_session('192.168.2.180', username='guest', password='')
    state = load_state()
    while True:
        moved = 0
        for src in iter_finals():
            try:
                st = os.stat(src)
            except OSError:
                continue
            age_ok = time.time() - st.st_mtime >= STABLE_SECS
            key = src
            if state.get(key, {}).get('size') == st.st_size:
                continue  # 已归档(幂等)
            if not age_ok:
                continue
            proj = os.path.basename(os.path.dirname(os.path.dirname(src)))
            dst = REMOTE_DIR + '\\' + f'{proj}-{os.path.basename(src)}'
            print(f'[archive] {src} -> {dst} ({st.st_size} bytes)', flush=True)
            if upload(src, dst, st.st_size):
                state[key] = {'size': st.st_size, 'remote': dst,
                              'archived_at': time.strftime('%F %T')}
                save_state(state)
                moved += 1
                print(f'[archive] OK 校验通过: {dst}', flush=True)
            else:
                print(f'[archive] FAIL 校验不一致: {dst}', flush=True)
        if args.once:
            print(f'[archive] once 模式完成, 本轮归档 {moved} 个', flush=True)
            return
        time.sleep(300)


if __name__ == '__main__':
    main()
