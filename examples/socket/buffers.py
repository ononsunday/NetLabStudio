import socket, threading, time
payload = b"x" * 262144
def serve(listener):
    conn, _ = listener.accept(); total = 0
    with conn:
        while True:
            data = conn.recv(4096)
            if not data: break
            total += len(data)
        conn.sendall(str(total).encode())
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    thread = threading.Thread(target=serve, args=(listener,)); thread.start()
    with socket.create_connection(listener.getsockname(), timeout=2) as client:
        client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)
        start = time.perf_counter(); client.sendall(payload); client.shutdown(socket.SHUT_WR)
        total = int(client.recv(100)); elapsed = time.perf_counter()-start
        print("received bytes:", total); print("loopback MiB/s:", round(total/1048576/elapsed, 2))
    thread.join(2)
