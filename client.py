from torrent import Torrent
import asyncio

async def main():
    path = "./test_files/pg2600.txt.torrent"
    # path = "./test_files/debian-11.6.0-amd64-netinst.iso.torrent"
    verbose = True # if you want to allow stacktrace printing, set this to True
    torrent = Torrent(path, verbose)
    await torrent.start_connections()
    
asyncio.run(main())
    

