import socket, selectors
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    with socket.create_connection(listener.getsockname(), timeout=2) as client:
        conn, _ = listener.accept()
        with conn, selectors.DefaultSelector() as selector:
            conn.setblocking(False); selector.register(conn, selectors.EVENT_READ)
            client.sendall(b"select event")
            for key, event in selector.select(timeout=2):
                data = key.fileobj.recv(4096); key.fileobj.sendall(data)
            print(client.recv(4096).decode())
