import math
import heapq
import hashlib
import random
from utils import pretty_print
import time
BLOCK_LENGTH = 2**14



class DownloadHandler:
    def __init__(self, tracker, torrent):
        self.tracker = tracker
        self.needed_pieces = []
        self.pending_pieces = []
        self.finished_pieces = []
        self.file_writer =None
        self.torrent = torrent
        self.start_time = time.time()  # record the start time of the download
        self.total_size = 0 # total file size
        self.init_pieces()
        

    def init_pieces(self):
        piece_length = self.tracker.piece_length
        for piece_num in range(0, self.tracker.num_pieces):
            hash = self.tracker.pieces[(20 * piece_num) : (20 * piece_num) + 20]
            if piece_num < (self.tracker.blocks_per_piece - 1):
                piece = Piece(
                    hash, piece_length, self.tracker.blocks_per_piece, piece_num
                )
            else:
                last_piece_length = 0
                if self.tracker.length % piece_length > 0:
                    last_piece_length = self.tracker.length % piece_length
                else:
                    last_piece_length = self.tracker.piece_length
                num_blocks_per_last_piece = math.ceil(last_piece_length / 2**14)
                piece = Piece(
                    hash, last_piece_length, num_blocks_per_last_piece, piece_num
                )
            self.needed_pieces.append([piece, 0])
        random.shuffle(self.needed_pieces)
        
    def get_finished_piece(self, piece_index):
        pretty_print("Getting finished piece", "magenta")
        # pretty_print(f"{self.finished_pieces}", "magenta")
        for piece in self.finished_pieces:
            pretty_print(f"{piece.index}", "magenta")
        pretty_print(f"{piece_index}", "yellow")
        for piece in self.finished_pieces:
            if piece.index == piece_index - 1:
                return piece
        return None


    def handle_have(self, piece_index):
        # if we don't have the piece, add it to the needed pieces
        # if we have the piece, increment the number of peers that have the piece
        if piece_index < self.tracker.num_pieces:
            # check if we have the piece
            l = [x for x in self.needed_pieces if x.index == piece_index]
            # if we don't have the piece, add it to the needed pieces
            if len(l):
                l[0][1] += 1
                
    # for avg download speed
    def format_size(self, size):
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        unit = 0
        while size >= 1024:
            size /= 1024
            unit += 1
        return f"{size:.2f}{units[unit]}"
    
    def get_avg_speed(self):
        elapsed_time = time.time() - self.start_time  # total time taken
        average_speed = self.total_size / elapsed_time  # calculate average speed in bytes/second
        return average_speed

    # what this function does is that it takes 
    # a piece and a block index and returns the block data
    def next(self, pieces):
        # if there are pending pieces, return the first one
        if len(self.pending_pieces):
            # return the first pending piece
            return self.pending_pieces.pop(0)
        # if there are no pending pieces, check if there are any needed pieces
        if len(self.needed_pieces) == 0:
            avg_speed = self.get_avg_speed()
            pretty_print("DOWNLOAD FINISHED 🥳🥳🥳", "green")
            pretty_print(f"Average download speed: {self.format_size(avg_speed)}/s", "green")
            
            
            
                
            return None
        # if there are needed pieces, check if any of them are in the pieces list
        filtered = [x for x in self.needed_pieces if x[0].index in pieces]
        # if there are no pieces in the pieces list, return None
        if len(filtered) == 0:
            return None
        # if there are pieces in the pieces list, return the first one
        top = min(filtered, key=lambda x: x[1])
        # if the piece is not downloaded, return the piece
        self.needed_pieces.remove(top)
        # if the piece is downloaded, return None
        return top[0]


class Piece:
    def __init__(self, hash, length, num_blocks, index):
        self.downloaded = False
        self.index = index
        self.offset = 0
        self.hash = hash
        self.length = length
        self.num_blocks = num_blocks
        self.blocks = []
        self.blocks_so_far = 0

    def next_block_length(self):
        # what this does is that it returns the length of the next block
        if self.offset + BLOCK_LENGTH <= self.num_blocks * BLOCK_LENGTH:
            return BLOCK_LENGTH
        # if the next block is the last block, return the length of the last block
        elif self.length - self.offset > 0:
            return self.length - self.offset
        # if the piece is downloaded, return None
        else:
            pretty_print("Piece downloaded", "green")
            return None
        
 


class FileWriter:
    def __init__(self, filename, total_size, download_handler):
        self.filename = filename
        self.total_size = total_size
        self.download_handler = download_handler
        self.file = open(filename, "wb")
        
        # self.data below is a 2d file that stores the data of each pice
        # each containing a list of blocks
        self.data = []

    def write_block(self, piece_index, block_index, block_data):
        current_piece = self.download_handler.get_finished_piece(piece_index)
        pretty_print(f"at {current_piece}", "green")
        # calculate the position of the block in the file
        position = piece_index * self.total_size + block_index
        # seek to the position and write the data
        self.file.seek(position)
        # write the data
        self.file.write(block_data)
        # flush the data to the file
        self.file.flush()
        
    
    def close(self):
        self.file.close()
