from peer import PeerConnection
from bencodepy import encode, decode
import struct
import hashlib
import urllib.parse
import socket
import math
from asyncio import DatagramProtocol
import asyncio

# These are the actions that we can send to the UDP tracker
UDP_CONNECT = 0
UDP_ANNOUNCE = 1
UDP_SCRAPE = 2
UDP_ERROR = 3

# These are the events that we can send to the UDP tracker
UDP_NONE_EVENT = 0
UDP_COMPLETED_EVENT = 1
UDP_STARTED_EVENT = 2
UDP_STOPPED_EVENT = 3

class UdpTrackerProtocol(DatagramProtocol):
    def __init__(self, future, action, connection_id):
        self.future = future
        self.action = action
        self.connection_id = connection_id

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if self.action == UDP_CONNECT:
            connection_id = struct.unpack(">Q", data[8:16])[0]
            self.future.set_result(connection_id)
        elif self.action == UDP_ANNOUNCE:
            interval, leechers, seeders = struct.unpack(">III", data[8:20])
            peers = [
                (socket.inet_ntoa(data[i : i + 4]), struct.unpack(">H", data[i + 4 : i + 6])[0])
                for i in range(20, len(data), 6)
            ]
            self.future.set_result((interval, leechers, seeders, peers))
        else:
            self.future.set_exception(Exception(f"Unknown action: {self.action}"))

    def error_received(self, exc):
        self.future.set_exception(exc)
        

class Tracker:
    def __init__(self, path, torrent):
        with open(path, "rb") as f:
            torrent_data = f.read()
        torrent = decode(torrent_data)
        self.announce = torrent.get(b"announce", b"").decode("utf-8")
        self.announce_host, self.announce_port = self.announce.split("/")[2].split(":")
        self.announce_port = int(self.announce_port)
        self.announce_list = torrent.get(b"announce-list", [])
        self.announce_list = [
            [url.decode("utf-8") for url in group] for group in self.announce_list
        ]
        self.creation_date = torrent.get(b"creation date", "N/A")
        self.comment = torrent.get(b"comment", b"").decode("utf-8")
        self.created_by = torrent.get(b"created by", b"").decode("utf-8")
        self.encoding = torrent.get(b"encoding", b"").decode("utf-8")
        self.info = torrent[b"info"]
        self.info_hash = hashlib.sha1(encode(self.info)).digest()
        self.piece_length = self.info[b"piece length"]
        self.pieces = self.info[b"pieces"]
        self.private = self.info.get(b"private", 0)
        self.name = self.info[b"name"].decode("utf-8")
        self.length = self.info[b"length"]
        self.mdf5sum = self.info.get(b"md5sum", b"").decode("utf-8")
        self.num_pieces = math.ceil(self.length / self.piece_length)
        self.blocks_per_piece = math.ceil(self.piece_length / 2**14)
        self.torrent = torrent

    
    async def udp_tracker_request(self, event):
        loop = asyncio.get_running_loop()

        for url in self.announce_list:
            if url.startswith("udp://"):
                url_parts = urllib.parse.urlparse(url)
                tracker_host = url_parts.hostname
                tracker_port = url_parts.port

                # UDP tracker connection protocol
                # Step 1: Connect request
                connect_request = struct.pack(">QII", 0x41727101980, UDP_CONNECT, 0)
                connect_future = loop.create_future()
                transport, protocol = await loop.create_datagram_endpoint(
                    lambda: UdpTrackerProtocol(connect_future, UDP_CONNECT, 0),
                    remote_addr=(tracker_host, tracker_port),
                )
                transport.sendto(connect_request)
                connection_id = await connect_future

                # Step 2: Announce request
                announce_request = struct.pack(
                    ">QII20s20sQQQIIIH",
                    connection_id,
                    UDP_ANNOUNCE,
                    0,
                    self.info_hash,
                    self.peer_id.encode(),
                    0,  # downloaded
                    self.length,  # left
                    0,  # uploaded
                    event,
                    0,  # IP address (0 means default)
                    0,  # key
                    -1,  # num_want
                    self.port,  # port
                )
                announce_future = loop.create_future()
                transport, protocol = await loop.create_datagram_endpoint(
                    lambda: UdpTrackerProtocol(
                        announce_future, UDP_ANNOUNCE, connection_id
                    ),
                    remote_addr=(tracker_host, tracker_port),
                )
                transport.sendto(announce_request)
                interval, leechers, seeders, peers = await announce_future

                self.interval = interval
                self.peers = peers

                break  # Stop after the first successful tracker
            
    def __str__(self):
        output = (
            f"Info Hash: {self.info_hash}\n"
            f"Announce URL: {self.announce}\n"
            f"Announce List: {self.announce_list}\n"
            f"Creation Date: {self.creation_date}\n"
            f"Comment: {self.comment}\n"
            f"Created By: {self.created_by}\n"
            f"Encoding: {self.encoding}\n"
            f"Piece Length: {self.piece_length} bytes\n"
            f"Private: {self.private}\n"
            f"Name: {self.name}\n"
            f"Length: {self.length}\n"
            f"MD5Sum: {self.mdf5sum}\n"
        )
        return output


if __name__ == "__main__":
    a = Tracker("test/debian-11.6.0-amd64-netinst.iso.torrent")
    print(a)
