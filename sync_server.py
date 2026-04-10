"""
ThreatPulse 数据同步服务端 - 部署在香港服务器
监听 TCP 9901 端口，接受广州服务器的数据拉取请求
协议：
  客户端发送 JSON: {"action": "sync", "last_id": 123, "last_trending_id": 0, "token": "xxx"}
  服务端返回 JSON: {"status": "ok", "intel_items": [...], "github_trending": [...]}
"""
import os
import socket
import json
import threading
import pymysql
import logging
import time
import hashlib

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/data/Th/sync_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 同步密钥（两端一致）
SYNC_TOKEN = hashlib.sha256(b"ThreatPulse_Sync_2026_HK_GZ").hexdigest()

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "threatpulse",
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": "threatpulse",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

LISTEN_PORT = 9901
MAX_BATCH = 50  # 每次最多同步50条


def fetch_incremental_intel(last_id):
    """获取增量情报数据"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM intel_items WHERE id > %s ORDER BY id ASC LIMIT %s",
                (last_id, MAX_BATCH)
            )
            rows = cur.fetchall()
            # 处理 datetime 和 json 字段
            for row in rows:
                for k, v in row.items():
                    if hasattr(v, 'isoformat'):
                        row[k] = v.isoformat()
                    elif isinstance(v, bytes):
                        row[k] = v.decode('utf-8', errors='replace')
                # 截断过长的 full_text 减小传输量
                if row.get('full_text') and len(str(row['full_text'])) > 2000:
                    row['full_text'] = str(row['full_text'])[:2000]
            return rows
    finally:
        conn.close()


def fetch_incremental_trending(last_id):
    """获取增量 GitHub Trending 数据"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM github_trending WHERE id > %s ORDER BY id ASC LIMIT %s",
                (last_id, MAX_BATCH)
            )
            rows = cur.fetchall()
            for row in rows:
                for k, v in row.items():
                    if hasattr(v, 'isoformat'):
                        row[k] = v.isoformat()
                    elif isinstance(v, bytes):
                        row[k] = v.decode('utf-8', errors='replace')
            return rows
    finally:
        conn.close()


def handle_client(client_sock, addr):
    """处理客户端连接"""
    logger.info(f"客户端连接: {addr}")
    try:
        # 接收请求（最大 64KB）
        data = b""
        client_sock.settimeout(60)
        while True:
            chunk = client_sock.recv(4096)
            if not chunk:
                break
            data += chunk
            # 检查是否收到完整的 JSON
            try:
                json.loads(data.decode('utf-8'))
                break
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

        if not data:
            logger.warning(f"空请求来自 {addr}")
            return

        request = json.loads(data.decode('utf-8'))
        logger.info(f"收到请求: action={request.get('action')}, last_id={request.get('last_id')}, last_trending_id={request.get('last_trending_id')}")

        # 验证 token
        if request.get('token') != SYNC_TOKEN:
            response = {"status": "error", "msg": "认证失败"}
            logger.warning(f"认证失败来自 {addr}")
        elif request.get('action') == 'sync':
            last_id = request.get('last_id', 0)
            last_trending_id = request.get('last_trending_id', 0)

            intel_items = fetch_incremental_intel(last_id)
            trending_items = fetch_incremental_trending(last_trending_id)

            response = {
                "status": "ok",
                "intel_items": intel_items,
                "github_trending": trending_items,
                "intel_count": len(intel_items),
                "trending_count": len(trending_items),
            }
            logger.info(f"返回数据: intel={len(intel_items)}, trending={len(trending_items)}")
        elif request.get('action') == 'ping':
            response = {"status": "ok", "msg": "pong", "time": time.time()}
        else:
            response = {"status": "error", "msg": f"未知操作: {request.get('action')}"}

        # 发送响应
        resp_data = json.dumps(response, ensure_ascii=False, default=str).encode('utf-8')
        # 先发送长度（8字节），再分块发送数据
        length_header = len(resp_data).to_bytes(8, 'big')
        client_sock.sendall(length_header)
        # 分块发送，每块 32KB
        offset = 0
        chunk_size = 32768
        while offset < len(resp_data):
            end = min(offset + chunk_size, len(resp_data))
            client_sock.sendall(resp_data[offset:end])
            offset = end
        logger.info(f"响应已发送: {len(resp_data)} bytes")

    except Exception as e:
        logger.error(f"处理客户端 {addr} 出错: {e}")
        try:
            err_resp = json.dumps({"status": "error", "msg": str(e)}).encode('utf-8')
            length_header = len(err_resp).to_bytes(8, 'big')
            client_sock.sendall(length_header + err_resp)
        except:
            pass
    finally:
        client_sock.close()
        logger.info(f"客户端断开: {addr}")


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1048576)
    server.bind(('0.0.0.0', LISTEN_PORT))
    server.listen(5)
    logger.info(f"ThreatPulse 数据同步服务端启动，监听端口 {LISTEN_PORT}")
    logger.info(f"同步 Token: {SYNC_TOKEN[:16]}...")

    while True:
        try:
            client_sock, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(client_sock, addr), daemon=True)
            t.start()
        except KeyboardInterrupt:
            logger.info("服务端关闭")
            break
        except Exception as e:
            logger.error(f"接受连接出错: {e}")


if __name__ == '__main__':
    main()
