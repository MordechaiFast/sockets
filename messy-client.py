import logging as log
import random
import time
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from selectors import EVENT_READ as READ
from selectors import EVENT_WRITE as WRITE
from selectors import BaseSelector, DefaultSelector, SelectorKey
from socket import AF_INET, SOCK_STREAM
from socket import socket as Socket


@dataclass
class ConnectionState:
    conn_id: int
    messages: list[bytes]
    expected_echo_length: int
    received_length: int = 0
    out_buffer: bytes = b''
    in_buffer: bytes = b''

    
def parse_args() -> Namespace:
    parser = ArgumentParser()
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--num_conns', type=int, default=3)
    parser.add_argument('--names', action='append', nargs='+',
                        default=['Elimelech\n', 'Etty\n', 'Tippy\n', 
                                 'Yaakov\n', 'Leah\n', 'Noah\n'])
    return parser.parse_args()


def main(host:str, port:int, num_conns: int, names: list[str]) -> None:
    byte_names = [name.encode() for name in names]
    selector = DefaultSelector()
    for conn_index in range(1, num_conns+1):
        socket = Socket(AF_INET, SOCK_STREAM)
        socket.setblocking(False)
        socket.connect_ex((host, port))
        log.info(f"Starting connection {conn_index} to {host}:{port}")
        actions = READ | WRITE
        rand_names = [random.choice(byte_names) 
                      for _ in range(round(len(names)/2) or 1)]
        data = ConnectionState(
            conn_id=conn_index,
            messages=rand_names,
            expected_echo_length=sum(len(name) for name in rand_names)
        )
        selector.register(socket, actions, data)
    try:
        while selector.get_map():
            # while there are sockets being monitored
            events = selector.select(timeout=1)
            for key, actions in events:
                service_connection(selector, key, actions)
        log.info("All connections closed. Exiting.")
    except KeyboardInterrupt:
        log.error("\nKeyboard interrupt received, exiting.")
    finally:
        selector.close()


def service_connection(selector: BaseSelector,
                       key: SelectorKey, actions: int) -> None:
    """Sends data at an uneven rate, 
    and checks received data that it gets to the end of the message"""
    socket, data = key.fileobj, key.data
    if not data.out_buffer and data.messages:
        # if there is no message waiting to be fully sent,
        # put the next message in the out buffer
        data.out_buffer = data.messages.pop(0)
    if actions & WRITE:
        if data.out_buffer:
            log.info(f"Sending {data.out_buffer} to connection {data.conn_id}")
            # send the data in the out buffer
            # and record the number of bytes sent successfully
            artificial_cap = random.randint(0, len(data.out_buffer))
            sent_length = socket.send(data.out_buffer[:artificial_cap])
            # remove the bytes successfully sent from the out buffer
            data.out_buffer = data.out_buffer[sent_length:]
            time.sleep(.001)
    if actions & READ:
        if (recv_data := socket.recv(1024)):
            data.received_length += len(recv_data)
            data.in_buffer += recv_data
            log.info(f"Recived data from connection {data.conn_id}")
    if data.received_length == data.expected_echo_length:
        log.info(f"Closing connection {data.conn_id}")
        socket.close()
        selector.unregister(socket)
    if data.in_buffer and data.in_buffer[-1] == 10: #'\n'
        # print full lines from the message
        print(data.in_buffer[:-1].decode())
        data.in_buffer = b''


log.basicConfig(
    format="%(asctime)s.%(msecs)03d: %(message)s", 
    datefmt="%S",
    level=log.INFO
)
if __name__ == '__main__':
    args = parse_args()
    main(args.host, args.port, args.num_conns, args.names)
