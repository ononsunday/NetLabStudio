import socket, threading
def chat(listener):
    peers = [listener.accept()[0] for _ in range(2)]
    try:
        message = peers[0].recv(4096)
        for peer in peers: peer.sendall(message)
    finally:
        for peer in peers: peer.close()
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    thread = threading.Thread(target=chat, args=(listener,)); thread.start()
    with socket.create_connection(listener.getsockname(), timeout=2) as alice, socket.create_connection(listener.getsockname(), timeout=2) as bob:
        alice.sendall(b"Alice: hello Bob")
        print("Alice received:", alice.recv(4096).decode()); print("Bob received:", bob.recv(4096).decode())
    thread.join(2)
