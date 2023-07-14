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
byte_message = b'Hello, server'
with Socket(family=AF_INET, type=SOCK_STREAM) as socket:
    socket.connect((host, port))
    log.info(f"Connected to host {host} port {port}")
    log.info(f"Sending: {byte_message}")
    socket.sendall(byte_message)
    data = socket.recv(1024)
    log.info(f"Received: {data}")
    
