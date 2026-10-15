import socket, threading
def handle(conn):
    with conn: conn.sendall(conn.recv(4096))
def serve(listener):
    workers = []
    for _ in range(3):
        conn, _ = listener.accept(); t = threading.Thread(target=handle, args=(conn,)); t.start(); workers.append(t)
    for t in workers: t.join(2)
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    worker = threading.Thread(target=serve, args=(listener,)); worker.start()
    for i in range(3):
        with socket.create_connection(listener.getsockname(), timeout=2) as client:
            client.sendall(("client %d" % i).encode()); print(client.recv(4096).decode())
    worker.join(2)
