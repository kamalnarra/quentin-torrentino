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
    def __init__(self, download_handler, ip, port, peer_id, info_hash, filewriter, torrent, verbose=True):
        self.filewriter = filewriter
        self.torrent = torrent
        self.download_handler = download_handler
        self.pieces = set()
        self.pending_piece = None
        self.peer_ip = ip
        self.peer_port = port
        self.client_id = peer_id
        self.info_hash = info_hash
        self.choked = True
        self.interested = False
        self.reader = None
        self.writer = None
        self.connection_try = 0 # number of times we tried to connect to this peer
        self.verbose = verbose # if you want to allow stacktrace printing
        self.start_time = time.time()  # record the start time of the download
        self.total_pieces = download_handler.tracker.num_pieces  # total number of pieces
        self.download_handler_lock = asyncio.Lock()
        self.filewriter_lock = asyncio.Lock()

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
        try:
            self.connection_try += 1 # increment the number of times we tried to connect to this peer
            self.reader, self.writer = await asyncio.open_connection(
                self.peer_ip, self.peer_port
            )
            # set timeout
            self.writer.get_extra_info("socket").settimeout(5)
            
            self.writer.write(self.make_handshake())
            print(f"[{self.peer_ip}]: SENT HANDSHAKE")
            await self.writer.drain()
            await self.validate_handshake()
        except ConnectionRefusedError:
            pretty_print(f"[{self.peer_ip}]: CONNECTION REFUSED. TRYING AGAIN.", "yellow")
            pretty_print(f"[{self.peer_ip}]: CONNECTION ATTEMPT {self.connection_try}", "magenta")
            if self.connection_try < 5: # try to connect 5 times
                await self.send_handshake()
            else:
                pretty_print(f"[{self.peer_ip}]: CONNECTION FAILED. REMOVING FROM PEER LIST", "red")
                self.torrent.peer_list.remove(self)
                return
        except Exception as e:
            if self.writer:
                self.writer.close()
            if self.verbose:
                traceback.print_exc()
            pretty_print("===Lost peer!===", "red")
            if self.pending_piece:
                self.download_handler.pending_pieces.append(self.pending_piece)
                    

    async def validate_handshake(self):
        recv_data = await self.reader.readexactly(68)
        recv_hash = recv_data[28:48]
        if recv_hash == self.info_hash:
            print(f"[{self.peer_ip}]: RECEIVED HANDSHAKE")
            await self.manage_peers()
        else:
            raise Exception("The hashes did not match")
      
    def calculate_time_since_download_started(self):
        # time stuff
        
        completed_pieces = len(self.download_handler.finished_pieces)
        percent_complete = round(completed_pieces * 100 / self.total_pieces)

        elapsed_time = time.time() - self.start_time  # total time taken so far
        estimated_total_time = elapsed_time * self.total_pieces / completed_pieces  # estimate total time
        estimated_remaining_time = estimated_total_time - elapsed_time  # estimate remaining time
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

    async def send_request(self):
        if self.pending_piece is None:
            async with self.download_handler_lock:
                self.pending_piece = self.download_handler.next(self.pieces)
                if self.pending_piece is None:
                    return
        length = self.pending_piece.next_block_length()
        if length is None:
            self.download_handler.finished_pieces.append(self.pending_piece)
                
                
            # time stuff
            percent_complete, estimated_remaining_time = self.calculate_time_since_download_started()

            pretty_print(
                f"[{self.peer_ip}] {percent_complete}% complete, "
                f"Estimated remaining time: {self.format_time(estimated_remaining_time)}", "yellow"
            )
            
            self.pending_piece = self.download_handler.next(self.pieces)
            if self.pending_piece is None:
                return
            length = self.pending_piece.next_block_length()
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

    async def manage_peers(self):
        x = 0
        while True:
            data = await self.reader.readexactly(4)
            try:
                (length,) = struct.unpack(">I", data)
            except:
                print(x)
                raise
            if length == 0:
                return
            data = await self.reader.readexactly(1)
            (id,) = struct.unpack(">B", data)
            if id == CHOKE:
                print(f"[{self.peer_ip}]: CHOKE")
                self.choked = True
                self.writer.write(
                    struct.pack(
                        ">Ib",
                        1,
                        INTERESTED,
                    )
                )
            elif id == UNCHOKE:
                print(f"[{self.peer_ip}]: UNCHOKE")
                self.choked = False
                await self.send_request()
                await self.writer.drain()
            elif id == INTERESTED:
                print(f"[{self.peer_ip}]: INTERESTED")
                self.interested = True
            elif id == NOTINTERESTED:
                print(f"[{self.peer_ip}]: NOTINTERESTED")
                self.interested = False
            elif id == HAVE:
                print(f"[{self.peer_ip}]: HAVE piece index: {piece_index}")
                piece_index_data = await self.reader.readexactly(4)
                piece_index = struct.unpack(">I", piece_index_data)[0]
                async with self.download_handler_lock:
                    self.download_handler.handle_have(piece_index)
                    self.pieces.add(piece_index)

            elif id == BITFIELD:
                bitfield = await self.reader.readexactly(length - 1)
                for index, byte in enumerate(bitfield):
                    for bit in range(8):
                        piece_index = index * 8 + bit
                        if (byte >> (7 - bit)) & 1:  # if bit is set
                            async with self.download_handler_lock:
                                self.download_handler.handle_have(piece_index)
                                self.pieces.add(piece_index)
                        if piece_index >= len(self.download_handler.needed_pieces):
                            break

            elif id == REQUEST:
                print(f"[{self.peer_ip}]: REQUEST")
            elif id == PIECE:
                piece_index_data = await self.reader.readexactly(4)
                piece_index = struct.unpack(">I", piece_index_data)[0]
                block_offset_data = await self.reader.readexactly(4)
                block_offset = struct.unpack(">I", block_offset_data)[0]
                block_data = await self.reader.readexactly(length - 9)
                async with self.filewriter_lock:
                    self.filewriter.write_block(piece_index, block_offset, block_data)
                    self.pending_piece.offset = block_offset + length - 9
                    await self.send_request()
            elif id == CANCEL:
                print(f"[{self.peer_ip}]: CANCEL")
            else:
                x += 1

    async def send_interested(self):
        message_id = 2
        msg = struct.pack(">Ib", 1, message_id)
        self.writer.write(msg)
        print(f"SENT INTERESTED: {msg}")
        await self.writer.drain()
        await self.manage_peers()
