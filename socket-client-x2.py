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
long_message = b'Client data: ' + b'0000000100100011010001010110011110001001101010111100110111101111'*16

with Socket(family=AF_INET, type=SOCK_STREAM) as socket1:
    log.info("Connecting to port")
    socket1.connect((host, port))
    log.info(f"Connected to host {host} port {port}")
    log.info(f"Sending: {byte_message}")
    socket1.sendall(byte_message)
    data = socket1.recv(1024)
    log.info(f"Received: {data}")
with Socket(family=AF_INET, type=SOCK_STREAM) as socket2:
    log.info("Connecting to port")
    socket2.connect((host, port))
    log.info(f"Connected to host {host} port {port}")
    log.info(f"Sending: {long_message}")
    socket2.sendall(long_message)
    data = socket2.recv(1024)
    log.info(f"Received: {data}")
    data = socket2.recv(1024)
    log.info(f"Received: {data}")
    
