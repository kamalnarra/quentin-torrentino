import asyncio
import struct
from utils import pretty_print

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


class Seeder:
    def __init__(self, host, port, peer_id, info_hash, filewriter, torrent):
        self.host = host
        self.port = port
        self.peer_id = peer_id
        self.info_hash = info_hash
        self.filewriter = filewriter
        self.torrent = torrent
        self.server = None

    async def start(self):
        self.server = await asyncio.start_server(
            self.handle_peer_connection, self.host, self.port
        )

        addr = self.server.sockets[0].getsockname()
        print(f"Seeding on {addr}")

        async with self.server:
            await self.server.serve_forever()

    async def send_bitfield(self, writer):
        bitfield = self.filewriter.get_bitfield()
        
        message = struct.pack(">Ib", len(bitfield) + 1, BITFIELD) + bitfield
        writer.write(message)
        await writer.drain()

    async def handle_peer_connection(self, reader, writer):
        addr = writer.get_extra_info("peername")
        print(f"Accepted connection from {addr}")

        # Handle handshake
        handshake = await reader.read(68)
        if not self.is_valid_handshake(handshake):
            print(f"Invalid handshake from {addr}")
            writer.close()
            return
        else:
            pretty_print(f"Valid handshake from {addr}", "green")

        # send handshake
        writer.write(handshake)

        # send bitfield
        await self.send_bitfield(writer)

        # send UNCHOKE
        writer.write(struct.pack(">IB", 1, UNCHOKE))

        # Handle incoming requests
        while not reader.at_eof():
            message_length_data = await reader.read(4)
            message_length = struct.unpack(">I", message_length_data)[0]
            if message_length == 0:
                continue  # keep-alive message

            message_id_data = await reader.read(1)
            message_id = struct.unpack(">B", message_id_data)[0]

            if message_id == REQUEST:
                # Peer requested a piece
                index, begin, length = struct.unpack(">III", await reader.read(12))
                await self.send_piece(writer, index, begin, length)

            else:
                print(f"Unexpected message id {message_id} from {addr}")

        print(f"Connection closed by {addr}")
        writer.close()

    def is_valid_handshake(self, handshake):
        recv_hash = handshake[28:48]
        return recv_hash == self.info_hash

    async def send_piece(self, writer, index, begin, length):
        try:
            pretty_print(
                f"Sending piece {index} (offset {begin}, length {length})", "green"
            )

            # Read the requested piece from the file
            piece_data = self.filewriter.read_piece(index, begin, length)
            

            # Send piece message: length prefix (4 bytes) + message ID (1 byte) + piece index (4 bytes) + block offset (4 bytes) + block data
            writer.write(struct.pack(">IbII", 9 + len(piece_data), PIECE, index, begin))
            writer.write(piece_data)
            self.torrent.uploaded += len(piece_data)

            await writer.drain()
        except Exception as e:
            print(f"Error sending piece {index} (offset {begin}, length {length}): {e}")
            writer.close()
            return
