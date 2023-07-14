import logging as log
import sys
from socket import AF_INET, SOCK_STREAM
from socket import socket as Socket

log.basicConfig(
   format="%(asctime)s: %(message)s", 
   datefmt="%d/%b/%Y %H:%M:%S",
   level=log.INFO
)
host, port = 'localhost', 8000

with Socket(family=AF_INET, type=SOCK_STREAM) as socket:
    socket.bind((host, port))
    socket.listen()
    log.info(f"Listening on address {host} port {port}")
    for _ in (1,2):
        conn, addr = socket.accept()
        log.info(f"Accepting connection from {addr[0]}:{addr[1]}")
        with conn:
            while (data := conn.recv(1024)):
                log.info(f"Received: {data}")
                response = bytes(f"That was {len(data)} bytes long.", 'utf-8')
                log.info(f"Sending: {response}")
                conn.sendall(response)
