"""
    pipe file collected from 4chan to stdout
"""
import json
import logging
from pprint import pprint
import subprocess
import time
import _thread
import requests
import os


class ChanPiper:

    def __init__(self, keyword, input_file_types, input_boards, input_refresh_rate):
        self.headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1)\
         AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}
        self.keyword = keyword
        self.file_types = input_file_types
        self.playlist = []
        self.processing = 0
        self.boards = input_boards
        self.refresh_rate = input_refresh_rate
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
        logging.info("Started " + name + " with id "+str(thread_num))
        while True:
            if self.playlist:
                pass
                file = self.playlist[self.processing]
                print("Now playing ", file)
                try:
                    subprocess.call(" curl -s "+file+" |ffmpeg -i - -f mp3 -loglevel panic - |\
                     sox -t mp3 - -t wav - tempo 1.125 pitch 150 firfit ./75usPreEmphasis.ff|\
                      sudo ./pi_fm_rds -freq 88.8 -ps \"4ChRadio\" -rt \"4Chan Radio Station\" -pi 2333 -audio -",
                                    shell=True)
                    self.processing += 1
                except OSError as e:
                    logging.warning("Unable to download {}".format(str(file)))
                else:
                    logging.warning("Downloaded {}".format(str(file)))
            time.sleep(1)

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

                    if qualified:
                        thread_data = requests.get("https://a.4cdn.org/{}/thread/{}.json".format(board, op["no"]),
                                                   headers=self.headers)
                        thread_response = json.loads(thread_data.content.decode('utf-8'))
                        # posts is a list of posts
                        posts = thread_response["posts"]

                        # post is a dict with info about each post
                        for post in posts:
                            if "ext" in post and post["ext"][1:] in self.file_types:
                                download_link = "https://i.4cdn.org/{}/{}{}".format(board, post["tim"], post["ext"])
                                if download_link not in self.playlist:
                                    self.playlist.append(download_link)
                time.sleep(30)

x = ChanPiper("ygyl", ["webm"], ["wsg"], 60*10)
x.start()
