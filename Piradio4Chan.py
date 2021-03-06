"""
    Collect webm from 4chan and broadcast them to FM radio using raspberry pi
    I know, this sounds like a bad idea and it is,
    but at this point there is no way back now
"""
import json
import logging
import subprocess
import time
import _thread
import requests
import os
from random import randrange
import argparse


class Piradio4Chan:
    def __init__(self, keyword, input_file_types, input_boards, input_refresh_rate):
        self.headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1)\
         AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
        self.keyword = keyword
        self.file_types = input_file_types
        self.playlist = []
        self.index = 0
        self.boards = input_boards
        self.refresh_rate = input_refresh_rate
        self.frequency = "87.9"
        self.shuffle = False
        self.ps = "Piradio"
        self.rt = "Raspberry pi Radio Staion"
        self.pi = "2333"

        logging.basicConfig(level=logging.WARNING,
                            format='%(asctime)s %(levelname)s %(message)s',
                            datefmt='%a, %d %b %Y %H:%M:%S',
                            filename='links.log',
                            filemode='a')

    def start(self):
        _thread.start_new_thread(self.download, ("Downloader", 1))
        while True:
            self.collect()
            time.sleep(self.refresh_rate)

    def download(self, name, thread_num):
        music_pipe_r, music_pipe_w = os.pipe()
        dev_null = open(os.devnull, "w")
        logging.info("Started " + name + " with id "+str(thread_num))
        command = "sudo\u2333/home/pi/Playground/PiFM/src/pi_fm_rds\u2333-freq" \
                  "\u2333{}\u2333-ps\u2333{}\u2333-rt\u2333{}\u2333-pi\u2333{}\u2333-audio\u2333-".format(
                    self.frequency, self.ps, self.rt, self.pi).split("\u2333")

        # start radio
        subprocess.Popen(command, stdin=music_pipe_r, stdout=dev_null)
        while True:
            if self.playlist:
                file = self.playlist[self.index]
                print("Now playing ", file)
                try:
                    subprocess.call(" curl -s "+file+" |ffmpeg -i - -f mp3 -loglevel panic - |\
                     sox -t mp3 - -t wav - tempo 1.125 pitch 185 firfit ./75usPreEmphasis.ff",
                                    shell=True, stdout=music_pipe_w, stderr=dev_null)
                except OSError:
                    logging.warning("Unable to download {}".format(str(file)))
                else:
                    logging.info("Downloaded {}".format(str(file)))
                finally:
                    if self.shuffle:
                        self.index = randrange(0, len(self.playlist))
                    else:
                        self.index += 1
                        if self.index == len(self.playlist):
                            self.index = 0

    def collect(self):
        for board in self.boards:
            for page_num in range(1, 10):
                page_data = requests.get('https://a.4cdn.org/{}/{}.json'.format(board, page_num), headers=self.headers)
                page_data = json.loads(page_data.content.decode('utf-8'))
                threads = page_data["threads"]
                for thread in threads:
                    qualified = False
                    op = thread["posts"][0]

                    # check title and op name
                    if self.keyword in (op['name'] + op['semantic_url']):
                        qualified = True

                    # check comment section if there are comments
                    if "com" in op:
                        if self.keyword in op["com"]:
                            qualified = True

                    # webm not collected
                    if qualified:
                        thread_data = requests.get("https://a.4cdn.org/{}/thread/{}.json"
                                                   .format(board, op["no"]),
                                                   headers=self.headers)
                        thread_response = json.loads(thread_data.content.decode('utf-8'))
                        # posts is a list of posts
                        posts = thread_response["posts"]

                        # post is a dict with info about each post
                        for post in posts:
                            if "ext" in post and post["ext"][1:] in self.file_types:
                                download_link = "https://i.4cdn.org/{}/{}{}"\
                                    .format(board, post["tim"], post["ext"])

                                if download_link not in self.playlist:
                                    self.playlist.append(download_link)
            time.sleep(30)

parser = argparse.ArgumentParser()
parser.add_argument("-k", help="keyword")
parser.add_argument("-f", "--frequency", help="FM frequency")
parser.add_argument("-b", "--board",  nargs='*')
parser.add_argument("-s", "--shuffle", action="store_true")
parser.add_argument("-ps")
parser.add_argument("-rt")
parser.add_argument("-pi")
args = parser.parse_args()

x = Piradio4Chan("ygyl", ["webm"], ["wsg"], 60*10)
if args.k:
    x.keyword = args.k
if args.frequency:
    x.frequency = args.frequency
if args.board:
    x.boards = args.board
x.shuffle = args.shuffle
if args.ps:
    x.ps = args.ps
if args.rt:
    x.rt = args.rt
if args.pi:
    x.pi = args.pi

x.start()
