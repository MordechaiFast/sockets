import logging as log
import sys
from dataclasses import dataclass
from selectors import BaseSelector, DefaultSelector, SelectorKey
from selectors import EVENT_READ as READ
from selectors import EVENT_WRITE as WRITE
from socket import AF_INET, SOCK_STREAM
from socket import socket as Socket


@dataclass
class DataBuffer:
    addr: tuple
    in_buffer: bytes = b''
    out_buffer: bytes = b''


def main(host: str , port: int) -> None:
    listening_socket = Socket(AF_INET, SOCK_STREAM)
    listening_socket.bind((host, port))
    listening_socket.listen()
    listening_socket.setblocking(False)
    print(f"Listening on {host}:{port}")
    selector = DefaultSelector()
    selector.register(listening_socket, READ, data=None)
    try:
        while True:
            events = selector.select()
            for key, actions in events:
                if key.data is None:
                    # this socket has not yet been assigned a buffer
                    accept_wrapper(selector, key.fileobj)
                else:
                    service_connection(selector, key, actions)
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, exiting.")
    finally:
        selector.close()


def accept_wrapper(selector: BaseSelector, socket: Socket) -> None:
    connection, addr = socket.accept()
    connection.setblocking(False)
    log.info(f"Accepting connection from {addr[0]}:{addr[1]}")
    actions = READ | WRITE
    data = DataBuffer(addr)
    selector.register(connection, actions, data)


def service_connection(selector: BaseSelector,
                       key: SelectorKey, actions: int) -> None:
    socket, data = key.fileobj, key.data
    if actions & READ:
        if (received_data := socket.recv(1024)):
            data.in_buffer += received_data
            log.info(f"Received {received_data} from "
                     f"{data.addr[0]}:{data.addr[1]}")
            echo(data)
        else:
            # received no data this time, so all data is processed,
            # as far as the server is concerned
            log.info(f"Closing connection to {data.addr[0]}:{data.addr[1]}")
            socket.close()
            selector.unregister(socket)
    if actions & WRITE:
        if data.out_buffer:
            log.info(f"Sending {data.out_buffer} to "
                     f"{data.addr[0]}:{data.addr[1]}")
            # send the data in the out buffer
            # and record the number of bytes sent successfully
            sent_length = socket.send(data.out_buffer)
            # remove the bytes successfully sent from the out buffer
            data.out_buffer = data.out_buffer[sent_length:]


def echo(data: DataBuffer) -> None:
    data.out_buffer += data.in_buffer
    data.in_buffer = b''


log.basicConfig(
    format="%(asctime)s.%(msecs)03d: %(message)s",
    datefmt="%S",
    level=log.INFO
)
if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <host> <port>")
        sys.exit(1)
    host, port = sys.argv[1], int(sys.argv[2])
    main(host, port)
