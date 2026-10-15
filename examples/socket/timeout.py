import socket
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    with socket.create_connection(listener.getsockname(), timeout=2) as client:
        conn, _ = listener.accept()
        with conn:
            client.settimeout(0.1)
            try: client.recv(4096)
            except socket.timeout: print("timeout handled: server sent no data")
