from peer import PeerConnection
from bencodepy import encode, decode
import struct
import hashlib
import urllib.parse
import socket
import math


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
