import logging as log
import sys
from dataclasses import dataclass
from selectors import BaseSelector, DefaultSelector, SelectorKey
from selectors import EVENT_READ as READ
from selectors import EVENT_WRITE as WRITE
from socket import AF_INET, SOCK_STREAM
from socket import socket as Socket


@dataclass
class ConnectionState:
    conn_id: int
    messages: list[bytes]
    expected_message_length: int
    received_length: int = 0
    out_buffer: bytes = b''


def main(host:str, port:int, num_conns: int, messages: list[bytes]) -> None:
    selector = DefaultSelector()
    for conn_index in range(1, num_conns+1):
        socket = Socket(AF_INET, SOCK_STREAM)
        socket.setblocking(False)
        socket.connect_ex((host, port))
        log.info(f"Starting connection {conn_index} to {host}:{port}")
        actions = READ | WRITE
        data = ConnectionState(
            conn_id=conn_index,
            messages=messages.copy(),
            expected_message_length=sum(len(message) for message in messages)
        )
        selector.register(socket, actions, data)
    try:
        while selector.get_map():
            # while there are sockets being monitored
            if (events := selector.select(timeout=1)):
                for key, actions in events:
                    service_connection(selector, key, actions)
        log.info("All connections closed. Exiting.")
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, exiting.")
    finally:
        selector.close()


def service_connection(selector: BaseSelector,
                       key: SelectorKey, actions: int) -> None:
    socket, data = key.fileobj, key.data
    if actions & WRITE:
        if data.out_buffer:
            log.info(f"Sending {data.out_buffer} to connection {data.conn_id}")
            # send the data in the out buffer
            # and record the number of bytes sent successfully
            sent_length = socket.send(data.out_buffer)
            # remove the bytes successfully sent from the out buffer
            data.out_buffer = data.out_buffer[sent_length:]
        elif data.messages:
            # if there is no message waiting to be fully sent,
            # put the next message in the out buffer
            data.out_buffer = data.messages.pop(0)
    if actions & READ:
        if (recv_data := socket.recv(1024)):
            data.received_length += len(recv_data)
            log.info(f"Recived {recv_data} from connection {data.conn_id}")
            # Do nothing with this data
        if data.received_length == data.expected_message_length:
            log.info(f"Closing connection {data.conn_id}")
            socket.close()
            selector.unregister(socket)


log.basicConfig(
    format="%(asctime)s.%(msecs)03d: %(message)s", 
    datefmt="%S",
    level=log.INFO
)
if __name__ == '__main__':
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <host> <port> <number of connections>")
        sys.exit(1)
    host, port = sys.argv[1], int(sys.argv[2])
    num_conns = int(sys.argv[3])
    messages = [b"Message 1 from client.", b"Message 2 from client."]
    main(host, port, num_conns, messages)
