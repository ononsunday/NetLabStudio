import socket, threading
def serve(listener):
    conn, _ = listener.accept()
    with conn:
        conn.sendall(conn.recv(4096))
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    thread = threading.Thread(target=serve, args=(listener,)); thread.start()
    with socket.create_connection(listener.getsockname(), timeout=2) as client:
        client.sendall("你好 TCP".encode()); print(client.recv(4096).decode())
    thread.join(2)
