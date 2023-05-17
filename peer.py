import asyncio
import selectors
import socket
import struct
import traceback
from utils import pretty_print
from download import FileWriter
import time

CHOKE = 0
UNCHOKE = 1
INTERESTED = 2
NOTINTERESTED = 3
HAVE = 4
BITFIELD = 5
REQUEST = 6
PIECE = 7
CANCEL = 8
PORT = 9


class PeerConnection:
    def __init__(
        self,
        download_handler,
        ip,
        port,
        peer_id,
        info_hash,
        filewriter,
        torrent,
        verbose=True,
    ):
        self.waiting = False
        self.filewriter = filewriter
        self.torrent = torrent
        self.download_handler = download_handler
        self.pieces = set()
        self.pending_piece = None
        self.peer_ip = ip
        self.peer_port = port
        self.client_id = peer_id
        self.info_hash = info_hash
        self.reader = None
        self.writer = None
        self.connection_try = 0  # number of times we tried to connect to this peer
        self.verbose = verbose  # if you want to allow stacktrace printing
        self.start_time = time.time()  # record the start time of the download
        self.total_pieces = (
            download_handler.tracker.num_pieces
        )  # total number of pieces

    async def start(self):
        try:
            await self.send_handshake()
            await self.validate_handshake()
            await self.listen()
        except:
            if self.writer:
                self.writer.close()
            if self.verbose:
                traceback.print_exc()
            pretty_print("===Lost peer!===", "red")
            self.torrent.peer_list.remove(self)
            if self.pending_piece:
                self.download_handler.pending_pieces.append(self.pending_piece)

    def make_handshake(self):
        return struct.pack(
            ">B19s8s20s20s",
            19,
            "BitTorrent protocol".encode("utf-8"),
            bytes([0] * 8),
            self.info_hash,
            self.client_id.encode("utf-8"),
        )

    async def send_handshake(self):
        self.connection_try += (
            1  # increment the number of times we tried to connect to this peer
        )
        self.reader, self.writer = await asyncio.open_connection(
            self.peer_ip, self.peer_port
        )
        self.writer.write(self.make_handshake())
        await self.writer.drain()

    async def validate_handshake(self):
        recv_data = await self.reader.readexactly(68)
        recv_hash = recv_data[28:48]
        if recv_hash != self.info_hash:
            raise Exception("The hashes did not match")
        else:
            pretty_print("Handshake validated 🤝", "green")

    def calculate_time_since_download_started(self):
        # time stuff
        completed_pieces = len(self.download_handler.finished_pieces)
        percent_complete = round(completed_pieces * 100 / self.total_pieces)

        elapsed_time = time.time() - self.start_time  # total time taken so far
        estimated_total_time = (
            elapsed_time * self.total_pieces / completed_pieces
        )  # estimate total time
        estimated_remaining_time = (
            estimated_total_time - elapsed_time
        )  # estimate remaining time
        return percent_complete, estimated_remaining_time

    # Converts time in seconds to a more human-readable format.
    def format_time(self, seconds):
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
        elif minutes > 0:
            return f"{int(minutes)}m {int(seconds)}s"
        else:
            return f"{seconds:.2f}s"

    async def listen(self):
        while True:
            data = await self.reader.readexactly(4)

            (length,) = struct.unpack(">I", data)
            if length == 0:
                return
            data = await self.reader.readexactly(1)
            (id,) = struct.unpack(">B", data)

            if id == CHOKE:
                await self.handle_choke()
            elif id == UNCHOKE:
                pretty_print("Received UNCHOKE", "yellow")
                await self.handle_unchoke()
            elif id == INTERESTED:
                pass
            elif id == NOTINTERESTED:
                pass
            elif id == HAVE:
                await self.handle_have()
            elif id == BITFIELD:
                pretty_print("Received bitfield", "yellow")
                await self.handle_bitfield(length)
            elif id == REQUEST:
                pass
            elif id == PIECE:
                await self.handle_piece(length)
            elif id == CANCEL:
                pass
            else:
                print("Invalid message")

    async def handle_choke(self):
        self.writer.write(
            struct.pack(
                ">Ib",
                1,
                INTERESTED,
            )
        )
        await self.writer.drain()

    async def handle_unchoke(self):
        if not self.waiting:
            pretty_print("Unchoked!", "green")
            await self.send_request()
            pretty_print("Back to unchoke", "yellow")

    async def handle_have(self):
        piece_index_data = await self.reader.readexactly(4)
        piece_index = struct.unpack(">I", piece_index_data)[0]
        self.download_handler.handle_have(piece_index)
        self.pieces.add(piece_index)
        if not self.waiting:
            await self.send_request()

    async def handle_bitfield(self, length):
        bitfield = await self.reader.readexactly(length - 1)
        for index, byte in enumerate(bitfield):
            for bit in range(8):
                piece_index = index * 8 + bit
                if (byte >> (7 - bit)) & 1:  # if bit is set
                    self.download_handler.handle_have(piece_index)
                    self.pieces.add(piece_index)
                if piece_index >= len(
                    self.download_handler.needed_pieces
                ):  # if we have all the pieces
                    break

    async def handle_piece(self, length):
        piece_index_data = await self.reader.readexactly(4)
        piece_index = struct.unpack(">I", piece_index_data)[0]
        block_offset_data = await self.reader.readexactly(4)
        block_offset = struct.unpack(">I", block_offset_data)[0]
        block_data = await self.reader.readexactly(length - 9)
        if self.pending_piece:
            if self.pending_piece.offset == block_offset:
                self.pending_piece.actual_hash.update(block_data)
                self.filewriter.write_block(piece_index, block_offset, block_data)
                self.pending_piece.offset = block_offset + length - 9
            await self.send_request()

    async def send_request(self):
        length = self.pending_piece and self.pending_piece.next_block_length()
        if length is None:
            if self.pending_piece:
                # piece finished
                hash = self.pending_piece.actual_hash.digest()
                if hash != self.pending_piece.hash:
                    print("Incorrect hash.")
                    self.download_handler.pending_pieces.append(self.pending_piece)
                else:
                    self.download_handler.finished_pieces.append(self.pending_piece)

                    # time stuff
                    (
                        percent_complete,
                        estimated_remaining_time,
                    ) = self.calculate_time_since_download_started()

                    pretty_print(
                        f"[{self.peer_ip}] {percent_complete}% complete, Estimated remaining time: {self.format_time(estimated_remaining_time)}",
                        "yellow",
                        end="\r",
                    )

            self.pending_piece = self.download_handler.next(self.pieces)
            if self.pending_piece is None:
                self.waiting = False
                self.download_handler.check_done()
                pretty_print("Download complete! Yippee!", "green")
                self.torrent.complete = True
                return
            length = self.pending_piece.next_block_length()
        self.waiting = True
        
        self.writer.write(
            struct.pack(
                ">IbIII",
                13,
                REQUEST,
                self.pending_piece.index,
                self.pending_piece.offset,
                length,
            )
        )
        await self.writer.drain()
