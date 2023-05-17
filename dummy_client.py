import asyncio
import struct
import argparse
from tracker import Tracker
import random
from utils import pretty_print
from peer import PeerConnection
from torrent import Torrent


async def main(server_ip, server_port):
    path = "./test_files/pg2600.txt.torrent"
    # path = "./test_files/debian-11.6.0-amd64-netinst.iso.torrent"
    verbose = True
    dummy_torrent = Torrent(
        path,
        verbose,
        preferred_file_name="dummy.txt",  # for testing purposes only -- if we have the same file name,
        # as the torrent file we are downloading, we will overwrite it
    )
    dummy_pc = PeerConnection(  # create a new connection for each peer
        dummy_torrent.download_handler,
        server_ip,
        server_port,
        dummy_torrent.peer_id,
        dummy_torrent.tracker.info_hash,
        dummy_torrent.filewriter,
        dummy_torrent,
        dummy_torrent.verbose,  # flag to allow stacktrace printing
    )
    preferred_peer_list = [dummy_pc]  # for testing purposes
    await dummy_torrent.start_connections(preferred_peer_list)


# Parse command line arguments
parser = argparse.ArgumentParser(description="Quentin Tarantino.")
parser.add_argument("ip", type=str, help="Server IP address")
parser.add_argument("port", type=int, help="Server port number")
args = parser.parse_args()

# Run the main function
asyncio.run(main(args.ip, args.port))
