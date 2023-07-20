import logging as log
from argparse import ArgumentParser, Namespace
from selectors import DefaultSelector
from selectors import EVENT_READ as READ
from selectors import EVENT_WRITE as WRITE
from socket import AF_INET, SOCK_STREAM
from socket import socket as Socket

from handler_lib import ClientMessage

def parse_args() -> Namespace:
    parser = ArgumentParser()
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--action', default='GET')
    parser.add_argument('--value', default='/')
    return parser.parse_args()


def main(host: str, port: int, action: str, value: str) -> None:
    selector = DefaultSelector()
    socket = Socket(AF_INET, SOCK_STREAM)
    socket.setblocking(False)
    socket.connect_ex((host, port))
    log.info(f"Starting connection to {host}:{port}")
    actions = READ | WRITE
    request = create_request(action, value)
    data = ClientMessage(selector, socket, (host, port), request)
    selector.register(socket, actions, data)
    try:
        while selector.get_map():
            # while there are sockets being monitored
            events = selector.select(timeout=1)
            for key, actions in events:
                handler = key.data
                try:
                    if actions & WRITE:
                        handler.write()
                    if actions & READ:
                        handler.read()
                except (ValueError, TypeError, ConnectionError) as error:
                    log.error(f"Error on {handler.addr}:")
                    log.error(error)
                    handler.close()
        log.info("All connections closed. Exiting.")
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, exiting.")
    finally:
        selector.close()


def create_request(action, value):
    if action == "search":
        return {
            "type": "text/json",
            "encoding": "utf-8",
            "content": {"action": action, "value": value},
        }
    else:
        return {
            "type": "binary/custom-client-binary-type",
            "encoding": "binary",
            "content": (action + value).encode(),
        }


log.basicConfig(
    format="%(asctime)s.%(msecs)03d: %(message)s", 
    datefmt="%S",
    level=log.INFO
)
if __name__ == '__main__':
    args = parse_args()
    main(args.host, args.port, args.action, args.value)
