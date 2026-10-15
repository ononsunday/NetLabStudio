import socket, threading, hashlib, struct
def exact(conn, n):
    data = bytearray()
    while len(data) < n:
        part = conn.recv(n-len(data))
        if not part: raise EOFError("truncated")
        data.extend(part)
    return bytes(data)
def receive(listener):
    conn, _ = listener.accept()
    with conn:
        n = struct.unpack("!I", exact(conn, 4))[0]
        if n > 1048576: return
        data = exact(conn, n); conn.sendall(hashlib.sha256(data).hexdigest().encode())
payload = b"NetLab file transfer" * 4096
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    thread = threading.Thread(target=receive, args=(listener,)); thread.start()
    with socket.create_connection(listener.getsockname(), timeout=2) as client:
        client.sendall(struct.pack("!I", len(payload)) + payload)
        actual = exact(client, 64).decode(); print("SHA256:", actual)
        print("verified:", actual == hashlib.sha256(payload).hexdigest())
    thread.join(2)
