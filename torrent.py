from tracker import Tracker
from peer import PeerConnection
import random
import socket
from bencodepy import decode
import struct
import urllib.parse
import asyncio
from download import DownloadHandler, FileWriter
import traceback
from utils import pretty_print
from seeder import Seeder


class Torrent:
    def __init__(
        self,
        path,
        verbose=True,
        port=6881,
        compact=0,
        max_connections=50,
        preferred_file_name=None,
    ):
        self.peer_id = "-WC0001-" + "".join(
            [str(random.randint(0, 9)) for _ in range(12)]
        )
        self.port = port  # what port is the client reading from
        self.compact = compact  # do we accept compact responses
        self.uploaded = 0  # bytes uploaded
        self.downloaded = 0  # bytes downloaded
        self.event = "started"  # auto-set to started and will be updated over time
        self.interval = 0
        self.complete = False  # used for seeding
        self.peer_list = []  # empty to start
        self.max_connections = max_connections
        self.verbose = verbose  # if you want to allow stacktrace printing
        # prevents race conditions when updating peer list
        self.peer_list_lock = asyncio.Lock()
        self.tracker = Tracker(path, self)
        self.filewriter = FileWriter(preferred_file_name or self.tracker.name, self)
        self.download_handler = DownloadHandler(self.tracker, self)
        self.left = self.tracker.length  # bytes left before fiel is complete
        self.ping_tracker()  # interval and peer list are updated

    def make_HTTP_request(self):
        params = {
            "info_hash": urllib.parse.quote(self.tracker.info_hash),
            "peer_id": self.peer_id,
            "port": self.port,
            "uploaded": self.uploaded,
            "downloaded": self.downloaded,
            "left": self.left,
            "compact": self.compact,
            "event": self.event,
        }
        host = self.tracker.announce.split("/")[2]
        payload_start = self.tracker.announce.replace("http://", "").replace(
            self.tracker.announce.split("/")[2], ""
        )
        request_path = (
            payload_start
            + "?"
            + "&".join([f"{key}={value}" for key, value in params.items()])
        )
        request = (
            f"GET {request_path} HTTP/1.1\r\n"
            + f"Host: {host}\r\n"
            + "Connection: close\r\n\r\n"
        )

        return request

    def ping_tracker(self):
        tracker_data = self.tracker
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((tracker_data.announce_host, tracker_data.announce_port))
            request = self.make_HTTP_request()
            sock.sendall(request.encode("utf-8"))
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
            _, payload = response.split(b"\r\n\r\n", 1)
            tracker_data = decode(payload)
            self.interval = tracker_data.get(b"interval", 0)
            if type(tracker_data.get(b"peers")) == bytes:
                peers_raw = tracker_data.get(b"peers", b"")
                for i in range(
                    0, len(peers_raw), 6
                ):  # iterate through the values in peers_raw
                    try:
                        ip = socket.inet_ntoa(peers_raw[i : i + 4])
                        port = struct.unpack(">H", peers_raw[i + 4 : i + 6])[0]
                        peer = PeerConnection(  # create a new connection for each peer
                            self.download_handler,
                            ip,
                            port,
                            self.peer_id,
                            self.tracker.info_hash,
                            self.filewriter,
                            self,
                            self.verbose,  # flag to allow stacktrace printing
                        )
                        # add the peers to the list
                        self.peer_list.append(peer)
                    except:
                        if self.verbose:
                            traceback.print_exc()
            else:
                peers_list = tracker_data.get(b"peers", [])
                for peer_dict in peers_list:
                    ip = peer_dict[b"ip"]
                    port = peer_dict[b"port"]
                    peer = PeerConnection(  # create a new connection for each peer
                        self.download_handler,
                        ip,
                        port,
                        self.peer_id,
                        self.tracker.info_hash,
                        self.filewriter,
                        self,
                        self.verbose,  # flag to allow stacktrace printing
                    )
                    self.peer_list.append(peer)

    async def initiate_download(self):
        async with self.peer_list_lock:
            await asyncio.gather(*(peer.start() for peer in self.peer_list))

    async def refresh_peers(self):
        while True:
            pretty_print("refresing peers", "cyan")
            async with self.peer_list_lock:
                # self.peer_list = []
                self.ping_tracker()
            await asyncio.sleep(self.interval)

    
    
    def ping_tracker_complete(self):
        self.event = "completed"
        self.downloaded = self.tracker.length
        self.left = 0
        tracker_data = self.tracker
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((tracker_data.announce_host, tracker_data.announce_port))
            request = self.make_HTTP_request()
            sock.sendall(request.encode("utf-8"))
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
            _, payload = response.split(b"\r\n\r\n", 1)
            tracker_data = decode(payload)
            self.interval = tracker_data.get(b"interval", 0)
            self.event = "started"  # reset the event back to "started"
        
        
        
    # ip addr of the seeder is 0.0.0.0
    # port is 6886
    # put these as cli args
    async def seed(self):
        self.ping_tracker_complete()
        pretty_print("starting seeding", "cyan")
        server = Seeder('0.0.0.0', 6886, self.peer_id,  self.tracker.info_hash, self.filewriter, self)
        await server.start()

    # the program only starts seeding five seconds
    # after the download is complete
    async def start_seeding(self):
        started = False
        while True:
            await asyncio.sleep(5)
            if self.complete == True and started == False:
                started = True
                await asyncio.gather(
                    self.seed(),
                )

    async def start_connections(self, preferred_peer_list=None):
        self.peer_list = preferred_peer_list or self.peer_list
        # append tasks here to run them concurrently
        await asyncio.gather(
            self.initiate_download(),  # task 1
            self.start_seeding()
        )

        await asyncio.gather(
            # self.initiate_download(),  # task 1
            self.refresh_peers(),  # task 2
            # self.start_seeding()
        )
