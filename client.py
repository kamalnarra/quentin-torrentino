from torrent import Torrent
import asyncio

path = "test/debian-11.6.0-amd64-netinst.iso.torrent"
torrent = Torrent(path)
asyncio.run(torrent.start_connections())
