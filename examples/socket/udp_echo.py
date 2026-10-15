import socket
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
    server.bind(("127.0.0.1", 0)); server.settimeout(2); client.settimeout(2)
    client.sendto(b"hello UDP", server.getsockname())
    data, peer = server.recvfrom(4096); server.sendto(data, peer)
    print(client.recvfrom(4096)[0].decode())
