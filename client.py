from torrent import Torrent
import asyncio

async def main():
    path = "./test_files/pg2600.txt.torrent"
    verbose = True # if you want to allow stacktrace printing, set this to True
    torrent = Torrent(path, verbose)
    await torrent.start_connections()
    
asyncio.run(main())
    

